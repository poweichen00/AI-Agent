from __future__ import annotations

from agentx.core.context import ExecutionContext


def _make_ctx(**kwargs) -> ExecutionContext:
    defaults = dict(run_id="r1", goal="test goal", max_steps=5)
    defaults.update(kwargs)
    return ExecutionContext(**defaults)


# 功能：驗證三層記憶全部存在時都出現在 system prompt 中且順序正確
# 設計：分別設定 global_context、project_context、session_notes，斷言各 section 標題及內容依次出現
def test_all_layers_present() -> None:
    ctx = _make_ctx(
        global_context="global line",
        project_context="project line",
        session_notes="session note",
    )
    prompt = ctx.system_prompt("BASE")
    assert "BASE" in prompt
    assert "## Global Context\nglobal line" in prompt
    assert "## Project Context\nproject line" in prompt
    assert "## Session Notes\nsession note" in prompt
    # 順序：global 在 project 之前，project 在 session 之前
    assert prompt.index("Global") < prompt.index("Project") < prompt.index("Session")


# 功能：驗證三層均為空時 system prompt 只含 base
# 設計：不設定任何記憶欄位，斷言輸出等於 base
def test_no_layers() -> None:
    ctx = _make_ctx()
    prompt = ctx.system_prompt("BASE_ONLY")
    assert prompt == "BASE_ONLY"


# 功能：驗證只有 global_context 時只出現 Global section，其他 section 不出現
# 設計：只設定 global_context，斷言 Project 和 Session 標題不在 prompt 中
def test_only_global() -> None:
    ctx = _make_ctx(global_context="global content")
    prompt = ctx.system_prompt("BASE")
    assert "## Global Context" in prompt
    assert "## Project Context" not in prompt
    assert "## Session Notes" not in prompt


# 功能：驗證 session_notes 非空時包含 note_save 提示語
# 設計：只設定 session_notes，斷言 prompt 含 note_save 相關提示
def test_session_notes_hint() -> None:
    ctx = _make_ctx(session_notes="some note")
    prompt = ctx.system_prompt("BASE")
    assert "note_save" in prompt
