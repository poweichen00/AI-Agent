from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from agentx.core.transport.socket_client import IpcError, SocketClient


async def _start_mock_server(
    handler: Any,
) -> tuple[asyncio.Server, int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port: int = server.sockets[0].getsockname()[1]
    return server, port


# 功能：驗證 send_command 向 mock server 傳送 JSON-RPC 請求並正確解析響應 result
# 設計：用 asyncio.start_server + port 0 啟動記憶體中的 mock server，避免依賴真實 daemon；
#       loop_task 併發執行 run_event_loop，使 send_command 的 future 能被 _dispatch 解析
async def test_send_command_returns_result() -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        req = json.loads(line)
        resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"pong": True}}
        writer.write(json.dumps(resp).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server, port = await _start_mock_server(handle)
    async with server:
        client = SocketClient("127.0.0.1", port)
        await client.connect()
        loop_task = asyncio.create_task(client.run_event_loop())

        result = await asyncio.wait_for(
            client.send_command("core.ping", {"client": "test"}),
            timeout=2.0,
        )
        assert result == {"pong": True}

        await loop_task
        await client.close()


# 功能：驗證 server 返回 JSON-RPC error 時 send_command 丟擲 IpcError 並攜帶正確錯誤碼
# 設計：mock server 返回 error 物件（code=-32601），斷言異常型別和 code 屬性，確認客戶端的錯誤路徑處理
async def test_send_command_raises_ipc_error() -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        req = json.loads(line)
        resp = {
            "jsonrpc": "2.0",
            "id": req["id"],
            "error": {"code": -32601, "message": "Method not found"},
        }
        writer.write(json.dumps(resp).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server, port = await _start_mock_server(handle)
    async with server:
        client = SocketClient("127.0.0.1", port)
        await client.connect()
        loop_task = asyncio.create_task(client.run_event_loop())

        with pytest.raises(IpcError) as exc_info:
            await asyncio.wait_for(
                client.send_command("core.nope", {}),
                timeout=2.0,
            )
        assert exc_info.value.code == -32601

        await loop_task
        await client.close()


# 功能：驗證 server 推送 kind=event 的訊息時，on_event 註冊的 handler 能收到 event 字典
# 設計：server 先返回 RPC 響應（解除 send_command 的等待），再推送事件；用 asyncio.Event 等待 handler 被呼叫，
#       避免 sleep 輪詢；斷言 event 內容中的 type 欄位是否正確
async def test_event_push_routed_to_handler() -> None:
    received_events: list[dict[str, Any]] = []
    push_done = asyncio.Event()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        req = json.loads(line)
        resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"subscription_id": "sub-1"}}
        writer.write(json.dumps(resp).encode() + b"\n")
        push = {"kind": "event", "event": {"type": "run.started", "run_id": "r1"}}
        writer.write(json.dumps(push).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server, port = await _start_mock_server(handle)
    async with server:
        client = SocketClient("127.0.0.1", port)

        async def collect(event_data: dict[str, Any]) -> None:
            received_events.append(event_data)
            push_done.set()

        client.on_event(collect)
        await client.connect()
        loop_task = asyncio.create_task(client.run_event_loop())

        await asyncio.wait_for(
            client.send_command("event.subscribe", {"topics": ["run.*"]}),
            timeout=2.0,
        )
        await asyncio.wait_for(push_done.wait(), timeout=2.0)

        assert len(received_events) == 1
        assert received_events[0]["type"] == "run.started"

        await loop_task
        await client.close()


# 功能：驗證 server 關閉連線後 run_event_loop 正常退出（不掛起）
# 設計：mock server 立即關閉寫流，client readline 收到空位元組後退出迴圈；
#       用 asyncio.wait_for 設定超時，防止 loop 意外掛起導致測試卡死
async def test_run_event_loop_exits_on_server_close() -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()
        await writer.wait_closed()

    server, port = await _start_mock_server(handle)
    async with server:
        client = SocketClient("127.0.0.1", port)
        await client.connect()
        await asyncio.wait_for(client.run_event_loop(), timeout=2.0)
        await client.close()
