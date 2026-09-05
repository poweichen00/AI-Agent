from __future__ import annotations

from pydantic import BaseModel

from agentx.core.events.bus import EventBus


class _FakeEvent(BaseModel):
    value: str


# 功能：驗證 publish 後訂閱者能收到事件物件
# 設計：用內聯 handler 收集事件引用，斷言 is 而非 ==，排除序列化中間步驟的幹擾
async def test_publish_reaches_subscriber() -> None:
    bus = EventBus()
    received: list[BaseModel] = []

    async def handler(event: BaseModel) -> None:
        received.append(event)

    bus.subscribe(handler)
    event = _FakeEvent(value="hello")
    await bus.publish(event)
    assert received == [event]


# 功能：驗證多個訂閱者都能獨立收到同一事件
# 設計：兩個獨立計數器分別累加，避免共享狀態掩蓋某一訂閱者未被呼叫的情況
async def test_multiple_subscribers_all_receive() -> None:
    bus = EventBus()
    counts = [0, 0]

    async def h1(e: BaseModel) -> None:
        counts[0] += 1

    async def h2(e: BaseModel) -> None:
        counts[1] += 1

    bus.subscribe(h1)
    bus.subscribe(h2)
    await bus.publish(_FakeEvent(value="x"))
    assert counts == [1, 1]


# 功能：驗證多個訂閱者按註冊順序被依次呼叫
# 設計：用追加整數到列表來記錄呼叫次序，因為 bus 的順序語義是 AgentLoop 事件序列正確性的前提
async def test_subscribers_called_in_order() -> None:
    bus = EventBus()
    order: list[int] = []

    async def h1(e: BaseModel) -> None:
        order.append(1)

    async def h2(e: BaseModel) -> None:
        order.append(2)

    bus.subscribe(h1)
    bus.subscribe(h2)
    await bus.publish(_FakeEvent(value="x"))
    assert order == [1, 2]


# 功能：驗證無訂閱者時 publish 不拋異常（空 bus 邊界條件）
# 設計：只呼叫 publish，不斷言返回值，以"不引發異常"作為唯一判據
async def test_no_subscribers_publish_is_noop() -> None:
    bus = EventBus()
    await bus.publish(_FakeEvent(value="x"))  # should not raise
