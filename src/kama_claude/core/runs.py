from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

RUNS_DIR = Path("runs")


# 返回指定 run_id 對應的目錄路徑
def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


# 返回指定 run_id 的事件日誌檔案路徑
def events_file(run_id: str) -> Path:
    return run_dir(run_id) / "events.jsonl"


# 生成格式為 YYYYMMDD-HHMMSS-xxxxxx 的唯一 run ID
def new_run_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{ts}-{suffix}"


# 建立 run 目錄（含父級）並返回路徑
def ensure_run_dir(run_id: str) -> Path:
    path = run_dir(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
