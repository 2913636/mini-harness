# ADR-005: 选择零框架依赖作为设计基础

## 状态

已采纳（Accepted）

## 背景

mini-harness 的定位是"理解 Agent 运行时原理的最佳起点"。需要在"降低学习门槛"和"借助现有框架快速开发"之间做选择。

## 决策

**核心运行时零框架依赖（仅 Python 标准库 + sqlite3 + tiktoken），对外部 LLM API 的调用使用轻量级适配器。**

## 考虑的方案

### 方案 A：零框架依赖（✅ 采纳）

- 代码量少（~1200 行），一个下午读完
- 每个组件独立可理解，便于面试展示
- 无框架版本锁定问题，长期可维护
- 用户理解原理后，迁移到 LangChain/CrewAI 更有底气

### 方案 B：基于 LangChain/LangGraph（❌ 否决）

- 50+ 依赖包，版本冲突频繁
- 学习曲线陡峭，掩盖了 Agent 运行时的核心原理
- 重量级抽象（Runnable、Chain、LCEL），对教学目的过度
- 但 LangGraph 的 Checkpoint 和 StateGraph 设计值得学习

### 方案 C：基于 CrewAI（❌ 否决）

- 20+ 依赖包
- 内置的 Crew/Agent/Task 抽象虽然直观，但限制了用户理解底层机制
- mini-harness 的目标是展示"怎么做"而非"用什么做"

## 影响

- `requirements.txt` 仅包含 3 个外部依赖：`openai`、`python-dotenv`、`tiktoken`
- 所有核心组件不依赖任何 AI 框架
- LLM 调用通过 `llm_client.py` 适配器与 DeepSeek API 通信（使用 OpenAI 兼容 SDK）
- 用户可以轻松替换为其他 LLM 提供商（Claude、GPT 等）
