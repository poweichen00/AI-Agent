from __future__ import annotations

from pathlib import Path

from agentx.core.session.model import Session
from agentx.core.session.store import SessionStore


# 功能：驗證 SessionStore 初始化時自動建立 sessions 根目錄
# 設計：傳入 tmp_path 下不存在的目錄，斷言目錄被建立，覆蓋首次啟動 daemon 的冷路徑
def test_store_creates_root(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    SessionStore(root)
    assert root.exists()


# 功能：驗證 session meta 寫入後能完整讀回
# 設計：構造含 run_ids 的 Session，經過 JSON 檔案往返後斷言欄位保持，覆蓋 meta.json 的持久化契約
def test_meta_roundtrip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = Session(
        id="sess-1",
        mode="chat",
        status="waiting_for_input",
        title="hello",
        created_at="t1",
        updated_at="t2",
        run_ids=["run-1"],
    )
    store.write_meta(session)
    loaded = store.read_meta("sess-1")
    assert loaded == session


# 功能：驗證含 tool_use/tool_result block 的 thread 訊息能按 Anthropic 格式讀回
# 設計：追加 assistant tool_use 和 user tool_result，讀取時應剝離 ts/run_id，只保留 API messages 所需欄位
def test_thread_message_roundtrip_with_tool_blocks(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.append_message("sess-1", "user", "read file")
    store.append_message(
        "sess-1",
        "assistant",
        [{"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}}],
        run_id="run-1",
    )
    store.append_message(
        "sess-1",
        "user",
        [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        run_id="run-1",
    )

    messages = store.read_messages("sess-1")
    assert messages == [
        {"role": "user", "content": "read file"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        },
    ]


# 功能：驗證 thread 尾部孤兒 tool_use 會被裁掉
# 設計：構造一條未配對 tool_result 的 assistant tool_use，讀取時只返回最後一次配平之前的訊息，避免 API 報 messages.invalid
def test_read_messages_trims_orphan_tool_use_tail(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.append_message("sess-1", "user", "hello")
    store.append_message(
        "sess-1",
        "assistant",
        [{"type": "tool_use", "id": "orphan", "name": "read_file", "input": {}}],
        run_id="run-1",
    )
    assert store.read_messages("sess-1") == [{"role": "user", "content": "hello"}]


# 功能：驗證 notes.md 不存在時讀為空，追加筆記後能讀到內容和 run_id
# 設計：先讀空狀態再追加，覆蓋 chat 第一輪前和 note_save 呼叫後的兩個關鍵狀態
def test_notes_read_and_append(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    assert store.read_notes("sess-1") == ""
    store.append_note("sess-1", "Python 3.12", "run-1")
    notes = store.read_notes("sess-1")
    assert "Python 3.12" in notes
    assert "run-1" in notes
