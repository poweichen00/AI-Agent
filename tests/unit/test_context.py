from __future__ import annotations

from agentx.core.context import ExecutionContext


# 功能：驗證 ExecutionContext 初始化時將 goal 包裝為第一條 user 訊息
# 設計：直接檢查 messages 列表初始狀態，不經過任何方法，因為這是 Anthropic messages 格式的起點，必須精確
def test_initial_message_is_goal() -> None:
    ctx = ExecutionContext(run_id="r1", goal="test goal", max_steps=5)
    assert ctx.messages == [{"role": "user", "content": "test goal"}]


# 功能：驗證新建 context 的 is_done() 返回 False
# 設計：初始化後立即查詢，無需任何操作，排除預設值錯誤導致 AgentLoop 在第一步就認為任務已完成
def test_is_done_returns_false_when_running() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    assert not ctx.is_done()


# 功能：驗證 mark_success 後 is_done、status、reason 三個欄位同時反映成功狀態
# 設計：同時斷言三個欄位，因為 AgentLoop 和 AgentRunner 都依賴這三者聯合判斷 run 結果
def test_mark_success() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.mark_success()
    assert ctx.is_done()
    assert ctx.status == "success"
    assert ctx.reason is None


# 功能：驗證 mark_failed 後 status 和 reason 被正確記錄
# 設計：傳入具體 reason 字串，斷言其在 context.reason 中完整保留，供 run.finished 事件使用
def test_mark_failed() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.mark_failed("exceeded_max_steps")
    assert ctx.is_done()
    assert ctx.status == "failed"
    assert ctx.reason == "exceeded_max_steps"


# 功能：驗證 add_assistant_message 追加符合 Anthropic 格式的訊息（role=assistant）
# 設計：驗證最後一條訊息的 role 和 content 引用，確認 Anthropic API 所要求的訊息結構
def test_add_assistant_message_appended() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    content = [{"type": "text", "text": "I'll help"}]
    ctx.add_assistant_message(content)
    assert ctx.messages[-1] == {"role": "assistant", "content": content}


# 功能：驗證工具結果被包裝為 tool_result 型別的 user 訊息，並帶有正確的 tool_use_id
# 設計：先加含 tool_use block 的 assistant 訊息（滿足 Anthropic 要求），再呼叫 add_tool_result，檢查最終訊息結構
def test_add_tool_result_creates_user_message() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.add_assistant_message(
        [{"type": "tool_use", "id": "toolu_01", "name": "read_file", "input": {"path": "x"}}]
    )
    ctx.add_tool_result("toolu_01", "file content")
    last = ctx.messages[-1]
    assert last["role"] == "user"
    assert last["content"][0]["type"] == "tool_result"
    assert last["content"][0]["tool_use_id"] == "toolu_01"
    assert last["content"][0]["content"] == "file content"


# 功能：驗證同一步驟的多個工具結果被合併到一條 user 訊息而非拆成多條
# 設計：連續兩次 add_tool_result，斷言訊息總數為 3（goal + assistant + 合併 user）；Anthropic API 要求同一輪 tool_result 合併提交
def test_multiple_tool_results_share_one_message() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.add_assistant_message([
        {"type": "tool_use", "id": "toolu_01", "name": "read_file", "input": {}},
        {"type": "tool_use", "id": "toolu_02", "name": "read_file", "input": {}},
    ])
    ctx.add_tool_result("toolu_01", "result A")
    ctx.add_tool_result("toolu_02", "result B")

    # goal + assistant + tool_results（合併為一條）
    assert len(ctx.messages) == 3
    last = ctx.messages[-1]
    assert last["role"] == "user"
    assert len(last["content"]) == 2
    assert last["content"][0]["tool_use_id"] == "toolu_01"
    assert last["content"][1]["tool_use_id"] == "toolu_02"


# 功能：驗證失敗的工具結果中 is_error 標記被正確傳遞到訊息 block
# 設計：傳入 is_error=True 後檢查 block 中的欄位，確認錯誤標記不丟失，LLM 在下一步能感知工具失敗
def test_tool_result_error_flag() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.add_assistant_message(
        [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]
    )
    ctx.add_tool_result("t1", "something failed", is_error=True)
    block = ctx.messages[-1]["content"][0]
    assert block["is_error"] is True
    assert block["content"] == "something failed"


# 功能：驗證多輪步驟的訊息 role 順序符合 user-assistant 交替規則
# 設計：只檢查 roles 列表，不檢查 content，聚焦 Anthropic API 對交替訊息格式的要求
def test_message_order_across_steps() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.add_assistant_message([{"type": "text", "text": "step 1 plan"}])
    ctx.add_tool_result("t1", "tool result")
    ctx.add_assistant_message([{"type": "text", "text": "step 2 plan"}])

    roles = [m["role"] for m in ctx.messages]
    assert roles == ["user", "assistant", "user", "assistant"]


# 功能：驗證步數計數器初始值為 0
# 設計：簡單邊界值測試，確認計數器起點，AgentLoop 依賴此初始值做步數限制判斷
def test_step_counter_default() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=20)
    assert ctx.step == 0
