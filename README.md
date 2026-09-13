<div align="center">

# AgentX

**本機執行的 AI Agent Runtime，讓長時間任務可觀察、可審批、可恢復。**

AgentX 以常駐 Core 執行 ReAct Agent，並透過 CLI 或 TUI 操作同一份會話與即時事件流。

![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![TUI](https://img.shields.io/badge/TUI-Textual-FFCC00)
![LLM](https://img.shields.io/badge/LLM-Anthropic-D97757)
![License](https://img.shields.io/badge/License-MIT-yellow)

</div>

AgentX 將任務執行與操作介面分離：`agentx-core` 負責會話、模型呼叫、工具執行與事件保存；CLI 和 TUI 則作為客戶端連線到 Core。即使介面中途關閉，任務仍可繼續執行，重新連線後也能回放先前事件。

> [!WARNING]
> AgentX 可以執行終端指令與修改檔案。建議先在測試專案中使用、仔細確認權限提示，並避免直接在含有敏感資料的目錄執行。

## 快速開始

### 環境需求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Anthropic API Key

### 安裝

```bash
git clone https://github.com/poweichen00/AI-Agent.git
cd AI-Agent
uv sync
cp .env.example .env
```

在 `.env` 設定 API Key：

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### 啟動

終端 A 啟動 Core：

```bash
uv run agentx-core
```

終端 B 啟動 TUI：

```bash
uv run agentx-tui
```

進入 TUI 後直接輸入任務，例如：

```text
分析目前專案的測試覆蓋範圍，列出三個最需要補強的地方
```

若不使用 TUI，也可以從另一個終端執行單次任務：

```bash
uv run agentx run --goal "用一句話介紹你自己"
```

## 核心能力

- **持久化 Runtime**：Agent 在常駐 Core 中執行，不依附單一 CLI 或 TUI 行程。
- **即時事件流**：模型輸出、工具呼叫、權限決策與 token 用量都會即時顯示並寫入 JSONL。
- **工具權限控管**：工具參數會先經過驗證，再依規則自動允許、拒絕，或等待使用者確認。
- **可恢復會話**：保存對話、筆記、任務事件與 Trace，支援斷線重連和事件回放。
- **上下文治理**：提供三層 Context、工具結果截斷，以及手動與自動壓縮機制。
- **Skills 與多 Agent**：可透過斜線命令套用固定流程，並由 planner、executor、reviewer 分工。
- **MCP 擴充**：外部 MCP 工具可接入既有的工具註冊、權限與事件處理流程。

## 使用方式

| 指令 | 用途 |
| --- | --- |
| `uv run agentx-core` | 在前景啟動 Core |
| `uv run agentx-tui` | 開啟互動式 TUI |
| `uv run agentx ping` | 確認 Core 是否可連線 |
| `uv run agentx run --goal "<任務>"` | 執行單次任務 |
| `uv run agentx chat` | 開始多輪 CLI 對話 |
| `uv run agentx core start` | 在背景啟動 Core |
| `uv run agentx core status` | 查看 Core 狀態 |
| `uv run agentx core stop` | 停止背景 Core |
| `uv run agentx trace --follow` | 持續查看新的 Trace |
| `uv run agentx-tui --replay <run_id>` | 回放指定任務事件 |

Trace 也能依任務或層級篩選：

```bash
uv run agentx trace <run_id>
uv run agentx trace --layer ipc
uv run agentx trace --layer event
uv run agentx trace --layer llm
```

### Skills 與多 Agent

在 TUI 內輸入 `/` 可觸發 Skill。以下範例會啟動程式碼審查流程：

```text
/review src/agentx/core/loop.py
```

以下範例會讓多個子 Agent 分工分析：

```text
/orchestrate 分析 src/agentx/core/runner.py 的重構風險，不要修改任何檔案
```

## 運作原理

一次任務會經過以下流程：

1. CLI 或 TUI 將使用者指令傳送給常駐的 `agentx-core`。
2. Core 驗證 JSON-RPC Request，並依照 method 交給對應 Handler。
3. `SessionManager` 建立或延續會話，再由 `AgentRunner` 啟動任務。
4. `AgentLoop` 持續呼叫模型、執行內建工具或 MCP 工具，直到任務完成。
5. 可能改變系統狀態的工具會先經過 `PermissionManager`；需要確認時，由使用者決定是否允許執行。
6. `EventBus` 將事件即時推送給客戶端，同時寫入 `events.jsonl` 與 Trace。

CLI、TUI 與 Core 使用 TCP 傳輸 JSON-RPC 2.0 命令與 NDJSON 事件。完整訊息格式請參閱 [WIRE_PROTOCOL.md](WIRE_PROTOCOL.md)。

## 設定

設定值的優先順序由低到高為：程式預設值、`~/.agentx/config.toml`、專案內的 `.agentx/config.toml`、`.env`、目前行程的環境變數。

常用環境變數：

| 變數 | 用途 | 預設值 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Anthropic API Key | 無 |
| `AGENTX_LLM_DEFAULT_MODEL` | 預設模型 | `claude-sonnet-4-6` |
| `AGENTX_MAX_STEPS` | 單次任務最多步數 | `20` |
| `AGENTX_LOG_LEVEL` | 日誌層級 | `INFO` |
| `AGENTX_LOG_FORMAT` | 日誌格式：`text` 或 `json` | `text` |
| `AGENTX_TRACE_ENABLED` | 是否寫入 Trace | `true` |
| `AGENTX_PERMISSION_TIMEOUT_S` | 權限確認等待秒數 | `60` |
| `AGENTX_COMPACT_THRESHOLD` | 自動壓縮門檻；`0` 代表停用 | `0` |

若設定 `AGENTX_CONFIG`，AgentX 只會讀取指定的 TOML 設定檔，不再疊加全域與專案設定。

## 權限與安全

工具執行前會依序經過參數驗證與權限判斷：

- `ALLOW`：符合既有規則，直接執行。
- `DENY`：不符合安全規則，拒絕執行。
- `ASK`：暫停該次工具呼叫，等待使用者在 TUI 允許或拒絕。

使用者可選擇只套用一次，也可以將決定保存到 `~/.agentx/policy.toml`。權限管理能降低誤操作風險，但不能取代隔離環境、版本控制與敏感資料管理。

## MCP 工具

在 `~/.agentx/config.toml` 加入 MCP Server，例如：

```toml
[[mcp.servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

重新啟動 Core 後，工具會以 `filesystem__工具名稱` 的形式註冊，並沿用 AgentX 的工具白名單、權限判斷與事件紀錄。此範例需要本機已安裝 Node.js 與 `npx`。

## 執行資料

AgentX 預設將本機狀態存放在 `~/.agentx/`：

| 路徑 | 內容 |
| --- | --- |
| `config.toml` | 全域設定 |
| `context.md` | 全域 Context |
| `policy.toml` | 已保存的權限決定 |
| `logs/core.log` | Core 日誌 |
| `traces/daemon.jsonl` | 系統 Trace |
| `sessions/<session_id>/thread.jsonl` | 對話歷史 |
| `sessions/<session_id>/notes.md` | 會話筆記 |
| `sessions/<session_id>/summary_*.md` | Context 壓縮摘要 |
| `sessions/<session_id>/runs/<run_id>/events.jsonl` | 單次任務事件 |

`.env`、API Key 與 `~/.agentx/` 不會提交到 Git。

## 開發與驗證

```bash
# 單元測試
make test

# Ruff 與 mypy
make lint

# 整合測試
make integration-test

# 確認 IPC 文件與資料模型同步
uv run python scripts/gen_protocol_doc.py --check
```

執行全部測試：

```bash
uv run pytest
```

## 專案結構

```text
AI-Agent/
├── src/agentx/
│   ├── cli/                    # CLI 指令與輸出
│   ├── tui/                    # Textual 終端介面
│   └── core/
│       ├── agents/             # 子 Agent 角色設定
│       ├── bus/                # 命令與事件模型
│       ├── compact/            # 上下文壓縮
│       ├── events/             # EventBus 與 JSONL 寫入
│       ├── llm/                # 模型 Provider
│       ├── mcp/                # MCP Client 與工具包裝
│       ├── permissions/        # 權限規則與審批
│       ├── session/            # 會話、筆記與任務資料
│       ├── skills/             # 斜線命令工作流程
│       ├── subagent/           # 子 Agent 與背景任務
│       ├── tools/              # 內建工具與 ToolRegistry
│       └── transport/          # Socket Client 與 Server
├── tests/                      # 單元與整合測試
├── scripts/                    # 開發與文件工具
├── RUNBOOK.md                  # 維運與故障排除
├── WIRE_PROTOCOL.md            # IPC 協議文件
├── pyproject.toml
└── Makefile
```

## 延伸文件

- [WIRE_PROTOCOL.md](WIRE_PROTOCOL.md)：IPC 命令、回應與事件格式。
- [RUNBOOK.md](RUNBOOK.md)：日誌、診斷與常見故障處理。

## 授權

Copyright © 2026 [poweichen00](https://github.com/poweichen00)。本專案使用 [MIT License](LICENSE)。
