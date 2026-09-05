from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentx.core.tools.builtin.bash import BashParams
from agentx.core.tools.builtin.list_dir import ListDirParams
from agentx.core.tools.builtin.note_save import NoteSaveParams
from agentx.core.tools.builtin.read_file import ReadFileParams
from agentx.core.tools.builtin.write_file import WriteFileParams


# 功能：驗證 BashParams 接受合法引數，預設 timeout 為 60
# 設計：直接 model_validate 字典，覆蓋必填欄位存在和可選欄位預設值兩種路徑
def test_bash_params_valid() -> None:
    p = BashParams.model_validate({"command": "echo hi"})
    assert p.command == "echo hi"
    assert p.timeout == 60


# 功能：驗證 BashParams timeout 上限被 pydantic le=120 約束
# 設計：傳入 200 預期 ValidationError，確保不需要工具內部手動 min()
def test_bash_params_timeout_clamped() -> None:
    with pytest.raises(ValidationError):
        BashParams.model_validate({"command": "sleep 200", "timeout": 200})


# 功能：驗證 BashParams 缺少 command 時拋 ValidationError
# 設計：傳空字典觸發 required 欄位缺失，覆蓋 schema_error 的核心觸發條件
def test_bash_params_missing_command() -> None:
    with pytest.raises(ValidationError):
        BashParams.model_validate({})


# 功能：驗證 BashParams command 為非字串時拋 ValidationError
# 設計：傳 int 觸發型別校驗，對應 agent 誤傳錯誤型別的情景
def test_bash_params_wrong_type() -> None:
    with pytest.raises(ValidationError):
        BashParams.model_validate({"command": 123})


# 功能：驗證 BashParams 忽略額外欄位（extra="ignore"）
# 設計：LLM 有時會多傳欄位，extra="ignore" 防止 ValidationError，保證魯棒性
def test_bash_params_extra_ignored() -> None:
    p = BashParams.model_validate({"command": "ls", "unknown_field": "x"})
    assert p.command == "ls"


# 功能：驗證 ReadFileParams 接受合法路徑字串
# 設計：最小合法輸入，斷言 path 原樣保留
def test_read_file_params_valid() -> None:
    p = ReadFileParams.model_validate({"path": "README.md"})
    assert p.path == "README.md"


# 功能：驗證 ReadFileParams path 為整數時拋 ValidationError
# 設計：覆蓋 LLM 傳 int 路徑的異常場景，對應 schema_error 分類
def test_read_file_params_wrong_type() -> None:
    with pytest.raises(ValidationError):
        ReadFileParams.model_validate({"path": 42})


# 功能：驗證 WriteFileParams 需要 path 和 content 兩個必填欄位
# 設計：分別缺一個欄位，覆蓋兩個 required 欄位的獨立缺失路徑
def test_write_file_params_missing_fields() -> None:
    with pytest.raises(ValidationError):
        WriteFileParams.model_validate({"path": "out.txt"})  # missing content
    with pytest.raises(ValidationError):
        WriteFileParams.model_validate({"content": "hello"})  # missing path


# 功能：驗證 WriteFileParams 合法輸入原樣保留
# 設計：完整輸入，斷言兩個欄位均正確賦值
def test_write_file_params_valid() -> None:
    p = WriteFileParams.model_validate({"path": "out.txt", "content": "hello"})
    assert p.path == "out.txt"
    assert p.content == "hello"


# 功能：驗證 ListDirParams 全部使用預設值時合法
# 設計：空字典觸發兩個欄位的預設值路徑，斷言 path="." max_depth=2
def test_list_dir_params_defaults() -> None:
    p = ListDirParams.model_validate({})
    assert p.path == "."
    assert p.max_depth == 2


# 功能：驗證 ListDirParams max_depth 超過上限時拋 ValidationError
# 設計：傳 le=4 邊界外的值 5，確保不需要工具內手動 min()
def test_list_dir_params_max_depth_exceeded() -> None:
    with pytest.raises(ValidationError):
        ListDirParams.model_validate({"max_depth": 5})


# 功能：驗證 NoteSaveParams 接受合法 content 字串
# 設計：最小合法輸入，斷言 content 原樣保留
def test_note_save_params_valid() -> None:
    p = NoteSaveParams.model_validate({"content": "Python 3.12"})
    assert p.content == "Python 3.12"


# 功能：驗證 NoteSaveParams 缺少 content 時拋 ValidationError
# 設計：傳空字典觸發 required 欄位缺失，覆蓋空呼叫場景
def test_note_save_params_missing_content() -> None:
    with pytest.raises(ValidationError):
        NoteSaveParams.model_validate({})
