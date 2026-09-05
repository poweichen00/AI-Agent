from __future__ import annotations

from agentx.core.compact.budget import truncate_tool_results


def _make_tool_result_msg(content: str) -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "id1", "content": content}],
    }


# 功能：驗證 tool_result 內容未超過閾值時原文不變
# 設計：構造 7999 字元內容（剛好低於 8000），斷言訊息原樣返回
def test_short_tool_result_untouched() -> None:
    text = "x" * 7999
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["content"] == text


# 功能：驗證 tool_result 內容超過閾值時被截斷並附加省略標記
# 設計：構造 10000 字元內容，斷言截斷後長度 < 原始，且包含省略標記字串
def test_long_tool_result_truncated() -> None:
    text = "y" * 10_000
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    truncated = result[0]["content"][0]["content"]
    assert len(truncated) < len(text)
    assert "chars omitted" in truncated
    assert truncated.startswith("y" * 4000)


# 功能：驗證 tool_result 內容恰好等於閾值時不截斷
# 設計：構造恰好 8000 字元內容，斷言原文保持不變
def test_exact_limit_untouched() -> None:
    text = "z" * 8000
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["content"] == text


# 功能：驗證 text 型別 block 不受截斷影響
# 設計：構造含 text block 的 user 訊息，內容超過閾值，斷言內容原樣返回
def test_non_tool_result_block_untouched() -> None:
    long_text = "a" * 20_000
    msgs = [{"role": "user", "content": [{"type": "text", "text": long_text}]}]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["text"] == long_text


# 功能：驗證同一 user 訊息含多個 tool_result 時各自獨立判斷截斷
# 設計：構造一條訊息含兩個 tool_result，一短一長，斷言只有長的被截斷
def test_multiple_tool_results_independent() -> None:
    short = "s" * 100
    long = "l" * 10_000
    msgs = [{
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "a", "content": short},
            {"type": "tool_result", "tool_use_id": "b", "content": long},
        ],
    }]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    blocks = result[0]["content"]
    assert blocks[0]["content"] == short
    assert "chars omitted" in blocks[1]["content"]


# 功能：驗證 assistant 訊息不被截斷處理
# 設計：構造超長內容的 assistant 訊息，斷言原樣返回
def test_assistant_message_untouched() -> None:
    text = "a" * 20_000
    msgs = [{"role": "assistant", "content": text}]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"] == text
