from __future__ import annotations

import asyncio

from agentx.core.context import ExecutionContext


# 管理後臺 subagent 任務的生命週期：註冊、查詢、批次取消
class BackgroundTaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, tuple[asyncio.Task[None], ExecutionContext]] = {}

    # 註冊一個後臺任務及其執行上下文
    def register(
        self,
        run_id: str,
        task: asyncio.Task[None],
        context: ExecutionContext,
    ) -> None:
        self._tasks[run_id] = (task, context)

    # 查詢後臺任務及其上下文；不存在時返回 None
    def get(self, run_id: str) -> tuple[asyncio.Task[None], ExecutionContext] | None:
        return self._tasks.get(run_id)

    # 返回所有已註冊的 (task, context) 對，用於 daemon 退出時批次清理
    def all(self) -> list[tuple[asyncio.Task[None], ExecutionContext]]:
        return list(self._tasks.values())
