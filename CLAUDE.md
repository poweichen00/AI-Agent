# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install / sync dependencies
uv sync

# Lint
uv run ruff check src tests scripts
uv run mypy src

# Tests
uv run pytest tests/unit -v           # unit only (fast, no daemon)
uv run pytest tests/integration -v    # needs no running daemon; fixture spawns one
uv run pytest tests/ -v               # all

# Single test
uv run pytest tests/unit/test_envelope.py::test_request_roundtrip -v

# Regenerate WIRE_PROTOCOL.md after changing bus models
uv run python scripts/gen_protocol_doc.py

# Verify WIRE_PROTOCOL.md is in sync (used in CI equivalent)
uv run python scripts/gen_protocol_doc.py --check

# Run daemon manually
uv run agentx-core                        # foreground; Ctrl+C to stop
AGENTX_PORT=8000 uv run agentx-core        # override port

# Send a ping
uv run agentx ping
uv run agentx --version
```

## Architecture

This is a **dual-process** local AI agent system. `agentx-core` is a persistent daemon; `agentx` and `agentx-tui` are clients that connect to it over TCP.

```
agentx-core (daemon)
  └─ listens on 127.0.0.1:7437 (TCP)
       ↑ JSON-RPC 2.0 NDJSON
agentx (CLI)   agentx-tui (TUI, S2+)
```

**`agentx-tui` is the primary frontend.** All user-facing work on task management, observability, and interaction should be designed for and validated in the TUI first. The `agentx` CLI exists only for quick scripted testing and debugging — it is not a product surface. When implementing features that touch the user interface, invest in the TUI layout, event rendering, and keyboard interactions. Do not shortcut TUI work by pointing to the CLI as an alternative.

### Protocol layer (`src/agentx/core/bus/`)

All IPC messages are typed pydantic v2 models with a **discriminated union on the `type` field**. This is the contract boundary — adding a new command or event means adding a new model class to `commands.py` or `events.py` and extending the `Command`/`Event` union.

- `envelope.py` — `JsonRpcRequest`, `JsonRpcSuccess`, `JsonRpcError`, error code constants, `make_error()`
- `commands.py` — `Command` union; currently only `PingCommand` + `PongResult`
- `events.py` — `Event` union; currently only `CoreStartedEvent`

`WIRE_PROTOCOL.md` is **generated** from these models by `scripts/gen_protocol_doc.py`. Always regenerate and commit it after changing bus models.

### Transport layer (`src/agentx/core/transport/`)

- `socket_server.py` — TCP server (`asyncio.start_server`); reads NDJSON lines, dispatches to registered `CommandHandler`s, handles JSON-RPC error cases. On `start()`, probes `host:port` first — errors if another daemon is already listening. Handlers registered via `server.register("method.name", handler_fn)`.

### Config (`src/agentx/core/config.py`)

Four-tier priority: **built-in defaults → `~/.agentx/config.toml` → `.env` → env vars**.

S0 keys: `host` (default `127.0.0.1`), `port` (default `7437`), `log_level`, `log_file`. Config file is silently skipped if absent; unknown keys cause a hard exit.

Relevant env vars: `AGENTX_CONFIG`, `AGENTX_HOST`, `AGENTX_PORT`, `AGENTX_LOG_LEVEL`, `AGENTX_LOG_FILE`, `AGENTX_LOG_FORMAT`.

### Daemon entry (`src/agentx/core/app.py`)

`CoreApp.run()` is the single async entry point: loads config → sets up logging → creates `SocketServer` → registers handlers → waits for `SIGINT`/`SIGTERM` → calls `server.stop()`. Adding new handlers: instantiate a handler method on `CoreApp` and call `server.register()`.

### Testing

Integration tests in `tests/conftest.py` spawn a real daemon subprocess using a random free port (via `free_port` fixture). The fixture finds a free port, releases it, passes it to the daemon via `AGENTX_PORT`, then polls `asyncio.open_connection` until the daemon is ready.

### Code style

All functions must have a **single-line Chinese comment** immediately above the `def` line explaining what the function does. Example:

```python
# 傳送 JSON-RPC 響應並重新整理寫緩衝區
async def _send(self, writer: asyncio.StreamWriter, msg: BaseModel) -> None:
    ...
```

Do not write multi-line docstrings; one concise Chinese line is enough.

**Test functions** require **two Chinese comment lines** immediately above the `def` line:

```python
# 功能：驗證 publish 後訂閱者能收到事件物件
# 設計：用內聯 handler 收集事件引用，斷言 is 而非 ==，排除序列化中間步驟的幹擾
async def test_publish_reaches_subscriber() -> None:
    ...
```

- `# 功能：` — 該測試驗證的具體行為或不變式，一句話說清楚"測什麼"
- `# 設計：` — 為什麼選擇這種測試方式：覆蓋了什麼邊界條件、為什麼用這個 stub/fixture、這種斷言方式相比其他方式的優勢

兩行註釋缺一不可。功能行讓讀者 5 秒內判斷測試意圖；設計行讓讀者理解測試背後的決策，而非只看到操作步驟。

### Design docs (outside the repo)

The planning documents live in `../docs/` (sibling of this repo, not committed here):
- `agent_development_plan.md` — staged development roadmap S0–S8
- `s0_implementation_plan.md` — detailed S0 decisions and rationale
- `agent_functional_outline.md` — full feature catalogue
