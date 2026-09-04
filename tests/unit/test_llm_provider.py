from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.provider import AnthropicProvider
from kama_claude.core.llm.types import LlmResponse

# --- helpers -----------------------------------------------------------------


def _make_usage(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
    cache_create: int = 0,
) -> MagicMock:
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.cache_read_input_tokens = cache_read
    u.cache_creation_input_tokens = cache_create
    return u


def _make_final(
    stop_reason: str = "end_turn",
    content: list[MagicMock] | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
) -> MagicMock:
    msg = MagicMock()
    msg.stop_reason = stop_reason
    msg.content = content or []
    msg.usage = _make_usage(input_tokens, output_tokens, cache_read)
    return msg


class FakeStream:
    """Minimal async context manager that fakes the anthropic streaming interface."""

    def __init__(self, texts: list[str], final: MagicMock) -> None:
        self._texts = texts
        self._final = final

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    @property
    def text_stream(self):  # type: ignore[return]
        async def _gen():
            for t in self._texts:
                yield t

        return _gen()

    async def get_final_message(self) -> MagicMock:
        return self._final


def _make_provider(
    texts: list[str] | None = None,
    stop_reason: str = "end_turn",
    content: list[MagicMock] | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
) -> tuple[AnthropicProvider, MagicMock]:
    final = _make_final(stop_reason, content, input_tokens, output_tokens, cache_read)
    client = MagicMock()
    client.messages.stream.return_value = FakeStream(texts or [], final)
    return AnthropicProvider(model="test-model", client=client), client


async def _chat(
    provider: AnthropicProvider,
    messages: list[dict[str, object]] | None = None,
    tool_schemas: list[dict[str, object]] | None = None,
) -> tuple[LlmResponse, list[BaseModel]]:
    collected: list[BaseModel] = []
    bus = EventBus()

    async def _collect(e: BaseModel) -> None:
        collected.append(e)

    bus.subscribe(_collect)
    result = await provider.chat(
        messages=messages or [],
        tool_schemas=tool_schemas or [],
        bus=bus,
        run_id="r1",
    )
    return result, collected


# --- tests -------------------------------------------------------------------


# 功能：驗證每次 chat 呼叫都發布攜帶模型名和路由策略的 llm.model_selected 事件
# 設計：檢查事件數量為 1 且欄位精確匹配，因為 S6 路由報告依賴此事件統計模型使用分佈
async def test_model_selected_event_published() -> None:
    provider, _ = _make_provider()
    _, events = await _chat(provider)
    sel = [e for e in events if e.type == "llm.model_selected"]  # type: ignore[attr-defined]
    assert len(sel) == 1
    assert sel[0].model == "test-model"  # type: ignore[attr-defined]
    assert sel[0].strategy == "static"  # type: ignore[attr-defined]
    assert sel[0].run_id == "r1"  # type: ignore[attr-defined]


# 功能：驗證流式響應的每個 token 觸發獨立的 llm.token 事件，內容與順序均正確
# 設計：使用 FakeStream 控制精確的 token 序列，斷言數量和各 token 的值，排除批次合併或跳過情況
async def test_token_events_published_per_chunk() -> None:
    provider, _ = _make_provider(texts=["Hello", " world"])
    _, events = await _chat(provider)
    tokens = [e for e in events if e.type == "llm.token"]  # type: ignore[attr-defined]
    assert len(tokens) == 2
    assert tokens[0].token == "Hello"  # type: ignore[attr-defined]
    assert tokens[1].token == " world"  # type: ignore[attr-defined]


# 功能：驗證 llm.usage 事件中的 token 統計欄位（input、output、cache_read）正確
# 設計：向 FakeStream 注入固定 usage 值，斷言三個欄位精確匹配，因為這些欄位是 S6 成本計算的資料來源
async def test_usage_event_published_after_stream() -> None:
    provider, _ = _make_provider(input_tokens=200, output_tokens=75, cache_read=150)
    _, events = await _chat(provider)
    usage_events = [e for e in events if e.type == "llm.usage"]  # type: ignore[attr-defined]
    assert len(usage_events) == 1
    ue = usage_events[0]
    assert ue.input_tokens == 200  # type: ignore[attr-defined]
    assert ue.output_tokens == 75  # type: ignore[attr-defined]
    assert ue.cache_read_input_tokens == 150  # type: ignore[attr-defined]


# 功能：驗證事件釋出順序為 model_selected → token（×N） → usage
# 設計：檢查型別列表的首尾元素，聚焦 provider 的時序契約，而非中間 token 事件的順序（那由流本身決定）
async def test_event_order_model_selected_first_usage_last() -> None:
    provider, _ = _make_provider(texts=["hi"])
    _, events = await _chat(provider)
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert types[0] == "llm.model_selected"
    assert "llm.token" in types
    assert types[-1] == "llm.usage"


# 功能：驗證 stop_reason=tool_use 時 final_message content block 被正確解析為 ToolCallBlock
# 設計：注入帶 tool_use block 的 final_message，逐欄位檢查 ToolCallBlock 的 id/name/input，確認解析路徑完整
async def test_tool_use_parsed_from_final_message() -> None:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "toolu_01"
    tool_block.name = "read_file"
    tool_block.input = {"path": "README.md"}
    provider, _ = _make_provider(stop_reason="tool_use", content=[tool_block])
    result, _ = await _chat(provider)
    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.id == "toolu_01"
    assert tc.name == "read_file"
    assert tc.input == {"path": "README.md"}


# 功能：驗證 stop_reason=end_turn 時不產生任何工具呼叫
# 設計：與 test_tool_use_parsed 互補，確認 stop_reason 決策樹的另一側，防止 end_turn 響應被誤解析為 tool_use
async def test_end_turn_produces_no_tool_calls() -> None:
    provider, _ = _make_provider(stop_reason="end_turn")
    result, _ = await _chat(provider)
    assert result.stop_reason == "end_turn"
    assert result.tool_calls == []


# 功能：驗證多個流式 token 被正確拼接為 LlmResponse.text 欄位
# 設計：三段 token 拼接，檢查 result.text 完整字串，因為 StdoutPrinter 消費 text 欄位展示最終輸出
async def test_text_accumulated_from_tokens() -> None:
    provider, _ = _make_provider(texts=["foo", "bar", "baz"])
    result, _ = await _chat(provider)
    assert result.text == "foobarbaz"


# 功能：驗證缺少 ANTHROPIC_API_KEY 時 provider 初始化立即 SystemExit 而非等到呼叫時才報錯
# 設計：用 monkeypatch 清除環境變數後例項化，確認 fail-fast 行為，防止"幽靈 run"（有 started 但無 finished 事件）
async def test_missing_api_key_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        AnthropicProvider(model="any")


# 功能：驗證空流式響應不釋出任何 llm.token 事件且 result.text 為空字串
# 設計：texts=[] 覆蓋零 token 邊界條件，確認 text="" 而非 None，避免呼叫方對空內容做額外 None 判斷
async def test_no_tokens_when_response_is_empty() -> None:
    provider, _ = _make_provider(texts=[])
    result, events = await _chat(provider)
    tokens = [e for e in events if e.type == "llm.token"]  # type: ignore[attr-defined]
    assert tokens == []
    assert result.text == ""
