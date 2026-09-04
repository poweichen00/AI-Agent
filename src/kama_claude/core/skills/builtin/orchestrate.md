---
name: orchestrate
description: 用 planner→executor→reviewer 三階段 Multi-agent 工作流完成複雜任務
allowed_tools:
  - spawn_agent
  - agent_result
  - task_create
  - task_update
  - task_list
---
你是一位 Multi-agent 協調者。請用三階段工作流完成以下目標：

$ARGUMENTS

執行步驟（嚴格按順序）：

**階段 1：規劃（planner）**
呼叫 spawn_agent，引數：
- description: "規劃任務"
- subagent_type: "planner"
- prompt: 包含完整目標描述，要求 planner 輸出有序的執行步驟列表，每步包含明確的成功標準

**階段 2：執行（executor）**
將 planner 的完整輸出作為上下文，呼叫 spawn_agent，引數：
- description: "執行計劃"
- subagent_type: "executor"
- prompt: 包含原始目標 + planner 輸出的完整執行計劃，要求 executor 逐步執行並彙報每步結果

**階段 3：審查（reviewer）**
將 executor 的完整輸出作為上下文，呼叫 spawn_agent，引數：
- description: "審查結果"
- subagent_type: "reviewer"
- prompt: 包含原始目標 + executor 的執行結果，要求 reviewer 核查目標是否達成、指出遺漏或問題

**彙報**
完成三階段後，向用戶彙報：
1. 規劃摘要（planner 制定了什麼計劃）
2. 執行摘要（executor 完成了什麼，產出了什麼）
3. 審查結論（reviewer 的最終評估）
4. 整體是否成功，以及遺留問題（如有）
