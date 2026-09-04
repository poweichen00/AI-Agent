from __future__ import annotations

import asyncio
from pathlib import Path

from kama_claude.core.trace.record import TraceRecord


class TraceWriter:
    # 初始化 TraceWriter；寫入目標檔案路徑在 start() 前不會建立
    def __init__(self, path: Path) -> None:
        self._path = path
        self._queue: asyncio.Queue[TraceRecord] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    # 建立目錄、啟動後臺 drain task
    async def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._drain())

    # 等待佇列清空後取消 drain task
    async def stop(self) -> None:
        await self._queue.join()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # 非阻塞地將 record 放入寫入佇列
    def emit(self, record: TraceRecord) -> None:
        self._queue.put_nowait(record)

    # 持續從佇列讀取 record 並追加寫入檔案
    async def _drain(self) -> None:
        with open(self._path, "a") as f:
            while True:
                record = await self._queue.get()
                try:
                    f.write(record.model_dump_json() + "\n")
                    f.flush()
                finally:
                    self._queue.task_done()
