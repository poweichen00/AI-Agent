"""
S5 permission flow integration tests.

No daemon subprocess needed — uses AgentRunner in-process with a mock LLM
provider and the real PermissionManager. BashTool runs real subprocesses, so
commands must be safe (echo, true).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from agentx.core.config import AgentXConfig
from agentx.core.events.bus import EventBus
from agentx.core.llm.types import LlmResponse, ToolCallBlock
from agentx.core.permissions.manager import PermissionManager
from agentx.core.runner import AgentRunner

# ── stub providers ────────────────────────────────────────────────────────────


class _SingleBashProvider:
    """Step 1: bash tool call. Step 2: end_turn."""

    def __init__(self, command: str = "echo hello") -> None:
        self._command = command
        self._step = 0

    async def chat(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        self._step += 1
        if self._step == 1:
            tc = ToolCallBlock(id="tc1", name="bash", input={"command": self._command})
            return LlmResponse(stop_reason="tool_use", tool_calls=[tc])
        return LlmResponse(stop_reason="end_turn", text="done")


class _TwoBashProvider:
    """Step 1+2: two separate bash calls. Step 3: end_turn."""

    def __init__(self) -> None:
        self._step = 0

    async def chat(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        self._step += 1
        if self._step == 1:
            tc = ToolCallBlock(id="tc1", name="bash", input={"command": "echo first"})
            return LlmResponse(stop_reason="tool_use", tool_calls=[tc])
        if self._step == 2:
            tc = ToolCallBlock(id="tc2", name="bash", input={"command": "echo second"})
            return LlmResponse(stop_reason="tool_use", tool_calls=[tc])
        return LlmResponse(stop_reason="end_turn", text="done")


# ── helper ────────────────────────────────────────────────────────────────────


def _runner(
    provider: object,
    bus: EventBus,
    manager: PermissionManager,
    tmp_path: Path,
    max_steps: int = 10,
) -> AgentRunner:
    config = AgentXConfig()
    config.agent.max_steps = max_steps
    return AgentRunner(
        config,
        bus=bus,
        provider=provider,  # type: ignore[arg-type]
        permission_manager=manager,
        runs_dir=tmp_path / "runs",
    )


# ── tests ─────────────────────────────────────────────────────────────────────


# 功能：驗證 allow_once 決策後工具正常執行並寫入 tool.call_finished 事件
# 設計：在 permission.requested 事件到達時同步呼叫 manager.respond("allow_once")；
#       Future 在同一 event-loop turn 內解決，工具隨後執行；斷言 tool.call_finished 存在且 tool.call_failed 不存在
async def test_permission_allow_once_tool_executes(tmp_path: Path) -> None:
    manager = PermissionManager()
    bus = EventBus()
    event_types: list[str] = []

    async def collect(e: BaseModel) -> None:
        t = getattr(e, "type", "")
        event_types.append(t)
        if t == "permission.requested":
            manager.respond(getattr(e, "tool_use_id", ""), "allow_once")

    bus.subscribe(collect)
    outcome = await _runner(_SingleBashProvider(), bus, manager, tmp_path).run_and_capture(
        "run bash"
    )

    assert "permission.requested" in event_types
    assert "tool.call_finished" in event_types
    assert "tool.call_failed" not in event_types
    assert outcome.status == "success"


# 功能：驗證 deny_once 決策後工具不執行，事件流中出現 permission_denied 錯誤
# 設計：在 permission.requested 時 respond("deny_once")；斷言 tool.call_failed 的 error_class 為
#       "permission_denied"，且 tool.call_finished 不出現，確認工具從未被呼叫
async def test_permission_deny_once_tool_not_executed(tmp_path: Path) -> None:
    manager = PermissionManager()
    bus = EventBus()
    event_types: list[str] = []
    failed_events: list[BaseModel] = []

    async def collect(e: BaseModel) -> None:
        t = getattr(e, "type", "")
        event_types.append(t)
        if t == "permission.requested":
            manager.respond(getattr(e, "tool_use_id", ""), "deny_once")
        if t == "tool.call_failed":
            failed_events.append(e)

    bus.subscribe(collect)
    await _runner(_SingleBashProvider(), bus, manager, tmp_path).run_and_capture("run bash")

    assert "permission.requested" in event_types
    assert "tool.call_failed" in event_types
    assert "tool.call_finished" not in event_types
    assert getattr(failed_events[0], "error_class", None) == "permission_denied"


# 功能：驗證 always_allow 決策在 session 內快取，第二次同名工具不再觸發 permission.requested
# 設計：兩步 bash 呼叫；第一次 respond("always_allow")，斷言 permission.requested 只出現一次；
#       第二次工具呼叫命中快取並直接執行，不掛起 Future
async def test_always_allow_cached_within_session(tmp_path: Path) -> None:
    manager = PermissionManager()
    bus = EventBus()
    perm_requested_count = 0

    async def collect(e: BaseModel) -> None:
        nonlocal perm_requested_count
        if getattr(e, "type", "") == "permission.requested":
            perm_requested_count += 1
            manager.respond(getattr(e, "tool_use_id", ""), "always_allow")

    bus.subscribe(collect)
    outcome = await _runner(_TwoBashProvider(), bus, manager, tmp_path).run_and_capture(
        "run two bash commands"
    )

    assert perm_requested_count == 1
    assert outcome.status == "success"
