from __future__ import annotations

from pathlib import Path

import pytest

from kama_claude.core.memory.loader import load_context_file


# 功能：驗證檔案存在時返回去除首尾空格的完整內容
# 設計：用 tmp_path 寫入帶前後空白行的檔案，斷言 strip 後內容一致
def test_load_existing_file(tmp_path: Path) -> None:
    ctx = tmp_path / "context.md"
    ctx.write_text("  # My Context\n- item one\n", encoding="utf-8")
    result = load_context_file(ctx)
    assert result == "# My Context\n- item one"


# 功能：驗證檔案不存在時返回空字串
# 設計：傳入不存在的路徑，無需建立檔案，斷言返回值為空字串
def test_load_missing_file(tmp_path: Path) -> None:
    result = load_context_file(tmp_path / "nonexistent.md")
    assert result == ""


# 功能：驗證檔案存在但內容為空（或僅空白）時返回空字串
# 設計：寫入純空白內容，strip 後為空，斷言返回空字串
def test_load_empty_file(tmp_path: Path) -> None:
    ctx = tmp_path / "context.md"
    ctx.write_text("   \n\n  ", encoding="utf-8")
    result = load_context_file(ctx)
    assert result == ""
