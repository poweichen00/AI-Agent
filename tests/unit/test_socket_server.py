from __future__ import annotations

import asyncio
import socket

from kama_claude.core.transport.socket_server import SocketServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# 功能：驗證客戶端斷開後 SocketServer 呼叫 broadcaster.unsubscribe(writer) 清理訂閱
# 設計：用內聯 MockBroadcaster 捕獲 unsubscribe 呼叫並設定 asyncio.Event，避免 sleep 輪詢；
#       等待 Event 而非斷言呼叫次數，確保時序正確性而不依賴競態假設
async def test_broadcaster_unsubscribe_called_on_disconnect() -> None:
    unsubscribed = asyncio.Event()

    class MockBroadcaster:
        def unsubscribe(self, writer: object) -> None:
            unsubscribed.set()

    port = _free_port()
    server = SocketServer("127.0.0.1", port, broadcaster=MockBroadcaster())  # type: ignore[arg-type]
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        await writer.wait_closed()

        await asyncio.wait_for(unsubscribed.wait(), timeout=2.0)
    finally:
        await server.stop()


# 功能：驗證不傳入 broadcaster 時 SocketServer 仍可正常啟動和停止（backward-compatible 預設值）
# 設計：直接例項化 SocketServer(host, port)（無 broadcaster），start/stop 不拋異常即為透過；
#       迴歸測試確保新引數的預設值 None 不破壞現有呼叫方
async def test_no_broadcaster_server_starts_and_stops() -> None:
    port = _free_port()
    server = SocketServer("127.0.0.1", port)
    await server.start()
    await server.stop()
