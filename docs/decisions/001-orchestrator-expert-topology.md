# ADR-001: 选择编排者-专家拓扑

**日期**：2026-07-01
**状态**：已采纳

## 背景

mini-harness v1 是单 Agent ReAct 循环。v2 需要支持多 Agent 协作。需要在多种多 Agent 拓扑中做出选择。

## 决策

选择**编排者-专家（Orchestrator-Expert）拓扑**。

## 考虑的方案

### 方案 A：管线式（Pipeline）
Agent A → Agent B → Agent C 串行。

- 优点：实现简单，流程明确
- 缺点：灵活性差，不支持并行，不适合复杂任务
- 否决原因：太基础，一个简单的 DAG 编排就覆盖了，不显技术深度

### 方案 B：辩论式（Debate）
多个 Agent 同时回答，互相质疑，投票/仲裁。

- 优点：新颖，能聊出 LLM 自校验话题
- 缺点：应用场景窄，token 消耗大
- 否决原因：工业界落地场景少，不适合作为项目展示

### 方案 C：编排者-专家（Orchestrator-Expert）
编排者拆解任务 → 匹配专家 → 调度执行 → 结果合成。

- 优点：工业界主流（CrewAI、AutoGen、LangGraph Supervisor 均为此模式），扩展性强，支持并行和依赖
- 缺点：编排者本身是单点，需要健壮的拆解和匹配逻辑
- **采纳**

### 方案 D：自主协作式（Autonomous）
多 Agent 自由交互，模拟社会行为。

- 优点：学术前沿
- 缺点：不可控，投入大产出小
- 否决原因：偏研究，不适合落地

## 影响

- 新增 Orchestrator 组件（~200 行），负责拆解/匹配/调度
- 新增 ExpertRegistry 组件，管理专家池
- 新增 ResultSynthesizer 组件，汇总多专家结果
- 六个 v1 组件需要升级以支持多 Agent 消息流

## 相关

- ADR-002: LLM 兜底策略
