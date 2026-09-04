from __future__ import annotations

from kama_claude.core.tools.base import BaseTool, ToolResult
from kama_claude.core.tools.registry import ToolRegistry


class _FakeTool(BaseTool):
    name = "fake"
    description = "A fake tool"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content="ok")


# 功能：驗證註冊工具後能透過名稱檢索到同一例項
# 設計：斷言 `is`（同一物件引用）而非 `==`，確認 registry 儲存的是引用而非副本，避免不必要的物件複製
def test_register_and_get() -> None:
    registry = ToolRegistry()
    tool = _FakeTool()
    registry.register(tool)
    assert registry.get("fake") is tool


# 功能：驗證查詢不存在的工具名返回 None 而非丟擲異常
# 設計：空 registry 直接查詢，確認返回值語義為 None（而非 KeyError），invoke_tool 依賴此行為判斷"未知工具"
def test_get_unknown_returns_none() -> None:
    assert ToolRegistry().get("missing") is None


# 功能：驗證 tool_schemas() 輸出的每條記錄包含 Anthropic API 所需的三個必填欄位
# 設計：這三個欄位（name/description/input_schema）是 Anthropic tool definition 格式，缺少任何一個都會導致 LLM 呼叫失敗
def test_tool_schemas_contains_name_description_input_schema() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    schemas = registry.tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "fake"
    assert schemas[0]["description"] == "A fake tool"
    assert "input_schema" in schemas[0]


# 功能：驗證多工具註冊後 tool_schemas() 包含所有工具，不遺漏
# 設計：用 set 比較名稱集合而非檢查順序，聚焦"完整性"而非"順序"，確認 registry 不遺漏任何已註冊工具
def test_multiple_tools_all_appear_in_schemas() -> None:
    class _AnotherTool(BaseTool):
        name = "another"
        description = "Another"
        input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

        async def invoke(self, params: dict[str, object]) -> ToolResult:
            return ToolResult(content="")

    registry = ToolRegistry()
    registry.register(_FakeTool())
    registry.register(_AnotherTool())
    names = {s["name"] for s in registry.tool_schemas()}
    assert names == {"fake", "another"}


# 功能：驗證重複註冊同名工具時新版本覆蓋舊版本（覆蓋語義而非追加）
# 設計：檢查 description 變更，確認 registry 的覆蓋語義，防止工具版本衝突導致舊實現殘留
def test_register_same_name_overwrites() -> None:
    class _Updated(BaseTool):
        name = "fake"
        description = "updated"
        input_schema: dict[str, object] = {}

        async def invoke(self, params: dict[str, object]) -> ToolResult:
            return ToolResult(content="")

    registry = ToolRegistry()
    registry.register(_FakeTool())
    registry.register(_Updated())
    found = registry.get("fake")
    assert found is not None
    assert found.description == "updated"
