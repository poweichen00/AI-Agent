# 運維手冊（RUNBOOK）

## 日常操作

### 啟動守護程式

```bash
uv run agentx-core
```

預設監聽 `127.0.0.1:7437`，按 `Ctrl+C` 優雅退出。

### 驗證連通

```bash
uv run agentx ping
# → pong server=0.0.1 uptime=12ms latency=2ms
```

### 停止守護程式

```bash
kill $(pgrep -f agentx-core)
```

---

## 配置

優先順序（低 → 高）：**內建預設值 → `~/.agentx/config.toml` → `.env` → 系統環境變數**。目前沿用舊資料目錄與 `AGENTX_*` 環境變數，以保留既有執行記錄與配置。

### `~/.agentx/config.toml`

```toml
[core]
host = "127.0.0.1"
port = 7437

[logging]
level  = "INFO"
file   = "~/.agentx/logs/core.log"
format = "text"    # "text" | "json"
```

### `.env`

從 `.env.example` 複製後修改，存放本機配置與金鑰（不提交 git）：

```bash
cp .env.example .env
```

### 系統環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `AGENTX_CONFIG` | `~/.agentx/config.toml` | 覆蓋配置檔案路徑 |
| `AGENTX_HOST` | `127.0.0.1` | TCP 監聽地址 |
| `AGENTX_PORT` | `7437` | TCP 監聽埠 |
| `AGENTX_LOG_LEVEL` | `INFO` | 日誌級別（DEBUG / INFO / WARNING / ERROR） |
| `AGENTX_LOG_FILE` | `~/.agentx/logs/core.log` | 日誌檔案路徑（留空則僅輸出 stderr） |
| `AGENTX_LOG_FORMAT` | `text` | 日誌格式（`text` 或 `json`） |

---

## 開發

```bash
uv run ruff check src tests scripts   # lint
uv run mypy src                       # 型別檢查
uv run pytest tests/ -v               # 全量測試
uv run pytest tests/unit/ -v         # 僅單元測試（無需啟動 daemon）

make docs                             # 重新生成 WIRE_PROTOCOL.md
make verify-s0                        # 完整驗證（lint + 型別 + 測試 + 協議同源檢查）
```

---

## 日誌

```bash
tail -f ~/.agentx/logs/core.log
```

---

## 常見錯誤

| 報錯 | 原因 | 處理 |
|------|------|------|
| `core already running at 127.0.0.1:7437` | 已有守護程式在執行 | `kill $(pgrep -f agentx-core)` |
| `core not running` | 未啟動守護程式 | `uv run agentx-core` |
| `Address already in use` | 埠被其他程式佔用 | `AGENTX_PORT=8000 uv run agentx-core` |
| `Config error: AGENTX_PORT must be an integer` | `.env` 或環境變數中埠值非整數 | 檢查 `AGENTX_PORT` 的值 |
