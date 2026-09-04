from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
from pathlib import Path

from kama_claude.core.config import get_config
from kama_claude.tui.app import KamaTuiApp

_DEFAULT_TUI_LOG = "~/.kama/logs/tui.log"


# TUI 檔案日誌初始化：不寫 stderr（避免幹擾 Textual 渲染），只寫滾動檔案
def _setup_logging(level: str) -> None:
    log_path = Path(os.environ.get("KAMA_TUI_LOG_FILE", _DEFAULT_TUI_LOG)).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            'level=%(levelname)s ts=%(asctime)s source=%(name)s msg="%(message)s"',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    root.handlers.clear()
    root.addHandler(handler)


# agentx-tui 入口：解析 --replay 引數後啟動 TUI 應用
def main() -> None:
    parser = argparse.ArgumentParser(prog="agentx-tui", description="AgentX TUI")
    parser.add_argument(
        "--replay",
        metavar="RUN_ID",
        help="Replay events from a past run on connect",
    )
    args = parser.parse_args()

    config = get_config()
    _setup_logging(config.logging.level)
    app = KamaTuiApp(config.host, config.port, replay_run_id=args.replay)
    app.run()


if __name__ == "__main__":
    main()
