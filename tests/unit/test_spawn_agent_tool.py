from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentx.core.events.bus import EventBus
from agentx.core.llm.types import LlmResponse, UsageStats
from agentx.core.subagent.registry import BackgroundTaskRegistry
from agentx.core.subagent.tool import AgentResultTool, SpawnAgentTool


def _make_provider(result_text: str = "child done") -> Any:
    provider = AsyncMock()
    provider.chat = AsyncMock(
        return_value=LlmResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text=result_text,
            usage=UsageStats(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                context_pct=0.01,
            ),
        )
    )
    return provider


def _make_tool(
    tmp_path: Path,
    provider: Any = None,
    depth: int = 0,
) -> tuple[SpawnAgentTool, BackgroundTaskRegistry, EventBus]:
    bus = EventBus()
    registry = BackgroundTaskRegistry()
    tool = SpawnAgentTool(
        provider=provider or _make_provider(),
        parent_bus=bus,
        parent_run_id="parent-run-01",
        permission_manager=None,
        max_steps=5,
        task_registry=registry,
        runs_dir=tmp_path,
        session_id="sess-test",
        depth=depth,
    )
    return tool, registry, bus


# 功能：前臺模式下 spawn_agent 應阻塞直到子 agent 完成並返回其結果
# 設計：使用返回 end_turn 的 mock provider，驗證 tool_result.content 包含 provider 返回的文字
@pytest.mark.asyncio
async def test_foreground_returns_result(tmp_path: Path) -> None:
    tool, _, _ = _make_tool(tmp_path, _make_provider("analysis complete"))
    result = await tool.invoke({
        "description": "分析程式碼",
        "prompt": "分析 src/ 目錄",
    })
    assert not result.is_error
    assert "analysis complete" in result.content


# 功能：後臺模式應立即返回含 run_id 的訊息，不阻塞等待子 agent
# 設計：run_in_background=true 後驗證返回訊息含 "run_id=" 並且任務登入檔已有對應條目
@pytest.mark.asyncio
async def test_background_returns_run_id(tmp_path: Path) -> None:
    tool, registry, _ = _make_tool(tmp_path)
    result = await tool.invoke({
        "description": "後臺任務",
        "prompt": "做點事",
        "run_in_background": True,
    })
    assert not result.is_error
    assert "run_id=" in result.content
    # extract run_id from message
    run_id = result.content.split("run_id=")[1].split(".")[0]
    assert registry.get(run_id) is not None


# 功能：後臺任務未完成時 agent_result 應返回 "still running"
# 設計：用 Event 阻塞 provider.chat，在未等待任務完成時查詢 agent_result
@pytest.mark.asyncio
async def test_agent_result_pending(tmp_path: Path) -> None:
    event = asyncio.Event()

    async def slow_chat(*args: Any, **kwargs: Any) -> LlmResponse:
        await event.wait()
        return LlmResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text="done",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = slow_chat

    tool, registry, _ = _make_tool(tmp_path, provider)
    spawn_result = await tool.invoke({
        "description": "slow task",
        "prompt": "do something slow",
        "run_in_background": True,
    })
    run_id = spawn_result.content.split("run_id=")[1].split(".")[0]

    result_tool = AgentResultTool(registry)
    result = await result_tool.invoke({"run_id": run_id})
    assert result.content == "still running"
    assert not result.is_error

    event.set()
    await asyncio.sleep(0.05)


# 功能：後臺任務完成後 agent_result 應返回子 agent 的最終文字
# 設計：等待後臺任務 task 完成後呼叫 agent_result，斷言返回內容與 provider 結果一致
@pytest.mark.asyncio
async def test_agent_result_done(tmp_path: Path) -> None:
    tool, registry, _ = _make_tool(tmp_path, _make_provider("final answer"))
    spawn_result = await tool.invoke({
        "description": "bg task",
        "prompt": "do it",
        "run_in_background": True,
    })
    run_id = spawn_result.content.split("run_id=")[1].split(".")[0]

    entry = registry.get(run_id)
    assert entry is not None
    task, _ = entry
    await asyncio.wait_for(task, timeout=5.0)

    result_tool = AgentResultTool(registry)
    result = await result_tool.invoke({"run_id": run_id})
    assert not result.is_error
    assert "final answer" in result.content


# 功能：depth=2 時呼叫 spawn_agent 應返回 is_error=True（巢狀限制）
# 設計：構造 depth=2 的工具，斷言 invoke 直接返回錯誤而不呼叫 provider
@pytest.mark.asyncio
async def test_nesting_limit(tmp_path: Path) -> None:
    provider = _make_provider()
    tool, _, _ = _make_tool(tmp_path, provider, depth=2)
    result = await tool.invoke({
        "description": "nested",
        "prompt": "do nested work",
    })
    assert result.is_error
    assert "nesting limit" in result.content
    provider.chat.assert_not_called()


# 功能：agent_result 查詢不存在的 run_id 應返回 is_error=True
# 設計：空 registry 中查詢隨機 run_id，驗證錯誤訊息含 "Unknown"
@pytest.mark.asyncio
async def test_agent_result_unknown_run_id(tmp_path: Path) -> None:
    registry = BackgroundTaskRegistry()
    tool = AgentResultTool(registry)
    result = await tool.invoke({"run_id": "nonexistent-id"})
    assert result.is_error
    assert "Unknown" in result.content


# 功能：SubagentStartedEvent 應在前臺 spawn 時釋出到父 bus
# 設計：訂閱父 bus 收集所有事件，斷言 subagent.started 出現，且 parent_run_id 和 description 正確
@pytest.mark.asyncio
async def test_foreground_publishes_started_event(tmp_path: Path) -> None:
    from agentx.core.bus.events import SubagentStartedEvent

    tool, _, bus = _make_tool(tmp_path)
    events: list[Any] = []

    async def _collect(e: Any) -> None:
        events.append(e)

    bus.subscribe(_collect)

    await tool.invoke({
        "description": "test task",
        "prompt": "test prompt",
    })
    started = [e for e in events if isinstance(e, SubagentStartedEvent)]
    assert len(started) == 1
    assert started[0].parent_run_id == "parent-run-01"
    assert started[0].description == "test task"
