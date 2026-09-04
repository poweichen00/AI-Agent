from __future__ import annotations

import pytest
from pydantic import ValidationError

from kama_claude.core.bus.envelope import (
    PARSE_ERROR,
    JsonRpcRequest,
    JsonRpcSuccess,
    make_error,
)


# 功能：驗證 JsonRpcRequest 序列化後再反序列化，所有欄位值完整保留
# 設計：JSON 往返（model_dump_json → model_validate_json）確認欄位完整性，這是 NDJSON wire 協議的基本契約
def test_request_roundtrip() -> None:
    req = JsonRpcRequest(id="1", method="core.ping", params={"client": "test"})
    req2 = JsonRpcRequest.model_validate_json(req.model_dump_json())
    assert req2.id == "1"
    assert req2.method == "core.ping"
    assert req2.params == {"client": "test"}


# 功能：驗證 params 欄位的預設值為空字典而非 None
# 設計：不傳 params 引數例項化，確認預設值為 {}，避免 SocketServer handler 對 params 做 None 判斷
def test_request_default_params() -> None:
    req = JsonRpcRequest(id="1", method="x")
    assert req.params == {}


# 功能：驗證缺少必填 id 欄位時 pydantic 校驗失敗
# 設計：傳入無 id 的 dict，確認 id 是必填欄位，防止無 id 請求繞過 JSON-RPC 格式校驗進入 handler
def test_request_missing_id_raises() -> None:
    with pytest.raises(ValidationError):
        JsonRpcRequest.model_validate({"jsonrpc": "2.0", "method": "x"})


# 功能：驗證 jsonrpc 欄位非 "2.0" 時 pydantic 校驗失敗
# 設計：傳入 "1.0" 確認 Literal["2.0"] 約束生效，jsonrpc 版本欄位是協議相容性的守門員
def test_request_wrong_version_raises() -> None:
    with pytest.raises(ValidationError):
        JsonRpcRequest.model_validate({"jsonrpc": "1.0", "id": "1", "method": "x"})


# 功能：驗證 JsonRpcSuccess 序列化往返後 result 欄位（Any 型別）保持原始巢狀結構
# 設計：result 是 Any 型別，往返測試確認巢狀 dict 不被丟棄或扁平化
def test_success_roundtrip() -> None:
    resp = JsonRpcSuccess(id="1", result={"key": "value"})
    resp2 = JsonRpcSuccess.model_validate_json(resp.model_dump_json())
    assert resp2.id == "1"
    assert resp2.result == {"key": "value"}


# 功能：驗證 make_error 工廠函式正確設定 code、id 欄位，data 預設為 None
# 設計：傳入具名錯誤碼常量（PARSE_ERROR），確認工廠函式不改變錯誤碼值，同時驗證 data=None 的預設行為
def test_make_error_sets_code() -> None:
    err = make_error("1", PARSE_ERROR, "Parse error")
    assert err.error.code == PARSE_ERROR
    assert err.id == "1"
    assert err.error.data is None


# 功能：驗證 make_error 接受 None id（對應無法解析請求 id 時的錯誤響應）
# 設計：JSON-RPC 規範在無法解析 id 時允許 id=null，確認 pydantic 模型的 id: str | None 約束正確建模
def test_make_error_null_id() -> None:
    err = make_error(None, PARSE_ERROR, "bad json")
    assert err.id is None
