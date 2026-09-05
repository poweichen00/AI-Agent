from __future__ import annotations

from pathlib import Path

import pytest

from agentx.core.tools.builtin.bash import BashTool
from agentx.core.tools.builtin.list_dir import ListDirTool
from agentx.core.tools.builtin.write_file import WriteFileTool

# ── bash ──────────────────────────────────────────────────────────────────────

# 功能：驗證成功命令的 stdout 出現在 ToolResult.content 中，is_error 為 False
# 設計：用 echo 命令避免外部依賴，直接比較輸出內容，無需 mock
@pytest.mark.asyncio
async def test_bash_success_stdout() -> None:
    result = await BashTool().invoke({"command": "echo hello"})
    assert not result.is_error
    assert "hello" in result.content


# 功能：驗證非零退出碼時 is_error=True 且 content 包含退出碼標註
# 設計：`exit 2` 是最簡單的非零退出；不依賴任何外部命令列為
@pytest.mark.asyncio
async def test_bash_nonzero_exit_is_error() -> None:
    result = await BashTool().invoke({"command": "exit 2"})
    assert result.is_error
    assert "[exit 2]" in result.content


# 功能：驗證命令超時後 is_error=True，error_type 為 "timeout"
# 設計：timeout=1s 搭配 sleep 2 必然超時；驗證 error_type 而非 content，避免超時訊息格式耦合
@pytest.mark.asyncio
async def test_bash_timeout() -> None:
    result = await BashTool().invoke({"command": "sleep 5", "timeout": 1})
    assert result.is_error
    assert result.error_type == "timeout"


# 功能：驗證 stderr 被合併到 stdout 輸出中
# 設計：只寫 stderr 的命令（>&2 echo），輸出應該出現在合併後的 content 裡
@pytest.mark.asyncio
async def test_bash_stderr_merged() -> None:
    result = await BashTool().invoke({"command": "echo err >&2"})
    assert not result.is_error
    assert "err" in result.content


# ── write_file ────────────────────────────────────────────────────────────────

# 功能：驗證 write_file 寫入檔案後內容可以被讀取，返回位元組數
# 設計：寫入臨時目錄，斷言檔案存在且內容一致；用 tmp_path fixture 自動清理
@pytest.mark.asyncio
async def test_write_file_creates_and_returns_size(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    result = await WriteFileTool().invoke(
        {"path": str(target), "content": "hello world"}
    )
    assert not result.is_error
    assert "11" in result.content  # "hello world" = 11 bytes
    assert target.read_text() == "hello world"


# 功能：驗證 write_file 自動建立不存在的父目錄
# 設計：路徑包含兩層不存在的子目錄，確認寫入後目錄結構被建立
@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "file.txt"
    result = await WriteFileTool().invoke({"path": str(target), "content": "x"})
    assert not result.is_error
    assert target.exists()


# 功能：驗證 write_file 拒絕包含 .. 的路徑並丟擲 PermissionError
# 設計：.. 路徑遍歷與 read_file 遵循相同規則，用相同的斷言模式保持一致性
@pytest.mark.asyncio
async def test_write_file_rejects_traversal() -> None:
    with pytest.raises(PermissionError):
        await WriteFileTool().invoke({"path": "../secret.txt", "content": "x"})


# ── list_dir ──────────────────────────────────────────────────────────────────

# 功能：驗證 list_dir 輸出包含目錄中的檔名
# 設計：在 tmp_path 建立已知結構，斷言檔名出現在 content 中；不約束格式細節
@pytest.mark.asyncio
async def test_list_dir_shows_files(tmp_path: Path) -> None:
    (tmp_path / "foo.py").write_text("x")
    (tmp_path / "bar.md").write_text("y")
    result = await ListDirTool().invoke({"path": str(tmp_path)})
    assert not result.is_error
    assert "foo.py" in result.content
    assert "bar.md" in result.content


# 功能：驗證 list_dir 按 max_depth 限制遞迴深度（depth=1 時不展示孫級目錄內容）
# 設計：建立 parent/child/grandchild 三層，depth=1 時 grandchild 不應出現在輸出中
@pytest.mark.asyncio
async def test_list_dir_respects_max_depth(tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    grandchild = child / "grandchild"
    grandchild.mkdir()
    (grandchild / "deep.txt").write_text("x")

    result = await ListDirTool().invoke({"path": str(tmp_path), "max_depth": 1})
    assert not result.is_error
    assert "child" in result.content
    assert "deep.txt" not in result.content


# 功能：驗證對不存在的路徑 list_dir 丟擲 FileNotFoundError
# 設計：直接傳入不存在的路徑字串，預期丟擲標準異常（invocation.py 捕獲後返回 error ToolResult）
@pytest.mark.asyncio
async def test_list_dir_missing_path_raises() -> None:
    with pytest.raises(FileNotFoundError):
        await ListDirTool().invoke({"path": "/this/does/not/exist"})


# 功能：驗證 list_dir 拒絕包含 .. 的路徑
# 設計：與 read_file 和 write_file 保持一致的安全規則
@pytest.mark.asyncio
async def test_list_dir_rejects_traversal() -> None:
    with pytest.raises(PermissionError):
        await ListDirTool().invoke({"path": "../"})
