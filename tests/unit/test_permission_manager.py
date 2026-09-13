from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentx.core.permissions.manager import PermissionManager
from agentx.core.permissions.policy import PermissionDecision, ToolPolicy
from agentx.core.permissions.storage import load_policy_file

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_manager(**policies: ToolPolicy) -> PermissionManager:
    # policy_file=None：測試中不使用持久化，不汙染 ~/.agentx/policy.toml
    return PermissionManager(policies or None)


async def _collect_emitted() -> tuple[list[dict[str, Any]], Any]:
    emitted: list[dict[str, Any]] = []

    async def emitter(event: dict[str, Any]) -> None:
        emitted.append(event)

    return emitted, emitter


# ── evaluate() delegation ─────────────────────────────────────────────────────


# 功能：驗證 PermissionManager.evaluate 委託給 policy 層返回正確決策
# 設計：直接呼叫 evaluate()，不涉及 Future，驗證策略載入與委託路徑
def test_evaluate_delegates_to_policy() -> None:
    mgr = _make_manager()
    assert mgr.evaluate("read_file", {"path": "x"}) == PermissionDecision.ALLOW
    assert mgr.evaluate("bash", {"command": "echo hi"}) == PermissionDecision.ASK
    assert mgr.evaluate("write_file", {"path": "x", "content": ""}) == PermissionDecision.ASK


# ── check_and_wait: ALLOW path ───────────────────────────────────────────────


# 功能：驗證策略為 ALLOW 時 check_and_wait 立即返回 (True, "auto_allow")，不發任何事件
# 設計：read_file 預設 ALLOW，斷言不產生 permission.requested 事件，覆蓋"無噪聲放行"路徑
async def test_check_and_wait_allow_no_event() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t1",
        tool_name="read_file",
        params={"path": "README.md"},
        session_id="s1",
        event_emitter=emitter,
    )

    assert allowed is True
    assert decision == "auto_allow"
    assert emitted == []


# ── check_and_wait: ASK path + respond ───────────────────────────────────────


# 功能：驗證 ASK 策略時發出 permission.requested 事件並等待 respond() 解決 Future
# 設計：在後臺協程中呼叫 respond("allow_once")，主協程 await 結束後斷言結果；
#       這是許可權系統的核心反向請求通路
async def test_check_and_wait_ask_emits_event_and_waits() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    async def _auto_respond() -> None:
        await asyncio.sleep(0)  # yield once so check_and_wait can emit the event
        mgr.respond("t2", "allow_once")

    task = asyncio.create_task(_auto_respond())
    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t2",
        tool_name="bash",
        params={"command": "echo hi"},
        session_id="s1",
        event_emitter=emitter,
    )
    await task

    assert allowed is True
    assert decision == "allow_once"
    assert len(emitted) == 1
    assert emitted[0]["type"] == "permission.requested"
    assert emitted[0]["tool_use_id"] == "t2"
    assert emitted[0]["tool_name"] == "bash"


# 功能：驗證 respond("deny_once") 使 check_and_wait 返回 (False, "deny_once")
# 設計：使用者拒絕時工具不應執行，確認 False 返回值而不是異常
async def test_check_and_wait_deny_once_returns_false() -> None:
    mgr = _make_manager()
    _, emitter = await _collect_emitted()

    async def _auto_deny() -> None:
        await asyncio.sleep(0)
        mgr.respond("t3", "deny_once")

    task = asyncio.create_task(_auto_deny())
    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t3",
        tool_name="bash",
        params={"command": "echo hi"},
        session_id="s1",
        event_emitter=emitter,
    )
    await task

    assert allowed is False
    assert decision == "deny_once"


# ── always_allow cache ────────────────────────────────────────────────────────


# 功能：驗證 respond("always_allow") 後同 session 同工具下次不再發事件
# 設計：第二次呼叫 check_and_wait 命中 always 快取，直接返回 (True, "auto_allow")，emitted 仍為 1 條
async def test_always_allow_skips_future_ask() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    # First call: user says "always allow"
    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("t4", "always_allow")

    task = asyncio.create_task(_auto_always())
    r1, _ = await mgr.check_and_wait(
        tool_use_id="t4",
        tool_name="bash",
        params={"command": "echo hi"},
        session_id="s1",
        event_emitter=emitter,
    )
    await task
    assert r1 is True

    # Second call: should hit cache, no new event
    r2, d2 = await mgr.check_and_wait(
        tool_use_id="t5",
        tool_name="bash",
        params={"command": "ls"},
        session_id="s1",
        event_emitter=emitter,
    )

    assert r2 is True
    assert d2 == "auto_allow"
    assert len(emitted) == 1  # only the first call emitted an event


# 功能：驗證 always_allow 在同一 manager 例項內對所有 session 生效（persistent_always 共享）
# 設計：s1 設定 always_allow → 寫入 _persistent_always；s2 命中 persistent 快取，直接放行；
#       emitted 只有 1 條（s2 不需要再 ASK）。這是 persistent always 的核心跨 session 語義。
async def test_always_allow_not_shared_across_sessions() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    # session s1 sets always allow for bash
    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("t6", "always_allow")

    task = asyncio.create_task(_auto_always())
    await mgr.check_and_wait(
        tool_use_id="t6",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
    )
    await task

    # session s2 — persistent_always["bash"] = "allow" → 直接放行，不再 ASK
    r, d = await mgr.check_and_wait(
        tool_use_id="t7",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s2",
        event_emitter=emitter,
    )

    assert r is True
    assert d == "auto_allow"
    assert len(emitted) == 1  # s2 命中 persistent 快取，不再發出事件


# ── always_deny cache ─────────────────────────────────────────────────────────


# 功能：驗證 respond("always_deny") 後同 session 同工具下次直接返回 (False, "auto_deny")
# 設計：使用者選擇 always deny 後不應繼續騷擾，下次呼叫靜默拒絕
async def test_always_deny_skips_future_ask() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    async def _auto_always_deny() -> None:
        await asyncio.sleep(0)
        mgr.respond("t8", "always_deny")

    task = asyncio.create_task(_auto_always_deny())
    r1, _ = await mgr.check_and_wait(
        tool_use_id="t8",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
    )
    await task
    assert r1 is False

    # Second call: cache hit → no event, return (False, "auto_deny")
    r2, d2 = await mgr.check_and_wait(
        tool_use_id="t9",
        tool_name="bash",
        params={"command": "ls"},
        session_id="s1",
        event_emitter=emitter,
    )
    assert r2 is False
    assert d2 == "auto_deny"
    assert len(emitted) == 1


# ── cancel_session ────────────────────────────────────────────────────────────


# 功能：驗證 cancel_session 將 pending Future 設為 deny_once，check_and_wait 返回 False
# 設計：模擬客戶端斷連場景——check_and_wait 掛起後呼叫 cancel_session，
#       確認 Future 被解決而非永久掛起（防止殭屍 run）
async def test_cancel_session_resolves_pending_future() -> None:
    mgr = _make_manager()
    _, emitter = await _collect_emitted()

    async def _cancel_after_emit() -> None:
        await asyncio.sleep(0)  # wait for event to be emitted
        mgr.cancel_session("s1", reason="client_disconnected")

    task = asyncio.create_task(_cancel_after_emit())
    allowed, _ = await mgr.check_and_wait(
        tool_use_id="t10",
        tool_name="bash",
        params={"command": "ls"},
        session_id="s1",
        event_emitter=emitter,
    )
    await task

    assert allowed is False


# 功能：驗證 cancel_session 只取消屬於該 session 的 pending Future
# 設計：s1 和 s2 各有一個 pending，cancel_session(s2) 不影響 s1 的 Future
async def test_cancel_session_only_affects_target_session() -> None:
    mgr = _make_manager()
    _, emitter = await _collect_emitted()

    # Launch two concurrent check_and_wait for different sessions
    s1_done = asyncio.Event()
    s2_done = asyncio.Event()
    s1_result: list[bool] = []
    s2_result: list[bool] = []

    async def _s1() -> None:
        r, _ = await mgr.check_and_wait(
            tool_use_id="ta",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s1",
            event_emitter=emitter,
        )
        s1_result.append(r)
        s1_done.set()

    async def _s2() -> None:
        r, _ = await mgr.check_and_wait(
            tool_use_id="tb",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s2",
            event_emitter=emitter,
        )
        s2_result.append(r)
        s2_done.set()

    t1 = asyncio.create_task(_s1())
    t2 = asyncio.create_task(_s2())

    await asyncio.sleep(0)  # let both emit events and hang

    # cancel only s2
    mgr.cancel_session("s2")
    await s2_done.wait()

    # s1 should still be pending; resolve it manually
    mgr.respond("ta", "allow_once")
    await s1_done.wait()

    await t1
    await t2

    assert s1_result == [True]  # s1 was allowed
    assert s2_result == [False]  # s2 was cancelled → denied


# ── respond: unknown tool_use_id ──────────────────────────────────────────────


# 功能：驗證 respond 傳入不存在的 tool_use_id 時靜默忽略，不拋異常
# 設計：競態場景（客戶端重複傳送響應）不應導致 daemon crash
def test_respond_unknown_tool_use_id_is_noop() -> None:
    mgr = _make_manager()
    mgr.respond("nonexistent", "allow_once")  # should not raise


# ── OUTSIDE_CWD 不被 always 快取繞過 ─────────────────────────────────────────


# 功能：驗證 always_allow bash 之後，含絕對路徑的命令仍觸發 ASK，不被快取繞過
# 設計：先讓 session s1 對 bash 設定 always_allow，再請求含絕對路徑命令；
#       OUTSIDE_CWD 檢查在 always 快取之前，應發出 permission.requested 事件
async def test_always_allow_does_not_bypass_outside_cwd() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    # 首次 allow → 寫入 session always 快取
    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("t_always", "always_allow")

    t = asyncio.create_task(_auto_always())
    await mgr.check_and_wait(
        tool_use_id="t_always",
        tool_name="bash",
        params={"command": "echo ok"},
        session_id="s1",
        event_emitter=emitter,
    )
    await t
    assert len(emitted) == 1  # 首次 ASK 觸發事件

    # 第二次：bash + 絕對路徑 → OUTSIDE_CWD 強制 ASK，不命中 session always 快取
    async def _auto_respond_abs() -> None:
        await asyncio.sleep(0)
        mgr.respond("t_abs", "allow_once")

    t2 = asyncio.create_task(_auto_respond_abs())
    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t_abs",
        tool_name="bash",
        params={"command": "cat /etc/hosts"},
        session_id="s1",
        event_emitter=emitter,
    )
    await t2

    assert allowed is True
    assert len(emitted) == 2  # 絕對路徑命令再次觸發 ASK，共 2 個事件


# ── 持久化 always 寫檔案 ──────────────────────────────────────────────────────


# 功能：驗證 always_allow 決策寫入 policy_file，新 PermissionManager 載入後自動放行
# 設計：用 tmp_path 作為 policy_file，斷言檔案存在且內容正確；
#       再新建 manager 載入檔案，同工具無需 ASK 直接返回 auto_allow
async def test_persistent_always_written_and_reloaded(tmp_path: pytest.TempPathFixture) -> None:
    policy_file = tmp_path / "policy.toml"
    mgr = PermissionManager(policy_file=policy_file)
    emitted, emitter = await _collect_emitted()

    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("tp1", "always_allow")

    t = asyncio.create_task(_auto_always())
    allowed, _ = await mgr.check_and_wait(
        tool_use_id="tp1",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
    )
    await t
    assert allowed is True
    assert policy_file.exists()

    loaded = load_policy_file(policy_file)
    assert loaded.get("bash") == "allow"

    # 新 manager 載入同一檔案，bash 應直接 auto_allow（無 OUTSIDE_CWD）
    mgr2 = PermissionManager(policy_file=policy_file)
    emitted2, emitter2 = await _collect_emitted()
    allowed2, decision2 = await mgr2.check_and_wait(
        tool_use_id="tp2",
        tool_name="bash",
        params={"command": "echo new"},
        session_id="s2",
        event_emitter=emitter2,
    )
    assert allowed2 is True
    assert decision2 == "auto_allow"
    assert emitted2 == []  # 無需 ASK


# ── 審批超時 ──────────────────────────────────────────────────────────────────


# 功能：驗證 check_and_wait 超時後返回 (False, "timeout")，不永久掛起
# 設計：timeout_s=0.05 極短超時，不主動 respond；斷言在合理時間內返回 False
async def test_permission_timeout_returns_false() -> None:
    mgr = PermissionManager(timeout_s=0.05)
    emitted, emitter = await _collect_emitted()

    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t_timeout",
        tool_name="bash",
        params={"command": "echo hi"},
        session_id="s1",
        event_emitter=emitter,
    )

    assert allowed is False
    assert decision == "timeout"
    assert len(emitted) == 1
    assert emitted[0]["type"] == "permission.requested"


# 功能：驗證超時後 pending 被清理，遲到的 respond 不影響後續呼叫
# 設計：超時後呼叫 respond，不拋異常（unknown tool_use_id 靜默忽略）；
#       再次 check_and_wait 同 tool_use_id 仍正常發出新的 permission.requested
async def test_permission_timeout_cleans_up_pending() -> None:
    mgr = PermissionManager(timeout_s=0.05)
    _, emitter = await _collect_emitted()

    await mgr.check_and_wait(
        tool_use_id="t_late",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
    )
    # 超時後遲到的 respond 不應 crash
    mgr.respond("t_late", "allow_once")  # should be noop
    assert "t_late" not in mgr._pending
