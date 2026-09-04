from __future__ import annotations

import asyncio
import json
import subprocess


# 功能：驗證真實 daemon 響應 core.ping 命令並返回包含版本、uptime、時間戳的 PongResult
# 設計：透過原始 TCP 連線傳送 JSON-RPC 幀（不經過任何 SDK 客戶端層），直接驗證 wire 協議的端到端正確性
async def test_ping_returns_pong(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", free_port)
    req = {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "core.ping",
        "params": {"client": "test/0.0.1"},
    }
    writer.write((json.dumps(req) + "\n").encode())
    await writer.drain()

    line = await asyncio.wait_for(reader.readline(), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    resp = json.loads(line)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "test-1"
    assert "result" in resp
    assert resp["result"]["server_version"] == "0.0.1"
    assert resp["result"]["uptime_ms"] >= 0
    assert "received_at" in resp["result"]


# 功能：驗證呼叫未註冊方法時 daemon 返回 METHOD_NOT_FOUND 錯誤碼（-32601）
# 設計：檢查精確的 JSON-RPC 錯誤碼，確認 SocketServer 的路由失敗路徑符合 JSON-RPC 2.0 規範
async def test_unknown_method_returns_error(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", free_port)
    req = {
        "jsonrpc": "2.0",
        "id": "test-2",
        "method": "core.nonexistent",
        "params": {},
    }
    writer.write((json.dumps(req) + "\n").encode())
    await writer.drain()

    line = await asyncio.wait_for(reader.readline(), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    resp = json.loads(line)
    assert "error" in resp
    assert resp["error"]["code"] == -32601  # METHOD_NOT_FOUND


# 功能：驗證傳送非 JSON 資料時 daemon 返回 PARSE_ERROR（-32700）並不崩潰
# 設計：傳送裸文字而非 JSON，檢查錯誤碼，確認 daemon 對格式錯誤輸入的健壯性（不因單個壞幀終止服務）
async def test_invalid_json_returns_error(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", free_port)
    writer.write(b"not valid json\n")
    await writer.drain()

    line = await asyncio.wait_for(reader.readline(), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    resp = json.loads(line)
    assert "error" in resp
    assert resp["error"]["code"] == -32700  # PARSE_ERROR
