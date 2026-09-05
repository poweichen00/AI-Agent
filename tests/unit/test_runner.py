from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from agentx.core.config import AgentXConfig
from agentx.core.events.bus import EventBus
from agentx.core.llm.types import LlmResponse, ToolCallBlock
from agentx.core.runner import AgentRunner

# --- mock provider -----------------------------------------------------------


class _EndTurnProvider:
    """Immediately returns end_turn; no API calls made."""

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
        return LlmResponse(stop_reason="end_turn", text="done")


class _LoopingProvider:
    """Always returns tool_use with an unknown tool to exhaust max_steps."""

    def __init__(self) -> None:
        self._call = 0

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
        self._call += 1
        tc = ToolCallBlock(id=f"t{self._call}", name="unknown_tool", input={})
        return LlmResponse(stop_reason="tool_use", tool_calls=[tc])


class _CapturingProvider:
    # 初始化捕獲型 provider，儲存固定響應
    def __init__(self, response: LlmResponse) -> None:
        self.response = response
        self.messages: list[dict[str, object]] = []
        self.system: str | None = None

    # 捕獲本次 LLM 呼叫的 messages 和 system prompt
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
        self.messages = [dict(m) for m in messages]
        self.system = system
        return self.response


# --- helpers -----------------------------------------------------------------


def _config(max_steps: int = 5) -> AgentXConfig:
    cfg = AgentXConfig()
    cfg.agent.max_steps = max_steps
    return cfg


async def _run(
    goal: str = "test goal",
    *,
    provider: object | None = None,
    config: AgentXConfig | None = None,
    tmp_path: Path,
) -> list[BaseModel]:
    collected: list[BaseModel] = []

    async def _collect(e: BaseModel) -> None:
        collected.append(e)

    cfg = config or _config()
    runner = AgentRunner(
        cfg,
        provider=provider or _EndTurnProvider(),  # type: ignore[arg-type]
        extra_handlers=[_collect],
        runs_dir=tmp_path,
    )
    await runner.run(goal)
    return collected


# --- tests -------------------------------------------------------------------


# 功能：驗證 run 開始時釋出攜帶正確 goal 的 run.started 事件
# 設計：用 extra_handlers 收集事件，而非從 events.jsonl 讀取，避免檔案 I/O 耦合；聚焦 runner 層的事件釋出職責
async def test_run_started_event_published(tmp_path: Path) -> None:
    events = await _run(goal="my goal", tmp_path=tmp_path)
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "run.started" in types
    started = next(e for e in events if e.type == "run.started")  # type: ignore[attr-defined]
    assert started.goal == "my goal"  # type: ignore[attr-defined]


# 功能：驗證成功完成時釋出 status=success 的 run.finished 事件
# 設計：EndTurnProvider 觸發最短成功路徑，聚焦 runner 層對任何終止路徑都能保證釋出 finished 事件
async def test_run_finished_event_published_on_success(tmp_path: Path) -> None:
    events = await _run(tmp_path=tmp_path)
    finished = next(
        (e for e in events if e.type == "run.finished"), None  # type: ignore[attr-defined]
    )
    assert finished is not None
    assert finished.status == "success"  # type: ignore[attr-defined]


# 功能：驗證步數耗盡時 run.finished 攜帶 failed 狀態和正確的失敗原因
# 設計：LoopingProvider + max_steps=2 觸發失敗路徑，確認 runner 在失敗終止路徑同樣釋出 finished 事件
async def test_run_finished_event_published_on_max_steps(tmp_path: Path) -> None:
    events = await _run(
        provider=_LoopingProvider(),
        config=_config(max_steps=2),
        tmp_path=tmp_path,
    )
    finished = next(e for e in events if e.type == "run.finished")  # type: ignore[attr-defined]
    assert finished.status == "failed"  # type: ignore[attr-defined]
    assert finished.reason == "exceeded_max_steps"  # type: ignore[attr-defined]


# 功能：驗證 events.jsonl 第一行為 run.started、最後一行為 run.finished
# 設計：從 tmp_path 遞迴查詢 events.jsonl 並按行解析，因為 events.jsonl 是 S1 的核心產物，首尾事件是完整性的最低要求
async def test_events_jsonl_created_with_started_and_finished(tmp_path: Path) -> None:
    await _run(tmp_path=tmp_path)
    jsonl_files = list(tmp_path.rglob("events.jsonl"))
    assert len(jsonl_files) == 1
    lines = [json.loads(ln) for ln in jsonl_files[0].read_text().splitlines() if ln]
    event_types = [e["type"] for e in lines]
    assert event_types[0] == "run.started"
    assert event_types[-1] == "run.finished"


# 功能：驗證 runner 在 runs_dir 下建立以 run_id 命名的子目錄並寫入 events.jsonl
# 設計：檢查 tmp_path 下只有一個子目錄且該目錄包含 events.jsonl，確認目錄結構約定（runs/<run_id>/events.jsonl）
async def test_run_creates_run_subdirectory(tmp_path: Path) -> None:
    await _run(tmp_path=tmp_path)
    subdirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(subdirs) == 1
    assert (subdirs[0] / "events.jsonl").exists()


# 功能：驗證透過 extra_handlers 注入的回撥能收到所有事件
# 設計：注入第二個收集器，確認 extra_handlers 機制有效；這是測試程式碼注入 mock 觀察器、生產程式碼接入 StdoutPrinter 的同一擴充套件點
async def test_extra_handlers_receive_events(tmp_path: Path) -> None:
    secondary: list[BaseModel] = []

    async def _second(e: BaseModel) -> None:
        secondary.append(e)

    cfg = _config()
    runner = AgentRunner(
        cfg,
        provider=_EndTurnProvider(),  # type: ignore[arg-type]
        extra_handlers=[_second],
        runs_dir=tmp_path,
    )
    await runner.run("goal")
    assert len(secondary) > 0


# 功能：驗證 config.agent.max_steps 被正確傳遞給 AgentLoop，控制 LLM 呼叫次數上限
# 設計：用 LoopingProvider 的呼叫次數反推 max_steps 是否生效，不依賴內部狀態檢查，從行為角度驗證配置傳遞
async def test_config_max_steps_passed_to_loop(tmp_path: Path) -> None:
    provider = _LoopingProvider()
    await _run(provider=provider, config=_config(max_steps=3), tmp_path=tmp_path)
    assert provider._call == 3


# 功能：驗證 run.started 和 run.finished 事件使用相同且非空的 run_id
# 設計：同時檢查兩個事件的 run_id 欄位，確認 runner 在整個 run 生命週期使用同一個 run_id
async def test_run_id_embedded_in_started_event(tmp_path: Path) -> None:
    events = await _run(tmp_path=tmp_path)
    started = next(e for e in events if e.type == "run.started")  # type: ignore[attr-defined]
    finished = next(e for e in events if e.type == "run.finished")  # type: ignore[attr-defined]
    assert started.run_id == finished.run_id  # type: ignore[attr-defined]
    assert len(started.run_id) > 0  # type: ignore[attr-defined]


# 功能：驗證注入外部 EventBus 時，runner 使用該 bus 而不自建，外部訂閱者能收到所有事件
# 設計：顯式傳入 EventBus 例項並訂閱收集器，確認 runner 不再內部新建 bus（否則外部訂閱者收不到事件）；
#       這是 CoreApp 注入全域性 bus 的核心行為，單元測試級別驗證可避免整合測試的守護程式依賴
async def test_injected_bus_receives_events(tmp_path: Path) -> None:
    from agentx.core.events.bus import EventBus

    external_bus = EventBus()
    collected: list[object] = []

    async def collect(e: object) -> None:
        collected.append(e)

    external_bus.subscribe(collect)

    runner = AgentRunner(
        _config(),
        bus=external_bus,
        provider=_EndTurnProvider(),  # type: ignore[arg-type]
        runs_dir=tmp_path,
    )
    await runner.run("goal")

    types = [e.type for e in collected]  # type: ignore[attr-defined]
    assert "run.started" in types
    assert "run.finished" in types


# 功能：驗證 session run 會從 thread.jsonl 預填 messages，並把 notes 注入 system prompt
# 設計：用 CapturingProvider 截獲 LLM 入參，不觸發真實 API；同時斷言 run 目錄寫到 session/runs 下
async def test_session_history_and_notes_injected(tmp_path: Path) -> None:
    from agentx.core.session.model import Session
    from agentx.core.session.store import SessionStore

    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.write_meta(session)
    store.append_message("sess-1", "user", "remember python")
    store.append_note("sess-1", "Python 3.12", "run-old")

    provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
    runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / "runs")

    await runner.run_and_capture("remember python", run_id="run-new", session=session, store=store)

    assert provider.messages == [{"role": "user", "content": "remember python"}]
    assert provider.system is not None
    assert "Python 3.12" in provider.system
    assert (store.runs_dir("sess-1") / "run-new" / "events.jsonl").exists()
    assert not (tmp_path / "runs" / "run-new").exists()


# 功能：驗證 session run 中註冊了 note_save，工具呼叫會寫入 notes.md
# 設計：mock provider 第一步請求 note_save、第二步 end_turn，覆蓋 runner→registry→tool invocation 的完整路徑
async def test_session_registers_note_save_tool(tmp_path: Path) -> None:
    from agentx.core.session.model import Session
    from agentx.core.session.store import SessionStore

    class _NoteProvider:
        # 初始化呼叫計數器，用於返回兩步響應
        def __init__(self) -> None:
            self.calls = 0

        # 第一步請求 note_save，第二步返回 end_turn
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
            self.calls += 1
            if self.calls == 1:
                return LlmResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        ToolCallBlock(
                            id="note-1",
                            name="note_save",
                            input={"content": "Use Python 3.12"},
                        )
                    ],
                )
            return LlmResponse(stop_reason="end_turn", text="noted")

    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.append_message("sess-1", "user", "remember")

    runner = AgentRunner(_config(max_steps=3), provider=_NoteProvider(), runs_dir=tmp_path)
    await runner.run_and_capture("remember", run_id="run-1", session=session, store=store)

    assert "Use Python 3.12" in store.read_notes("sess-1")
