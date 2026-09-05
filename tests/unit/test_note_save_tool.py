from __future__ import annotations

from pathlib import Path

from agentx.core.session.store import SessionStore
from agentx.core.tools.builtin.note_save import NoteSaveTool


# 功能：驗證 note_save 正常呼叫會把 content 寫入 notes.md
# 設計：使用真實 SessionStore 和 tmp_path，斷言工具返回與檔案內容，覆蓋工具到檔案層的完整路徑
async def test_note_save_appends_note(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    tool = NoteSaveTool(store, "sess-1", "run-1")

    result = await tool.invoke({"content": "Python 3.12"})

    assert result.content == "saved"
    assert not result.is_error
    assert "Python 3.12" in store.read_notes("sess-1")


# 功能：驗證空 content 會返回工具錯誤且不寫入 notes.md
# 設計：傳入空白字串，斷言 is_error 與 error_type，覆蓋 schema 之外的業務校驗
async def test_note_save_rejects_empty_content(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    tool = NoteSaveTool(store, "sess-1", "run-1")

    result = await tool.invoke({"content": "   "})

    assert result.is_error
    assert result.error_type == "runtime_error"
    assert store.read_notes("sess-1") == ""
