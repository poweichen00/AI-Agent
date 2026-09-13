from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from agentx.core.context import ExecutionContext
from agentx.core.events.bus import EventBus
from agentx.core.llm.types import LlmResponse, ToolCallBlock
from agentx.core.loop import AgentLoop
from agentx.core.tools.base import BaseTool, ToolResult
from agentx.core.tools.registry import ToolRegistry

# --- stubs -------------------------------------------------------------------


class _MockProvider:
    """Returns canned responses in order; raises exc immediately if given."""

    def __init__(
        self,
        responses: list[LlmResponse],
        exc: BaseException | None = None,
    ) -> None:
        self._responses = iter(responses)
        self._exc = exc

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        if self._exc is not None:
            raise self._exc
        return next(self._responses)


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes msg"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content=str(params["msg"]))


class _FailTool(BaseTool):
    name = "fail"
    description = "Always raises"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        raise RuntimeError("tool error")


# --- helpers -----------------------------------------------------------------


def _ctx(max_steps: int = 5) -> ExecutionContext:
    return ExecutionContext(run_id="r1", goal="test goal", max_steps=max_steps)


def _tc(name: str = "echo", inp: dict[str, object] | None = None, uid: str = "t1") -> ToolCallBlock:
    return ToolCallBlock(id=uid, name=name, input=inp or {"msg": "hi"})


def _make_loop(
    provider: _MockProvider,
    registry: ToolRegistry | None = None,
    bus: EventBus | None = None,
) -> tuple[AgentLoop, EventBus]:
    b = bus or EventBus()
    return AgentLoop(provider, registry or ToolRegistry(), b), b  # type: ignore[arg-type]


async def _events(bus: EventBus) -> list[BaseModel]:
    collected: list[BaseModel] = []

    async def _h(e: BaseModel) -> None:
        collected.append(e)

    bus.subscribe(_h)
    return collected


# --- tests -------------------------------------------------------------------


# 功能：驗證 LLM 返回 end_turn 時 loop 將 context 標記為 success
# 設計：單步 provider 直接返回 end_turn，最簡正常路徑，確認 loop 的基本終止邏輯
async def test_end_turn_marks_success() -> None:
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="done")])
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 1


# 功能：驗證達到 max_steps 時 loop 以 exceeded_max_steps 原因將 context 標記為 failed
# 設計：設定 max_steps=2 + 無限 tool_use provider，同時驗證 step 數量和失敗原因，確認計數器與終止邏輯聯動正確
async def test_max_steps_marks_failed() -> None:
    tc = _tc("unknown", {})
    provider = _MockProvider([LlmResponse(stop_reason="tool_use", tool_calls=[tc])] * 10)
    loop, _ = _make_loop(provider)
    ctx = _ctx(max_steps=2)
    await loop.run(ctx)
    assert ctx.status == "failed"
    assert ctx.reason == "exceeded_max_steps"
    assert ctx.step == 2


# 功能：驗證"調工具 → end_turn"的兩步路徑最終標記為 success
# 設計：provider 返回 [tool_use, end_turn] 序列，註冊真實 EchoTool，覆蓋最常見的正常工作路徑
async def test_tool_use_then_end_turn_marks_success() -> None:
    provider = _MockProvider(
        [
            LlmResponse(stop_reason="tool_use", tool_calls=[_tc()]),
            LlmResponse(stop_reason="end_turn", text="summary"),
        ]
    )
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 2


# 功能：驗證工具結果按 Anthropic 格式（tool_result user 訊息）追加到訊息歷史
# 設計：檢查 messages[2]（tool_result 所在位置），斷言 tool_use_id 和 content，確認 loop 正確呼叫了 context.add_tool_result
async def test_tool_result_appended_to_context() -> None:
    provider = _MockProvider(
        [
            LlmResponse(stop_reason="tool_use", tool_calls=[_tc(inp={"msg": "hello"})]),
            LlmResponse(stop_reason="end_turn"),
        ]
    )
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    # messages: [goal, assistant(tool_use), user(tool_result), assistant(end_turn)]
    tool_result_msg = ctx.messages[2]
    assert tool_result_msg["role"] == "user"
    block = tool_result_msg["content"][0]  # type: ignore[index]
    assert block["tool_use_id"] == "t1"
    assert block["content"] == "hello"


# 功能：驗證工具失敗時 loop 不終止，而是將錯誤追加上下文讓 LLM 重新決策
# 設計：工具始終 raise + provider 第二步返回 end_turn，確認 loop 最終到達 success；這是 agent 區別於普通指令碼的核心特性
async def test_tool_failure_loop_continues_to_success() -> None:
    provider = _MockProvider(
        [
            LlmResponse(stop_reason="tool_use", tool_calls=[_tc("fail", {})]),
            LlmResponse(stop_reason="end_turn", text="handled error"),
        ]
    )
    registry = ToolRegistry()
    registry.register(_FailTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 2


# 功能：驗證工具失敗的錯誤資訊以 is_error=True 追加進上下文，讓 LLM 能感知工具呼叫失敗
# 設計：檢查 tool_result block 中的 is_error 標記，與 test_tool_failure_loop_continues_to_success 互補
async def test_tool_failure_result_is_error_in_context() -> None:
    provider = _MockProvider(
        [
            LlmResponse(stop_reason="tool_use", tool_calls=[_tc("fail", {})]),
            LlmResponse(stop_reason="end_turn"),
        ]
    )
    registry = ToolRegistry()
    registry.register(_FailTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    tool_result_msg = ctx.messages[2]
    block = tool_result_msg["content"][0]  # type: ignore[index]
    assert block.get("is_error") is True


# 功能：驗證收到 CancelledError 時 loop 將 context 標記為 cancelled 後繼續上拋 CancelledError
# 設計：用 pytest.raises 捕獲 CancelledError，同時檢查 context.status，確認優雅退出行為：先記錄狀態，再傳播取消訊號
async def test_cancelled_error_marks_failed_and_reraises() -> None:
    provider = _MockProvider([], exc=asyncio.CancelledError())
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    with pytest.raises(asyncio.CancelledError):
        await loop.run(ctx)
    assert ctx.status == "failed"
    assert ctx.reason == "cancelled"


# 功能：驗證 LLM 呼叫異常被捕獲並標記為 llm_error，不向上傳播
# 設計：provider 拋 RuntimeError，確認 loop 不崩潰、context 狀態為 failed/llm_error，異常被正確吸收
async def test_llm_api_error_marks_failed() -> None:
    provider = _MockProvider([], exc=RuntimeError("api error"))
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "failed"
    assert ctx.reason == "llm_error"


# 功能：驗證每個步驟都發布 step.started 和 step.finished 事件
# 設計：注入 bus + 事件收集器，檢查事件型別集合，確認步驟級事件的可觀測性（S2 TUI 依賴這兩個事件顯示進度）
async def test_step_started_and_finished_events_published() -> None:
    bus = EventBus()
    events = await _events(bus)
    provider = _MockProvider([LlmResponse(stop_reason="end_turn")])
    loop, _ = _make_loop(provider, bus=bus)
    ctx = _ctx()
    await loop.run(ctx)
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "step.started" in types
    assert "step.finished" in types


# 功能：驗證多步執行後 step 計數器正確累積到步數總量
# 設計：三步序列 [tool_use, tool_use, end_turn]，確認 step==3，排除計數器初始化錯誤或某步未遞增的情況
async def test_step_counter_increments_across_steps() -> None:
    provider = _MockProvider(
        [
            LlmResponse(stop_reason="tool_use", tool_calls=[_tc()]),
            LlmResponse(stop_reason="tool_use", tool_calls=[_tc()]),
            LlmResponse(stop_reason="end_turn"),
        ]
    )
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.step == 3
    assert ctx.status == "success"


# 功能：驗證 LLM 文字響應以正確的 content block 格式追加到訊息歷史
# 設計：檢查 messages[1] 的 role 和 content block 結構，確認 loop 構造的 assistant 訊息符合 Anthropic 格式
async def test_assistant_message_blocks_added_to_context() -> None:
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="answer")])
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    await loop.run(ctx)
    assistant_msg = ctx.messages[1]
    assert assistant_msg["role"] == "assistant"
    blocks = assistant_msg["content"]
    assert blocks[0]["type"] == "text"  # type: ignore[index]
    assert blocks[0]["text"] == "answer"  # type: ignore[index]
