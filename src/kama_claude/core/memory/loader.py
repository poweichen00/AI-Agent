from __future__ import annotations

from pathlib import Path


# 讀取指定路徑的 context.md，路徑不存在或內容為空時返回空字串
def load_context_file(path: Path) -> str:
    p = path.expanduser()
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()
