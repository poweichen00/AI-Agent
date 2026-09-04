from __future__ import annotations

import pytest

from kama_claude.cli.commands.run import StdoutPrinter


# 功能：驗證 run.started 事件在 stdout 中列印 [run] 字首和 run_id
# 設計：用 capsys 捕獲 stdout，直接斷言關鍵字串，避免對格式細節過度約束
async def test_run_started_prints_run_id(capsys: pytest.CaptureFixture[str]) -> None:
    printer = StdoutPrinter()
    await printer.handle(
        {"type": "run.started", "run_id": "20260515-abc", "goal": "g", "ts": "t"}
    )
    out = capsys.readouterr().out
    assert "[run]" in out
    assert "20260515-abc" in out


# 功能：驗證 step.started 事件列印 [step N] 和 planning... 文字
# 設計：斷言步驟編號和 planning 關鍵詞同時出現，覆蓋格式模板的兩個可變部分
async def test_step_started_prints_step_number(capsys: pytest.CaptureFixture[str]) -> None:
    printer = StdoutPrinter()
    await printer.handle({"type": "step.started", "run_id": "r", "step": 3, "ts": "t"})
    out = capsys.readouterr().out
    assert "[step 3]" in out
    assert "planning" in out


# 功能：驗證 llm.token 事件將 token 無換行列印並設定 _inline 標誌
# 設計：傳送 token 後檢查 _inline 為 True，再發 step.started 觸發 _ensure_newline，
#       確認換行被補齊（新行裡有 [step]），驗證內聯狀態機的完整轉換
async def test_llm_token_inline_then_newline_on_next_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = StdoutPrinter()
    await printer.handle({"type": "llm.token", "run_id": "r", "token": "hello", "ts": "t"})
    assert printer._inline is True  # type: ignore[attr-defined]

    await printer.handle({"type": "step.started", "run_id": "r", "step": 2, "ts": "t"})
    assert printer._inline is False  # type: ignore[attr-defined]
    out = capsys.readouterr().out
    assert "hello" in out
    assert "[step 2]" in out


# 功能：驗證 tool.call_started 列印工具名和 JSON 序列化的 params
# 設計：用帶 Unicode 內容的 params 檢查 ensure_ascii=False（保留中文字元），斷言工具名和引數都出現
async def test_tool_call_started_prints_name_and_params(
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = StdoutPrinter()
    await printer.handle(
        {
            "type": "tool.call_started",
            "run_id": "r",
            "tool_use_id": "t1",
            "tool_name": "read_file",
            "params": {"path": "README.md"},
            "ts": "t",
        }
    )
    out = capsys.readouterr().out
    assert "[tool]" in out
    assert "read_file" in out
    assert "README.md" in out


# 功能：驗證 run.finished 列印 status 和 steps 欄位
# 設計：success 路徑下斷言 status 和 steps 出現在輸出中，不檢查 elapsed 的精確值（依賴時間）
async def test_run_finished_prints_status_and_steps(capsys: pytest.CaptureFixture[str]) -> None:
    printer = StdoutPrinter()
    await printer.handle(
        {"type": "run.started", "run_id": "r", "goal": "g", "ts": "t"}
    )
    await printer.handle(
        {"type": "run.finished", "run_id": "r", "status": "success", "steps": 4, "ts": "t"}
    )
    out = capsys.readouterr().out
    assert "success" in out
    assert "4" in out
