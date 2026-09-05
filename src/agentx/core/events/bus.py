from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

type EventHandler = Callable[[BaseModel], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []

    # 註冊一個事件處理函式
    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler)

    # 按註冊順序依次呼叫所有訂閱者
    async def publish(self, event: BaseModel) -> None:
        for handler in self._subscribers:
            await handler(event)
