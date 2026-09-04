from __future__ import annotations

import asyncio
import json
import subprocess


# 傳送一條 JSON-RPC 請求並返回響應物件
async def _send_recv(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    method: str,
    params: dict,
    req_id: str = "1",
) -> dict:
    req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    writer.write((json.dumps(req) + "\n").encode())
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=5.0)
    return json.loads(line)


# 功能：驗證 daemon 暴露 session.create、session.get_history、session.close 三個 S4 IPC 命令
# 設計：不觸發 session.send_message，避免真實 LLM 依賴；只驗證 CoreApp handler 註冊、協議序列化和 session 狀態持久化
async def test_session_create_history_close_over_ipc(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", free_port)

    created = await _send_recv(
        reader,
        writer,
        "session.create",
        {"mode": "chat", "title": "ipc test"},
        req_id="create",
    )
    assert "result" in created, created
    session_id = created["result"]["session_id"]
    assert created["result"]["status"] == "active"

    history = await _send_recv(
        reader,
        writer,
        "session.get_history",
        {"session_id": session_id},
        req_id="history",
    )
    assert history["result"]["messages"] == []

    closed = await _send_recv(
        reader,
        writer,
        "session.close",
        {"session_id": session_id},
        req_id="close",
    )
    assert closed["result"]["status"] == "closed"

    writer.close()
    await writer.wait_closed()
