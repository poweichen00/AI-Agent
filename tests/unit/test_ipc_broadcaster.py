from __future__ import annotations

import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from kama_claude.core.bus.events import RunStartedEvent, StepStartedEvent
from kama_claude.core.transport.ipc_broadcaster import IpcEventBroadcaster


def _make_writer(*, drain_raises: Exception | None = None) -> asyncio.StreamWriter:
    writer = MagicMock(spec=asyncio.StreamWriter)
    if drain_raises is not None:
        writer.drain = AsyncMock(side_effect=drain_raises)
    else:
        writer.drain = AsyncMock()
    return cast(asyncio.StreamWriter, writer)


def _run_started(run_id: str = "r1") -> RunStartedEvent:
    return RunStartedEvent(run_id=run_id, goal="test", ts="2026-01-01T00:00:00Z")


# 功能：驗證 subscribe 後 handle 將匹配 topic 的事件寫入 writer，且內容是合法的 EventPushEnvelope
# 設計：用 MagicMock writer 捕獲寫入的位元組，反序列化後斷言 kind 和 event.type，排除對網路層的依賴
async def test_subscriber_receives_matching_event() -> None:
    broadcaster = IpcEventBroadcaster()
    writer = _make_writer()
    broadcaster.subscribe(writer, topics=["run.*"])

    await broadcaster.handle(_run_started())

    writer.write.assert_called_once()  # type: ignore[attr-defined]
    data = json.loads(writer.write.call_args[0][0].rstrip(b"\n"))  # type: ignore[attr-defined]
    assert data["kind"] == "event"
    assert data["event"]["type"] == "run.started"


# 功能：驗證無訂閱時 handle 不向任何 writer 寫入資料
# 設計：建立 broadcaster 但不 subscribe，呼叫 handle 後斷言 write 從未被呼叫，驗證空 fan-out 的邊界情況
async def test_no_subscription_no_write() -> None:
    broadcaster = IpcEventBroadcaster()
    writer = _make_writer()

    await broadcaster.handle(_run_started())

    writer.write.assert_not_called()  # type: ignore[attr-defined]


# 功能：驗證 topic glob "step.*" 匹配 step.started 但不匹配 run.started
# 設計：向同一 broadcaster 釋出兩種事件，斷言 write 只被呼叫一次，驗證 fnmatch 語義的 glob 邊界行為
async def test_topic_glob_matches_step_not_run() -> None:
    broadcaster = IpcEventBroadcaster()
    writer = _make_writer()
    broadcaster.subscribe(writer, topics=["step.*"])

    step_event = StepStartedEvent(run_id="r1", step=1, ts="2026-01-01T00:00:00Z")
    run_event = _run_started()

    await broadcaster.handle(step_event)
    await broadcaster.handle(run_event)

    assert writer.write.call_count == 1  # type: ignore[attr-defined]
    data = json.loads(writer.write.call_args[0][0].rstrip(b"\n"))  # type: ignore[attr-defined]
    assert data["event"]["type"] == "step.started"


# 功能：驗證 scope="global" 的訂閱能收到任意 run_id 的事件
# 設計：釋出兩個不同 run_id 的事件，斷言兩次都寫入，確認 global scope 不過濾 run_id 欄位
async def test_scope_global_receives_all_run_ids() -> None:
    broadcaster = IpcEventBroadcaster()
    writer = _make_writer()
    broadcaster.subscribe(writer, topics=["run.*"], scope="global")

    await broadcaster.handle(_run_started("r1"))
    await broadcaster.handle(_run_started("r2"))

    assert writer.write.call_count == 2  # type: ignore[attr-defined]


# 功能：驗證 scope="run:<id>" 只接收匹配 run_id 的事件，過濾其他 run_id
# 設計：訂閱 scope="run:abc"，釋出 run_id="abc" 和 run_id="xyz"，斷言只寫入一次，驗證 run-specific scope 的過濾語義
async def test_scope_run_specific_filters_other_run_ids() -> None:
    broadcaster = IpcEventBroadcaster()
    writer = _make_writer()
    broadcaster.subscribe(writer, topics=["run.*"], scope="run:abc")

    await broadcaster.handle(_run_started("abc"))
    await broadcaster.handle(_run_started("xyz"))

    assert writer.write.call_count == 1  # type: ignore[attr-defined]


# 功能：驗證 unsubscribe 後 handle 不再向該 writer 傳送事件
# 設計：先 subscribe 再 unsubscribe，再呼叫 handle，斷言 write 從未被呼叫，驗證訂閱生命週期的正確性
async def test_unsubscribe_stops_delivery() -> None:
    broadcaster = IpcEventBroadcaster()
    writer = _make_writer()
    broadcaster.subscribe(writer, topics=["run.*"])
    broadcaster.unsubscribe(writer)

    await broadcaster.handle(_run_started())

    writer.write.assert_not_called()  # type: ignore[attr-defined]


# 功能：驗證寫入失敗（ConnectionResetError）後訂閱自動移除，下次 handle 不再嘗試寫入
# 設計：drain() 丟擲 ConnectionResetError 觸發死連線清理；斷言第二次 handle 時 write 未被呼叫；
#       第一次 write 在 drain 前已執行，call_count==1 是預期行為而非被測點
async def test_dead_connection_removed_after_failure() -> None:
    broadcaster = IpcEventBroadcaster()
    writer = _make_writer(drain_raises=ConnectionResetError())
    broadcaster.subscribe(writer, topics=["run.*"])

    event = _run_started()
    await broadcaster.handle(event)  # drain fails → subscription removed

    assert writer.write.call_count == 1  # type: ignore[attr-defined]

    writer.write.reset_mock()  # type: ignore[attr-defined]
    await broadcaster.handle(event)  # no subscribers remain
    writer.write.assert_not_called()  # type: ignore[attr-defined]
