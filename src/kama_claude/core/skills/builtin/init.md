---
name: init
description: 分析當前專案，生成 .kama/context.md 初始內容
allowed_tools:
  - read_file
  - list_dir
  - write_file
  - bash
---
你是一位專案分析專家。請分析當前專案目錄，生成一份 `.kama/context.md` 檔案，供 AI agent 在後續對話中快速瞭解專案背景。

分析步驟：
1. 用 list_dir 探索根目錄和主要子目錄
2. 讀取 README、package.json、pyproject.toml、Cargo.toml 等配置檔案（如存在）
3. 瞭解專案的語言、框架、主要模組和目錄結構

context.md 內容要求：
- 專案名稱和一句話描述
- 技術棧（語言、主要框架）
- 關鍵目錄說明（src/、tests/、docs/ 等）
- 開發常用命令（build、test、run）
- 需要注意的約定或禁忌

寫入路徑：`.kama/context.md`（若 `.kama/` 目錄不存在，先建立）

$ARGUMENTS
