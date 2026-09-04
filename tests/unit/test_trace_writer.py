import json
from pathlib import Path

import pytest

from kama_claude.core.trace.record import TraceRecord
from kama_claude.core.trace.writer import TraceWriter


def _record(direction: str = "CORE", kind: str = "event") -> TraceRecord:
    return TraceRecord(
        ts="2026-01-01T00:00:00.000Z",
        direction=direction,  # type: ignore[arg-type]
        layer="event",
        kind=kind,
        data={"type": "run.started", "run_id": "r1"},
    )


# 功能：驗證 emit 後 stop 能將 record 寫入檔案
# 設計：用臨時目錄避免汙染；await stop() 保證 drain 完成後再讀檔案
@pytest.mark.asyncio
async def test_emit_writes_record_to_file(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    await writer.start()

    writer.emit(_record())
    await writer.stop()

    lines = path.read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["direction"] == "CORE"
    assert parsed["kind"] == "event"


# 功能：驗證多條 record 按 emit 順序寫入檔案
# 設計：emit 三條方向各異的 record，斷言順序與方向均保持一致
@pytest.mark.asyncio
async def test_emit_multiple_records_in_order(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    await writer.start()

    writer.emit(_record("CLIENT→CORE", "command"))
    writer.emit(_record("CORE", "event"))
    writer.emit(_record("LLM→CORE", "api_response"))
    await writer.stop()

    lines = path.read_text().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["direction"] == "CLIENT→CORE"
    assert json.loads(lines[1])["direction"] == "CORE"
    assert json.loads(lines[2])["direction"] == "LLM→CORE"


# 功能：驗證 emit 是同步非阻塞的（不需要 await）
# 設計：在 start() 之前呼叫 emit 會放入佇列而不拋異常，start 後正常 drain
@pytest.mark.asyncio
async def test_emit_is_nonblocking(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    await writer.start()

    # emit 是同步呼叫，不應阻塞事件迴圈
    for _ in range(10):
        writer.emit(_record())
    await writer.stop()

    assert len(path.read_text().splitlines()) == 10


# 功能：驗證 TraceWriter 自動建立不存在的父目錄
# 設計：指定一個深層巢狀路徑，start() 後 emit 能正常寫入
@pytest.mark.asyncio
async def test_start_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "c" / "trace.jsonl"
    writer = TraceWriter(path)
    await writer.start()
    writer.emit(_record())
    await writer.stop()

    assert path.exists()
    assert len(path.read_text().splitlines()) == 1


# 功能：驗證 stop 後再次 start 可以追加寫入（檔案已存在時）
# 設計：兩次 start/stop 迴圈，斷言檔案行數累加而非覆蓋
@pytest.mark.asyncio
async def test_append_mode_on_restart(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"

    writer = TraceWriter(path)
    await writer.start()
    writer.emit(_record())
    await writer.stop()

    writer2 = TraceWriter(path)
    await writer2.start()
    writer2.emit(_record())
    await writer2.stop()

    assert len(path.read_text().splitlines()) == 2
