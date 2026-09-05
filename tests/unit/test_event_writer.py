from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from agentx.core.bus.events import RunFinishedEvent, RunStartedEvent
from agentx.core.events.bus import EventBus
from agentx.core.events.writer import EventWriter


# 功能：驗證 handle 後事件被正確序列化為單行 JSONL 寫入磁碟
# 設計：使用真實檔案（tmp_path）而非 mock，因為 EventWriter 的核心職責是磁碟寫入，只有實際讀取檔案內容才能證明寫入正確
async def test_event_writer_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = RunStartedEvent(run_id="run-1", goal="test goal", ts="2026-05-11T00:00:00Z")

    async with EventWriter(path) as writer:
        await writer.handle(event)

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["type"] == "run.started"
    assert data["run_id"] == "run-1"
    assert data["goal"] == "test goal"


# 功能：驗證目標路徑的父目錄不存在時 EventWriter 自動建立多級目錄
# 設計：傳入多級不存在的路徑，只斷言檔案最終存在，避免過度測試實現細節（如 mkdir 呼叫次數）
async def test_event_writer_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "abc123" / "events.jsonl"
    event = RunStartedEvent(run_id="abc123", goal="test", ts="2026-05-11T00:00:00Z")

    async with EventWriter(path) as writer:
        await writer.handle(event)

    assert path.exists()


# 功能：驗證多次 handle 是追加寫入而非覆蓋
# 設計：寫兩條不同型別事件，檢查行數和各行 type 欄位，確認 JSONL 追加語義
async def test_event_writer_appends_multiple_events(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"

    async with EventWriter(path) as writer:
        await writer.handle(RunStartedEvent(run_id="r1", goal="g1", ts="2026-05-11T00:00:00Z"))
        finished = RunFinishedEvent(
            run_id="r1", status="success", steps=2, ts="2026-05-11T00:00:01Z"
        )
        await writer.handle(finished)

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "run.started"
    assert json.loads(lines[1])["type"] == "run.finished"


# 功能：驗證 subscribe 把 writer 接入 EventBus 後，bus.publish 能觸發檔案寫入
# 設計：透過 bus.publish 觸發寫入（而非直接調 writer.handle），測試整合路徑，確認訂閱接線正確
async def test_event_writer_subscribe_via_bus(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    bus = EventBus()
    event = RunStartedEvent(run_id="r1", goal="g", ts="2026-05-11T00:00:00Z")

    async with EventWriter(path) as writer:
        writer.subscribe(bus)
        await bus.publish(event)

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == "r1"


# 功能：驗證檔案未透過 async with 開啟時 handle 靜默返回、不拋異常
# 設計：直接例項化 writer（跳過 async with），呼叫 handle 後不斷言檔案存在，以"不引發異常"為唯一判據；對應 EventWriter 的防禦性設計
async def test_event_writer_handle_when_not_open_is_noop(tmp_path: Path) -> None:
    writer = EventWriter(tmp_path / "events.jsonl")
    event = RunStartedEvent(run_id="r1", goal="g", ts="2026-05-11T00:00:00Z")
    await writer.handle(event)  # _file is None, should not raise


# 功能：驗證磁碟寫入失敗時只記錄 ERROR 日誌、不向上傳播異常
# 設計：手動關閉已開啟的檔案控制程式碼觸發 OSError，用 caplog 斷言 ERROR 級別日誌；EventWriter 的契約是"不因寫檔案失敗終止 agent"
async def test_event_writer_oserror_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "events.jsonl"
    event = RunStartedEvent(run_id="r1", goal="g", ts="2026-05-11T00:00:00Z")

    with caplog.at_level(logging.ERROR, logger="agentx.core.events.writer"):
        async with EventWriter(path) as writer:
            assert writer._file is not None
            writer._file.close()
            # _file 仍非 None 但已關閉，write 會拋 OSError
            await writer.handle(event)

    assert any("failed to write" in r.message for r in caplog.records)
