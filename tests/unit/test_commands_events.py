from __future__ import annotations

import pytest
from pydantic import ValidationError

from kama_claude.core.bus.commands import PingCommand, PongResult
from kama_claude.core.bus.events import CoreStartedEvent


# 功能：驗證 PingCommand 序列化後再反序列化，client 和 type 欄位完整保留
# 設計：JSON 往返測試確認 wire 協議的序列化正確性，type 欄位是 discriminated union 的判別鍵
def test_ping_command_roundtrip() -> None:
    cmd = PingCommand(client="cli/0.0.1")
    cmd2 = PingCommand.model_validate_json(cmd.model_dump_json())
    assert cmd2.client == "cli/0.0.1"
    assert cmd2.type == "core.ping"


# 功能：驗證 PingCommand 的 type 欄位預設值為 "core.ping"
# 設計：Literal 預設值測試，type 是 Command union 的判別鍵，必須與 union 定義完全一致，否則反序列化時會路由到錯誤型別
def test_ping_command_default_type() -> None:
    cmd = PingCommand(client="x")
    assert cmd.type == "core.ping"


# 功能：驗證缺少必填 client 欄位時 pydantic 校驗失敗
# 設計：傳入空 dict 觸發校驗，確認 client 是必填欄位，防止 daemon 收到不完整的 ping 命令進入 handler
def test_ping_command_missing_client_raises() -> None:
    with pytest.raises(ValidationError):
        PingCommand.model_validate({})


# 功能：驗證 PongResult 序列化往返後所有欄位完整保留
# 設計：與 PingCommand 對稱，測試命令-響應對的兩端序列化，確認 int 和 str 欄位型別在往返中不變
def test_pong_result_roundtrip() -> None:
    pong = PongResult(server_version="0.0.1", uptime_ms=42, received_at="2026-05-11T00:00:00Z")
    pong2 = PongResult.model_validate(pong.model_dump())
    assert pong2.server_version == "0.0.1"
    assert pong2.uptime_ms == 42


# 功能：驗證 CoreStartedEvent 序列化往返後 listen_addr 和 type 欄位正確保留
# 設計：CoreStartedEvent 是 daemon 啟動通知，往返測試確認 type 的 Literal 約束在反序列化後保持（不被欄位名覆蓋）
def test_core_started_event_roundtrip() -> None:
    evt = CoreStartedEvent(listen_addr="127.0.0.1:7437", version="0.0.1")
    evt2 = CoreStartedEvent.model_validate_json(evt.model_dump_json())
    assert evt2.listen_addr == "127.0.0.1:7437"
    assert evt2.type == "core.started"
