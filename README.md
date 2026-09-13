<div align="center">

# 🤖 AgentX

**一套可觀察、可治理、可擴充的本地 AI Agent 執行環境。**

以 Python 實作完整 ReAct 迴圈，透過常駐 Core、CLI 與 TUI 串接工具呼叫、權限審批、事件流、長期會話、上下文壓縮、Skills、Subagents 與 MCP。

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-FFCC00)
![Anthropic](https://img.shields.io/badge/LLM-Anthropic-D97757)
![Tests](https://img.shields.io/badge/Tests-pytest-0A9EDC?logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

</div>

---

## 📖 專案介紹

一般 AI Demo 通常把「接收輸入、呼叫模型、顯示答案」全部塞在同一個程式裡，難以處理長時間任務、多個客戶端、權限審批與中斷恢復。

AgentX 將真正執行任務的能力放進常駐的 `agentx-core`，CLI 與 TUI 都只是透過 TCP IPC 連線的客戶端。模型每一步的推理、工具呼叫、權限決策與 token 使用量都會成為事件，因此能即時顯示、寫入 JSONL，並在斷線後重新播放。

### 核心功能

- **ReAct Agent Loop**：支援模型思考、工具呼叫、結果回填與多步任務執行。
- **Daemon + 多客戶端**：Core 持續執行，CLI 與 TUI 可同時訂閱同一份事件流。
- **型別化 IPC**：使用 JSON-RPC 2.0 + NDJSON，命令回應與事件推送共用 TCP 連線。
- **即時 TUI**：顯示串流 token、工具呼叫、執行狀態、權限審批與上下文水位。
- **工具安全**：先驗證參數，再依策略允許、拒絕或交由使用者決定。
- **可恢復會話**：儲存 thread、notes、run events 與 trace，支援斷線重連和事件重播。
- **上下文治理**：三層 Context、工具結果截斷、手動與自動 Compact。
- **多 Agent 協作**：以 planner、executor、reviewer 子 Agent 拆分複雜任務。
- **Skills 工作流程**：用 `/review`、`/orchestrate` 等斜線命令套用固定流程與工具白名單。
- **MCP 工具擴充**：將外部 MCP Server 工具接入既有 ToolRegistry、權限與事件鏈路。

---

## 👤 我的角色

> 個人 AI Agent 系統專案

我負責將原始教學架構整理為獨立的 AgentX 專案，完成品牌與套件命名統一、繁體中文在地化、TUI 中文輸入修正、文件重構與測試環境整理。

主要工作範圍：

- **核心執行環境**：AgentRunner、AgentLoop、LLM Provider 與 ToolRegistry。
- **程式間通訊**：TCP、JSON-RPC 2.0、NDJSON 與事件廣播。
- **互動介面**：Textual TUI、串流輸出、權限選擇與中文輸入。
- **可靠性機制**：Session、JSONL 記錄、Trace、重連、Replay 與 Compact。
- **擴充能力**：Skills、Subagents、角色工具邊界與 MCP。

---

## 💡 解決的問題

- **任務不中斷**：TUI 關閉或重新連線時，Core 中的任務仍可持續執行。
- **過程可追蹤**：不只顯示最後答案，也儲存每個 Run 的事件與完整 Trace。
- **工具可治理**：具有副作用的操作必須經過權限策略，避免模型直接執行危險命令。
- **長會話可續航**：系統會顯示 Context 水位，並可將歷史壓縮成可接續的交接摘要。
- **複雜任務可分工**：父 Agent 負責協調，子 Agent 依角色進行規劃、執行與審查。
- **外部能力可插拔**：MCP 工具可直接加入既有執行鏈路，不必修改 AgentLoop。

---

## 🛠 技術棧

**Python 3.12** · **asyncio** · **Anthropic SDK** · **Pydantic v2** · **Textual** · **Rich** · **JSON-RPC 2.0** · **NDJSON** · **MCP** · **pytest** · **Ruff** · **mypy** · **uv**

---

## 🏗 系統架構

```text
                    ┌──────────────────────┐
                    │   agentx-core daemon │
                    │   127.0.0.1:7437     │
                    └──────────┬───────────┘
                               │
                 JSON-RPC 2.0 + NDJSON / TCP
                               │
                    ┌──────────┴──────────┐
                    │                     │
               agentx CLI           agentx-tui
                                          │
使用者目標                                │ 即時事件
    ↓                                     │
SessionManager → AgentRunner → AgentLoop  │
                              ├─ LLM Provider
                              ├─ ToolRegistry ── MCP Tools
                              ├─ PermissionManager
                              └─ EventBus ───────┬─ TUI
                                                ├─ events.jsonl
                                                └─ TraceWriter
```

一次任務的主要流程：

```text
CLI / TUI 接收指令
↓
讀取設定並連接 Core
↓
透過 TCP 傳送 JSON-RPC / NDJSON
↓
Core 驗證 Request
↓
method 路由到 Handler
↓
AgentLoop 呼叫模型與工具
↓
EventBus 廣播並保存事件
↓
CLI / TUI 驗證 Response 並顯示結果
```

---

## 📂 專案結構

```text
AI-Agent/
├── src/agentx/
│   ├── cli/                    # CLI 指令與輸出
│   ├── tui/                    # Textual 終端介面
│   └── core/
│       ├── agents/             # planner / executor / reviewer 設定
│       ├── bus/                # JSON-RPC 命令、事件與 envelope
│       ├── compact/            # 上下文壓縮
│       ├── events/             # EventBus 與 JSONL Writer
│       ├── llm/                # Anthropic Provider 與串流回應
│       ├── mcp/                # MCP Client、Manager 與工具包裝
│       ├── permissions/        # 權限策略、審批與持久化
│       ├── session/            # 會話、Thread、Notes 與 Run
│       ├── skills/             # 斜線命令工作流程
│       ├── subagent/           # 子 Agent 與背景任務
│       ├── tools/              # 內建工具與 ToolRegistry
│       └── transport/          # TCP Socket Client / Server
├── tests/
│   ├── unit/                   # 單元測試
│   └── integration/            # 真實程式間通訊測試
├── scripts/                    # 協議文件產生器
├── WIRE_PROTOCOL.md            # 自動產生的 IPC 協議文件
├── RUNBOOK.md                  # 維運與故障排除
├── pyproject.toml
└── Makefile
```

---

## 🚀 快速開始

### 1. 安裝環境

需要 Python 3.12 與 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/poweichen00/AI-Agent.git
cd AI-Agent
uv sync
cp .env.example .env
```

在 `.env` 填入：

```bash
ANTHROPIC_API_KEY=你的_API_Key
```

### 2. 啟動 AgentX

終端 A 啟動 Core：

```bash
uv run agentx-core
```

終端 B 啟動 TUI：

```bash
uv run agentx-tui
```

也可以用 CLI 觸發單次任務：

```bash
uv run agentx run --goal "用一句話介紹你自己"
```

### 3. 驗證 Skills 與 Subagents

在 TUI 輸入：

```text
/review src/agentx/core/loop.py
```

測試多 Agent 工作流程：

```text
/orchestrate 分析 src/agentx/core/runner.py 的重構風險，不要修改任何檔案
```

---

## 🧪 品質檢查

```bash
# 單元測試
uv run pytest tests/unit -v

# 全部測試
uv run pytest

# 程式風格與靜態型別
uv run ruff check src tests scripts
uv run mypy src

# 確認 IPC 文件與模型同步
uv run python scripts/gen_protocol_doc.py --check
```

也可以執行：

```bash
make test
make lint
```

---

## 💾 執行資料

AgentX 預設將本機狀態儲存於：

```text
~/.agentx/
├── config.toml                 # 全域設定
├── context.md                  # 全域 Context
├── policy.toml                 # 持久化權限決策
├── logs/core.log               # Core 日誌
├── traces/daemon.jsonl         # 系統 Trace
└── sessions/<session_id>/
    ├── thread.jsonl            # 對話歷史
    ├── notes.md                # Session 備註
    ├── summary_*.md            # Compact 摘要
    └── runs/<run_id>/events.jsonl
```

`.env`、API Key 與 `~/.agentx/` 都不會提交至 Git。

---

## 🔌 MCP 設定範例

在 `~/.agentx/config.toml` 加入：

```toml
[[mcp.servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

重新啟動 Core 後，外部工具會以 `filesystem__工具名稱` 的形式註冊，並沿用 AgentX 的工具白名單、權限審批、錯誤分類與事件顯示。

---

## 📫 聯絡方式

**poweichen00** — [GitHub](https://github.com/poweichen00) · [專案原始碼](https://github.com/poweichen00/AI-Agent)

---

## 📄 授權

本專案使用 [MIT License](LICENSE)。衍生與修改內容仍保留原始專案的授權聲明。
