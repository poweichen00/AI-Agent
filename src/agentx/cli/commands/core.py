from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

from agentx.core.config import AgentXConfig

_PID_FILE = Path.home() / ".agentx" / "agentx-core.pid"


# 嘗試連線 daemon，成功則正常返回，失敗則丟擲 ConnectionRefusedError/OSError
async def _ping_check(config: AgentXConfig) -> None:
    _r, w = await asyncio.open_connection(config.host, config.port)
    w.close()
    await w.wait_closed()


# 讀取 PID 檔案並確認程式存活，程式已消失則刪除檔案並返回 None
def _running_pid() -> int | None:
    if not _PID_FILE.exists():
        return None
    try:
        pid = int(_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        _PID_FILE.unlink(missing_ok=True)
        return None


# 列印 daemon 當前狀態（running / not running）
def cmd_core_status(config: AgentXConfig) -> None:
    try:
        asyncio.run(_ping_check(config))
        print(f"running  ({config.host}:{config.port})")
    except (ConnectionRefusedError, OSError):
        print("not running")


# 在後臺啟動 daemon，若已在執行則提示並退出
def cmd_core_start(config: AgentXConfig) -> None:
    try:
        asyncio.run(_ping_check(config))
        print(f"already running  ({config.host}:{config.port})")
        return
    except (ConnectionRefusedError, OSError):
        pass

    proc = subprocess.Popen(
        [sys.executable, "-m", "agentx.core"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(proc.pid))
    print(f"started  pid={proc.pid}  ({config.host}:{config.port})")


# 向 daemon 傳送 SIGTERM 停止程式，若未執行則提示
def cmd_core_stop(config: AgentXConfig) -> None:
    pid = _running_pid()
    if pid is None:
        print("not running")
        return
    os.kill(pid, signal.SIGTERM)
    _PID_FILE.unlink(missing_ok=True)
    print(f"stopped  pid={pid}")
