from __future__ import annotations

import os

from rich.markdown import Markdown
from textual.widget import Widget

from agentx.tui.app import (
    AgentXTuiApp,
    LLMStreamBlock,
    ToolCallBlock,
    _param_summary,
    _preview,
)


# 功能：驗證 _preview 超出長度時截斷並追加省略號
# 設計：不依賴任何 TUI 元件，純函式測試
def test_preview_truncates() -> None:
    assert _preview("abcde", 3) == "abc…"
    assert _preview("ab", 5) == "ab"


# 功能：驗證工具引數摘要優先展示工具最關鍵欄位
# 設計：覆蓋 read_file/bash/note_save 三類常見工具，避免工具塊摘要退化成整段 JSON
def test_param_summary_prefers_key_fields() -> None:
    assert _param_summary("read_file", {"path": "README.md"}) == "path='README.md'"
    assert _param_summary("bash", {"command": "echo hi", "timeout": 1}) == "command='echo hi'"
    assert _param_summary("note_save", {"content": "Python 3.12"}) == "content='Python 3.12'"


# 功能：驗證 llm.token 事件累積到 LLMStreamBlock，不連續 token 各自新開一塊
# 設計：monkey-patch _append 收集追加的 widgets，斷言 token 追加到同一塊；
#       傳送非 token 事件後新 block 被重置，下一個 token 開啟新塊
def test_llm_tokens_accumulate_in_block() -> None:
    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event({"type": "llm.token", "token": "Hello", "run_id": "r", "ts": "t"})
    app._handle_event({"type": "llm.token", "token": " world", "run_id": "r", "ts": "t"})

    assert len(appended) == 1  # same block reused
    assert isinstance(appended[0], LLMStreamBlock)
    assert appended[0]._text == "Hello world"  # type: ignore[attr-defined]


# 功能：驗證 LLMStreamBlock 結束時會把累積文字渲染為 Rich Markdown
# 設計：直接呼叫 finalize_markdown，斷言 renderable 型別，覆蓋 Markdown polish 的核心行為
def test_llm_block_finalize_renders_markdown() -> None:
    block = LLMStreamBlock()
    block.append_token("## Title\n\n- one\n\n```python\nprint('hi')\n```")
    block.finalize_markdown()
    assert isinstance(block.content, Markdown)


# 功能：驗證非 token 事件後 _current_llm 被重置，下一個 token 開啟新塊
# 設計：插入 step.started 中斷流，驗證之前的 block 被 finalize，之後的 llm.token 建立新 LLMStreamBlock
def test_llm_block_resets_after_non_token_event() -> None:
    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event({"type": "llm.token", "token": "A", "run_id": "r", "ts": "t"})
    app._handle_event({"type": "step.started", "run_id": "r", "step": 2, "ts": "t"})
    app._handle_event({"type": "llm.token", "token": "B", "run_id": "r", "ts": "t"})

    llm_blocks = [w for w in appended if isinstance(w, LLMStreamBlock)]
    assert len(llm_blocks) == 2
    assert llm_blocks[0]._finalized  # type: ignore[attr-defined]


# 功能：驗證 run.started 事件追加 Static widget 且包含 run_id 和 goal
# 設計：monkey-patch _append，斷言追加的 widget 的 renderable 包含關鍵欄位
def test_run_started_appends_widget_with_content() -> None:
    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event(
        {"type": "run.started", "run_id": "run-abc", "goal": "do the thing", "ts": "t"}
    )

    assert len(appended) == 1
    rendered = appended[0].content
    assert "run-abc" in rendered
    assert "do the thing" in rendered


# 功能：驗證 run.finished success 追加包含 "completed" 的 widget
# 設計：monkey-patch _append，檢查 rendered 內容包含 completed 和 green
def test_run_finished_success_shows_completed() -> None:
    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event(
        {"type": "run.finished", "run_id": "r", "status": "success", "steps": 3, "ts": "t"}
    )

    rendered = appended[0].content
    assert "completed" in rendered
    assert "green" in rendered


# 功能：驗證 run.finished failed 追加包含 "failed" 和 red 的 widget
# 設計：與 success 對稱，檢查顏色標記差異
def test_run_finished_failed_shows_red() -> None:
    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event(
        {
            "type": "run.finished",
            "run_id": "r",
            "status": "failed",
            "steps": 1,
            "reason": "llm_error",
            "ts": "t",
        }
    )

    rendered = appended[0].content
    assert "failed" in rendered
    assert "red" in rendered


# 功能：驗證 tool.call_started 追加 ToolCallBlock，call_finished 更新其結果
# 設計：直接呼叫 _handle_event 兩次，透過 _pending_tool_blocks 驗證狀態流轉
def test_tool_call_started_and_finished() -> None:
    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event(
        {
            "type": "tool.call_started",
            "tool_use_id": "uid-1",
            "tool_name": "bash",
            "params": {"command": "echo hi"},
            "run_id": "r",
            "ts": "t",
        }
    )
    assert "uid-1" in app._pending_tool_blocks  # type: ignore[attr-defined]

    app._handle_event(
        {
            "type": "tool.call_finished",
            "tool_use_id": "uid-1",
            "tool_name": "bash",
            "elapsed_ms": 42,
            "output": "hi",
            "run_id": "r",
            "ts": "t",
        }
    )
    assert "uid-1" not in app._pending_tool_blocks  # type: ignore[attr-defined]
    block = appended[0]
    assert isinstance(block, ToolCallBlock)
    assert block._finished  # type: ignore[attr-defined]
    assert block._output == "hi"  # type: ignore[attr-defined]


# 功能：驗證 note_save 成功完成時工具塊摘要顯示 remembered
# 設計：直接操作 ToolCallBlock，覆蓋 note_save 的特殊低噪聲展示策略
def test_note_save_tool_block_shows_remembered() -> None:
    block = ToolCallBlock("note_save", {"content": "Python 3.12"})
    block.set_result("saved", 3)
    assert "remembered" in block._summary()  # type: ignore[attr-defined]


# 功能：驗證提交使用者輸入時會追加 user turn，並進入 busy 狀態
# 設計：用 fake client 替代 SocketClient，直接呼叫 on_chat_text_area_submitted，
#       覆蓋 TextArea 清空內容 + 設定 busy 佔位符的核心狀態遷移
async def test_input_submit_appends_user_turn_and_disables_prompt() -> None:
    class _FakeArea:
        def __init__(self) -> None:
            self.disabled = False
            self.border_title = ""
            self.text = "hello"

    class _FakeEvent:
        def __init__(self, area: _FakeArea) -> None:
            self.value = area.text
            self.text_area = area

    class _FakeClient:
        async def send_command(self, method: str, params: dict) -> dict:
            return {"run_id": "run-1"}

    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]
    app._update_header = lambda state: None  # type: ignore[method-assign]
    app._client = _FakeClient()  # type: ignore[assignment]
    app._session_id = "sess-1"

    area = _FakeArea()
    event = _FakeEvent(area)
    await app.on_chat_text_area_submitted(event)  # type: ignore[arg-type]

    assert app._busy  # type: ignore[attr-defined]
    assert area.disabled
    assert area.text == ""
    assert "agent is working" in area.border_title.lower()
    assert appended[0].content == "[bold]>[/bold] hello"


# 功能：驗證未知事件型別不拋異常也不追加任何 widget
# 設計：傳送 type 為 unknown 的事件，斷言 appended 為空
def test_unknown_event_silently_ignored() -> None:
    app = AgentXTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event({"type": "some.unknown.type", "run_id": "r", "ts": "t"})
    assert appended == []


assert os.environ.get("TEXTUAL_DISABLE_KITTY_KEY") == "1"
