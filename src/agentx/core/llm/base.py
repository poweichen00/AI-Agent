from __future__ import annotations

from typing import Protocol

from agentx.core.events.bus import EventBus
from agentx.core.llm.types import LlmResponse


class LLMProvider(Protocol):
    # 流式呼叫 LLM 併發布進度事件，返回完整響應
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse: ...
