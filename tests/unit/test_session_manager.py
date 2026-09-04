from __future__ import annotations

from pathlib import Path

import pytest

from kama_claude.core.bus.envelope import HandlerError
from kama_claude.core.events.bus import EventBus
from kama_claude.core.runner import RunOutcome
from kama_claude.core.session.manager import SESSION_CLOSED, SESSION_NOT_FOUND, SessionManager
from kama_claude.core.session.model import Session
from kama_claude.core.session.store import SessionStore


class _Runner:
    # 模擬 AgentRunner，將 run 新訊息寫入 thread 後返回成功
    async def run_and_capture(
        self,
        goal: str,
        *,
        run_id: str | None = None,
        session: Session | None = None,
        store: SessionStore | None = None,
        system_prompt_override: str | None = None,
        tool_whitelist: list[str] | None = None,
    ) -> RunOutcome:
        assert run_id is not None
        assert session is not None
        assert store is not None
        store.append_messages(
            session.id,
            [{"role": "assistant", "content": [{"type": "text", "text": f"done {goal}"}]}],
            run_id,
        )
        return RunOutcome(status="success", result="done", reason=None)


# 功能：驗證 create 會建立 active session、寫入 meta 併發布 session.created 事件
# 設計：用真實 SessionStore + EventBus 收集事件，覆蓋 manager 與 store/bus 的協作邊界
async def test_create_session_writes_meta_and_event(tmp_path: Path) -> None:
    events: list[object] = []
    bus = EventBus()

    async def collect(event: object) -> None:
        events.append(event)

    bus.subscribe(collect)
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), bus)  # type: ignore[arg-type]

    session = await manager.create("chat", "title")

    assert session.status == "active"
    assert store.read_meta(session.id).title == "title"
    assert [e.type for e in events] == ["session.created"]  # type: ignore[attr-defined]


# 功能：驗證 chat session 處理一條訊息後進入 waiting_for_input，並保留 user/assistant thread
# 設計：mock runner 主動追加 assistant 訊息，確認 send_message 負責 user 訊息、狀態流轉和 run_id 記錄
async def test_send_message_chat_enters_waiting_and_writes_thread(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")

    run_id = await manager.send_message(session.id, "hello")

    loaded = store.read_meta(session.id)
    assert loaded.status == "waiting_for_input"
    assert loaded.run_ids == [run_id]
    messages = store.read_messages(session.id)
    assert messages[0] == {"role": "user", "content": "hello"}
    assert messages[1]["role"] == "assistant"


# 功能：驗證 one_shot session 在單次訊息完成後自動 closed
# 設計：複用 mock runner 的成功路徑，聚焦 mode 對最終狀態的影響，保證 kama run 的統一路徑正確
async def test_one_shot_auto_closes(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("one_shot")

    await manager.send_message(session.id, "hello")

    assert store.read_meta(session.id).status == "closed"


# 功能：驗證不存在的 session_id 返回 session_not_found 錯誤碼
# 設計：直接呼叫 get_history 的查詢路徑，斷言 HandlerError code，覆蓋 IPC handler 可結構化返回錯誤
async def test_missing_session_raises_handler_error(tmp_path: Path) -> None:
    manager = SessionManager(SessionStore(tmp_path), lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    with pytest.raises(HandlerError) as exc:
        await manager.get_history("missing")
    assert exc.value.code == SESSION_NOT_FOUND


# 功能：驗證 closed session 不能繼續 send_message
# 設計：先顯式 close，再傳送訊息，斷言 session_closed 錯誤碼，覆蓋狀態機拒絕路徑
async def test_closed_session_rejects_message(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")
    await manager.close(session.id)

    with pytest.raises(HandlerError) as exc:
        await manager.send_message(session.id, "again")
    assert exc.value.code == SESSION_CLOSED
