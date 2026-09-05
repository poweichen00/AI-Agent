from __future__ import annotations

from pathlib import Path

import pytest

from agentx.core.tools.builtin.read_file import ReadFileTool


# 功能：驗證讀取存在的檔案時返回完整內容且 is_error 為 False
# 設計：寫臨時檔案後讀取，斷言 content 和 is_error，覆蓋正常路徑（happy path）
async def test_read_existing_file(tmp_path: Path) -> None:
    f = tmp_path / "hello.txt"
    f.write_text("hello world", encoding="utf-8")
    result = await ReadFileTool().invoke({"path": str(f)})
    assert not result.is_error
    assert result.content == "hello world"


# 功能：驗證檔案不存在時丟擲 FileNotFoundError 而非返回錯誤 ToolResult
# 設計：傳入不存在的路徑，確認 ReadFileTool 不吞掉異常，讓呼叫方（invoke_tool）負責錯誤分類和事件釋出
async def test_file_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await ReadFileTool().invoke({"path": str(tmp_path / "missing.txt")})


# 功能：驗證包含 `..` 的路徑被拒絕並丟擲 PermissionError
# 設計：傳入 `"../secret.txt"` 這種最典型的目錄遍歷形式，確認安全邊界第一道防線有效
async def test_path_traversal_dotdot_raises() -> None:
    with pytest.raises(PermissionError):
        await ReadFileTool().invoke({"path": "../secret.txt"})


# 功能：驗證多級路徑中嵌入的 `..` 經過路徑規範化後也被正確檢測
# 設計：使用 `"subdir/../../etc/passwd"` 測試路徑 resolve 後的深度遍歷，確認單層 `..` 過濾不足以覆蓋此情況
async def test_path_traversal_nested_raises() -> None:
    with pytest.raises(PermissionError):
        await ReadFileTool().invoke({"path": "subdir/../../etc/passwd"})


# 功能：驗證超過 512KB 的檔案被截斷並在末尾追加 [truncated] 標記
# 設計：寫 600KB 檔案，斷言內容以 x×512KB 開頭、以 [truncated] 結尾，確認截斷不破壞字首內容
async def test_truncation_over_512kb(tmp_path: Path) -> None:
    f = tmp_path / "big.txt"
    f.write_bytes(b"x" * (600 * 1024))
    result = await ReadFileTool().invoke({"path": str(f)})
    assert not result.is_error
    assert result.content.endswith("[truncated]")
    # Actual text content is exactly 512KB worth of 'x' chars
    assert result.content.startswith("x" * (512 * 1024))


# 功能：驗證恰好等於 512KB 的檔案不被截斷（邊界值：超過而非大於等於）
# 設計：boundary check，確認截斷閾值為"嚴格超過 512KB"，防止 off-by-one 錯誤
async def test_exact_512kb_is_not_truncated(tmp_path: Path) -> None:
    f = tmp_path / "exact.txt"
    f.write_bytes(b"y" * (512 * 1024))
    result = await ReadFileTool().invoke({"path": str(f)})
    assert not result.is_error
    assert not result.content.endswith("[truncated]")
    assert len(result.content) == 512 * 1024


# 功能：驗證空檔案返回空字串而非 None 或錯誤
# 設計：零位元組檔案確認 content="" 的正常返回，避免呼叫方（LLM prompt 組裝）對空內容做額外 None 判斷
async def test_empty_file_returns_empty_content(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    result = await ReadFileTool().invoke({"path": str(f)})
    assert not result.is_error
    assert result.content == ""
