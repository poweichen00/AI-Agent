from __future__ import annotations

import asyncio
import subprocess
from typing import Any

from kama_claude.core.transport.socket_client import SocketClient


# 功能：驗證 agent.run 命令返回非空 run_id，且 daemon 隨即廣播 run.started 事件
# 設計：用 SocketClient 封裝 IPC 層，asyncio.Event 等待事件而非輪詢，
#       timeout=5s 防測試掛起；run.started 在 LLM 呼叫前觸發，無需真實 API Key
async def test_agent_run_returns_run_id_and_emits_started(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
) -> None:
    client = SocketClient("127.0.0.1", free_port)
    await client.connect()

    started_event: asyncio.Event = asyncio.Event()
    received: dict[str, Any] = {}

    async def on_event(event: dict[str, Any]) -> None:
        if event.get("type") == "run.started":
            received.update(event)
            started_event.set()

    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())

    try:
        await client.send_command("event.subscribe", {"topics": ["run.*"], "scope": "global"})
        result = await client.send_command("agent.run", {"goal": "hello"})

        assert result.get("run_id"), "run_id must be non-empty"
        returned_run_id: str = result["run_id"]

        await asyncio.wait_for(started_event.wait(), timeout=5.0)
        assert received.get("run_id") == returned_run_id
        assert received.get("goal") == "hello"
    finally:
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)
        await client.close()


# 功能：驗證兩個獨立客戶端同時訂閱後，其中一個觸發 agent.run，兩個都能收到 run.started 廣播
# 設計：兩個 SocketClient 並行等待事件（asyncio.gather），確認 IpcEventBroadcaster 的扇出語義；
#       不需要兩個客戶端都發命令，只驗證廣播覆蓋所有訂閱者
async def test_two_clients_both_receive_broadcast(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
) -> None:
    client1 = SocketClient("127.0.0.1", free_port)
    client2 = SocketClient("127.0.0.1", free_port)
    await client1.connect()
    await client2.connect()

    event1: asyncio.Event = asyncio.Event()
    event2: asyncio.Event = asyncio.Event()

    async def on_event1(event: dict[str, Any]) -> None:
        if event.get("type") == "run.started":
            event1.set()

    async def on_event2(event: dict[str, Any]) -> None:
        if event.get("type") == "run.started":
            event2.set()

    client1.on_event(on_event1)
    client2.on_event(on_event2)

    loop1 = asyncio.create_task(client1.run_event_loop())
    loop2 = asyncio.create_task(client2.run_event_loop())

    try:
        await client1.send_command("event.subscribe", {"topics": ["run.*"], "scope": "global"})
        await client2.send_command("event.subscribe", {"topics": ["run.*"], "scope": "global"})
        await client1.send_command("agent.run", {"goal": "broadcast test"})

        await asyncio.wait_for(
            asyncio.gather(event1.wait(), event2.wait()),
            timeout=5.0,
        )
    finally:
        loop1.cancel()
        loop2.cancel()
        await asyncio.gather(loop1, loop2, return_exceptions=True)
        await client1.close()
        await client2.close()


# 功能：驗證客戶端斷開後使用 replay_from_run 重連，訂閱響應中 replayed_count > 0
# 設計：client1 觸發 run 並等到 run.started 落盤（run.started 在 LLM 呼叫前寫入 events.jsonl），
#       稍作等待後斷開；client2 用 replay_from_run=run_id 訂閱，斷言 replayed_count > 0，
#       不依賴 API Key，只需驗證 replay 機制讀出了已落盤的 run.started
async def test_disconnect_and_replay_from_run(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
) -> None:
    # Phase 1: trigger a run and wait for run.started to be written to disk
    client1 = SocketClient("127.0.0.1", free_port)
    await client1.connect()

    started_event: asyncio.Event = asyncio.Event()
    run_id_holder: list[str] = []

    async def on_event(event: dict[str, Any]) -> None:
        if event.get("type") == "run.started":
            run_id_holder.append(event.get("run_id", ""))
            started_event.set()

    client1.on_event(on_event)
    loop1 = asyncio.create_task(client1.run_event_loop())

    try:
        await client1.send_command("event.subscribe", {"topics": ["run.*"], "scope": "global"})
        await client1.send_command("agent.run", {"goal": "replay test"})
        await asyncio.wait_for(started_event.wait(), timeout=5.0)
    finally:
        loop1.cancel()
        await asyncio.gather(loop1, return_exceptions=True)
        await client1.close()

    assert run_id_holder, "run.started was never received"
    run_id = run_id_holder[0]

    # Brief pause to ensure the event is flushed to disk before we replay
    await asyncio.sleep(0.05)

    # Phase 2: reconnect with replay_from_run and verify replayed_count > 0
    client2 = SocketClient("127.0.0.1", free_port)
    await client2.connect()
    loop2 = asyncio.create_task(client2.run_event_loop())

    try:
        result = await client2.send_command(
            "event.subscribe",
            {
                "topics": ["run.*"],
                "scope": "global",
                "replay_from_run": run_id,
            },
        )
        assert result.get("replayed_count", 0) > 0, (
            f"Expected replayed_count > 0 for run_id={run_id!r}, got {result}"
        )
    finally:
        loop2.cancel()
        await asyncio.gather(loop2, return_exceptions=True)
        await client2.close()
