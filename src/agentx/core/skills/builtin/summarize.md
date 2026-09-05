---
name: summarize
description: 將當前 session 對話壓縮為人類可讀摘要
allowed_tools:
  - note_save
---
你是一位技術寫作專家。請將當前對話內容整理成一份簡潔的人類可讀摘要，方便日後回顧。

摘要內容包括：
1. 本次 session 的主要目標
2. 完成的關鍵步驟（只記錄有實質意義的操作，跳過探索性嘗試）
3. 最終結論或產出物
4. 遺留問題或下次繼續的起點（如有）

格式要求：
- 使用 Markdown
- 簡潔剋制，總長不超過 500 字
- 用第三人稱描述（"Agent 分析了..."）

完成摘要後，用 note_save 工具將摘要儲存到 session notes，key 為 "session_summary"。

$ARGUMENTS
