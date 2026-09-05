"""AgentX 終端介面。"""

import os

# macOS 中文輸入法需要由終端提交完整的組字結果。Textual 的 Kitty 延伸鍵盤
# 協定可能讓組字期間的按鍵直接進入 TUI，因此在載入 Textual 前將它關閉。
os.environ.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")
