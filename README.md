# mini-harness v2 — 多 Agent 运行时

> "Agent 的 Harness 就像操作系统的内核 — 你感觉不到它，但没有它 Agent 就跑不起来。"

**mini-harness** 从零实现了多 Agent 运行时的九大核心组件。不到 1200 行代码，无外部框架依赖，是理解 Agent 基础设施的最佳起点。

---

## 为什么选择 mini-harness？

| | LangChain/LangGraph | CrewAI | mini-harness |
|------|:--:|:--:|:--:|
| 依赖量 | 50+ 包 | 20+ 包 | 2 个（Python 标准库 + tiktoken） |
| 学习曲线 | 陡峭 | 中等 | 平缓（一个下午读完源码） |
| 多 Agent | LangGraph 需手动组合 | 内置 Crew | 内置编排者-专家 |
| 可观测性 | 需要 LangSmith | 基础日志 | SQLite 全链路追踪 + 专家性能面板 |
| 适合场景 | 生产级复杂编排 | 快速原型 | 学习 Agent 原理 + 中小型项目 |

**如果你想要**：理解 Agent 运行时内核、快速把多个 AI 工具串成协作网络、在简历上展示 Agent 架构能力 — mini-harness 就是为你准备的。

---

## 快速开始

```bash
# 安装
pip install -r requirements.txt

# 运行 v1 演示（单 Agent 六大组件）
py demo.py

# 运行 v2 演示（多 Agent 协作）
py demo_v2.py

# 运行测试
pytest tests/ -v
```

## 5 分钟上手

```python
from harness import AgentHarness, Expert, Message

# 1. 创建 Harness
harness = AgentHarness(
    session_db="sessions.db",
    trace_db="traces.db",
    max_tokens=8000,
)

# 2. 注册工具
harness.register_tool(
    name="calculator",
    description="执行数学计算",
    parameters={"expression": {"type": "string", "description": "算式"}},
    fn=lambda expression: str(eval(expression)),
    category="safe",
)

# 3. 注册专家（v2 新增）
harness.register_expert(Expert(
    name="code_reviewer",
    description="审查代码质量，发现潜在 bug",
    domain=["code", "quality"],
    capabilities=["代码审查", "Bug 检测"],
    fn=my_code_review_function,
))

# 4. 注入 LLM
def my_llm(messages: list[Message], tools_desc: str) -> str:
    response = call_api(messages, tools_desc)  # DeepSeek / GPT / Claude
    return response

harness.set_llm(my_llm)

# 5a. 单 Agent 运行（v1 兼容）
result = harness.run("帮我算 123 * 456")

# 5b. 多 Agent 运行（v2 新增）
result = harness.run_multi(
    "审查代码质量 + 安全扫描 + 编写测试，重点关注安全性",
    user_priorities=["安全性"],
)
print(result["report"])  # 带来源标注的最终报告
print(result["stats"])   # 执行统计
print(result["gaps"])    # 能力缺口

# 6. 查看专家性能面板
perf = harness.expert_performance()
for p in perf:
    print(f"{p['expert_id']}: {p['calls']}次调用, {p['total_ms']:.0f}ms")

harness.close()
```

---

## 架构

```
                       用户任务
                          |
                    ┌─────▼──────┐
                    │ Orchestrator│  v2 新增
                    │ 拆解→匹配→调度│
                    └──┬───┬───┬──┘
                       │   │   │
              ┌────────▼┐ ┌▼───▼──┐ ┌────────▼┐
              │ Expert A │ │Expert B│ │ Expert C │
              │ (代码审查) │ │(安全)  │ │ (测试)   │
              └────┬─────┘ └───┬───┘ └────┬─────┘
                   │           │          │
              ┌────▼───────────▼──────────▼────┐
              │       ResultSynthesizer        │ v2 新增
              │    去重 → 排序 → 来源标注       │
              └───────────────┬───────────────┘
                              │
                        最终报告（带来源标注）
```

### 六大基础组件（v1）

```
用户输入
  → [Recovery] 保存检查点
  → [SessionStore] 加载/追加消息
  → [Compressor] token 超限？压缩旧消息
  → [ToolRegistry] 拼工具描述到 Prompt
  → [LLM] 调用大模型
  → 解析输出：是否调工具？
       ├─ 不调工具 → 最终回复
       └─ 调工具：
            → [PermissionGate] 权限检查
            → [ToolRegistry] 执行工具
            → [Tracer] 记录每步
            → 回到循环
```

---

## 九大组件一览

| # | 组件 | v1/v2 | 职责 | 对应业界方案 |
|:--:|------|:--:|------|------|
| 1 | **ToolRegistry** | v1 | 工具注册、Schema 管理、LLM 格式导出 | MCP Tool 列表 |
| 2 | **PermissionGate** | v1↑ | 工具权限 + Agent 间调用权限 | Claude Code 权限弹窗 |
| 3 | **SessionStore** | v1↑ | 树形会话持久化（SQLite） | LangGraph Checkpoint |
| 4 | **Compressor** | v1↑ | 分支级上下文压缩 | Token 爆炸专题方案 |
| 5 | **Tracer** | v1↑ | 多 Agent 因果追踪 + 专家性能面板 | LangSmith |
| 6 | **Recovery** | v1↑ | 分支级状态恢复 | A2A Task 状态追踪 |
| 7 | **ExpertRegistry** | v2 | 专家注册、领域匹配、能力目录 | CrewAI Agent Registry |
| 8 | **ResultSynthesizer** | v2 | 结果合成、去重、优先级排序 | — |
| 9 | **Orchestrator** | v2 | 任务拆解、DAG 调度、缺口检测 | AutoGen / LangGraph Supervisor |

---

## 项目结构

```
mini-harness/
├── harness/
│   ├── __init__.py          # 包入口（v2 导出所有组件）
│   ├── tool_registry.py     # 组件 1：工具注册表
│   ├── permission.py        # 组件 2：权限门禁
│   ├── session.py           # 组件 3：会话存储
│   ├── compressor.py        # 组件 4：上下文压缩
│   ├── tracer.py            # 组件 5：日志追踪
│   ├── recovery.py          # 组件 6：状态恢复
│   ├── expert.py            # 组件 7：专家注册表（v2 新增）
│   ├── synthesizer.py       # 组件 8：结果合成器（v2 新增）
│   ├── orchestrator.py      # 组件 9：编排者引擎（v2 新增）
│   └── harness.py           # 主入口：组合九大组件
├── tests/
│   ├── test_expert.py       # Expert + ExpertRegistry 测试（13 条）
│   ├── test_orchestrator.py # Orchestrator 测试（8 条）
│   └── test_synthesizer.py  # ResultSynthesizer 测试（8 条）
├── docs/
│   └── decisions/
│       ├── 001-orchestrator-expert-topology.md
│       └── 002-llm-fallback-strategy.md
├── .github/workflows/ci.yml # CI/CD（ruff + mypy + pytest）
├── demo.py                  # v1 六大组件演示
├── demo_v2.py               # v2 多 Agent 验收演示
├── requirements.txt
├── CHANGELOG.md
└── README.md
```

---

## 设计原则

1. **每个组件可独立使用** — 不需要 Harness 也能单独用任何一个组件
2. **可插拔** — 不需要某个功能？不设对应参数即可，自动降级
3. **无框架依赖** — 核心只依赖 Python 标准库 + sqlite3
4. **可观察** — Tracer 同时写控制台和 SQLite，既能实时看也能事后查
5. **渐进式复杂度** — v1 单 Agent 够用就不升级；需要多 Agent 时注册专家即可

## 设计取舍

| 选择 | 理由 |
|------|------|
| 编排者-专家 vs 管线式/辩论式 | 工业界主流，扩展性强，面试最能聊深度（[ADR-001](docs/decisions/001-orchestrator-expert-topology.md)） |
| LLM 兜底 vs 硬失败 | 不阻塞流程，同时告知能力缺口引导完善（[ADR-002](docs/decisions/002-llm-fallback-strategy.md)） |
| SQLite vs Redis/Postgres | 零依赖，单机够用，适合中小型项目 |
| 字符串匹配 vs 向量语义匹配 | 字符串匹配零依赖、可解释；向量匹配需要 embedding 模型，留给用户集成 |
| Python 标准库 vs 引入框架 | 学习目的优先，理解原理后再用 LangChain/CrewAI 更有底气 |

---

## 测试

```bash
pytest tests/ -v    # 29 条测试，覆盖 3 个 P0 功能的核心路径
```

覆盖范围：
- ExpertRegistry: 注册/查找/匹配/异常/领域筛选（10 条）
- Orchestrator: 拆解/匹配/缺口检测/DAG 执行/完整流水线（8 条）
- ResultSynthesizer: 合成/去重/排序/格式/空结果（8 条）

---

## License

MIT

---

*mini-harness v2 — 从单 Agent 到多 Agent 协作，九大组件，零框架依赖。*
