# mini-harness — 从零搭建的 Agent 运行时

> "Agent 的 Harness 就像操作系统的内核——你感觉不到它，但没有它 Agent 就跑不起来。"

**mini-harness** 从零实现了 Agent 运行时的六大核心组件。不到 800 行代码，无外部框架依赖，是理解 Agent 基础设施的最佳起点。

---

## 🧩 六大组件

| # | 组件 | 对应 Claude Code | 对应你学过的 |
|:--:|------|------|------|
| 1 | **Tool Registry** 工具注册表 | MCP Tool 列表 | FastMCP Server |
| 2 | **Permission Gate** 权限门禁 | "是否执行这个命令？"弹窗 | `interrupt_before` |
| 3 | **Session Store** 会话存储 | 关闭重开对话还在 | LangGraph Checkpoint |
| 4 | **Compressor** 上下文压缩 | 聊太长自动摘要 | Token爆炸专题 E1-E6 |
| 5 | **Tracer** 日志追踪 | 每步 token/耗时记录 | `@traceable`, LangSmith |
| 6 | **Recovery** 状态恢复 | 断网后从断点继续 | LangGraph Checkpoint 恢复 |

---

## 🚀 快速开始

```bash
# 安装（可选依赖，无则用字符估算）
pip install -r requirements.txt

# 运行演示
py demo.py
```

---

## 📖 使用方式

```python
from harness import AgentHarness, Message

# 1. 创建 Harness
harness = AgentHarness(
    session_db="sessions.db",   # 会话持久化
    trace_db="traces.db",       # 追踪持久化
    max_tokens=8000,            # token 上限
)

# 2. 注册工具
harness.register_tool(
    name="calculator",
    description="执行数学计算",
    parameters={"expression": {"type": "string", "description": "算式"}},
    fn=lambda expression: str(eval(expression)),
    category="safe",  # 安全工具 → 自动放行
)

harness.register_tool(
    name="search",
    description="联网搜索",
    parameters={"query": {"type": "string", "description": "搜索词"}},
    fn=my_search_function,
    category="network",  # 网络工具 → 需要确认
)

# 3. 注入 LLM
def my_llm(messages: list[Message], tools_desc: str) -> str:
    # 调用 DeepSeek / GPT / Claude API
    response = call_api(messages, tools_desc)
    return response

harness.set_llm(my_llm)

# 4. 运行
harness.start_session()
result = harness.run("帮我算 123 * 456 并搜索一下 AI Agent")
print(result)

# 5. 查看统计
print(harness.stats())
harness.close()
```

---

## 🎯 调用流程

```
用户输入
  → [Recovery] 保存检查点
  → [Session Store] 加载/追加消息
  → [Compressor] token 超限？压缩旧消息
  → [Tool Registry] 拼工具描述到 Prompt
  → [LLM] 调用大模型
  → 解析输出：是否调工具？
       ├─ 不调工具 → 最终回复
       └─ 调工具：
            → [Permission Gate] 权限检查
            → [Tool Registry] 执行工具
            → [Tracer] 记录每步
            → 回到循环（最多 5 次迭代）
```

---

## 🏗️ 项目结构

```
mini-harness/
├── harness/
│   ├── __init__.py          # 包入口
│   ├── tool_registry.py     # 组件 1：工具注册表
│   ├── permission.py        # 组件 2：权限门禁
│   ├── session.py           # 组件 3：会话存储（SQLite）
│   ├── compressor.py        # 组件 4：上下文压缩
│   ├── tracer.py            # 组件 5：日志追踪
│   ├── recovery.py          # 组件 6：状态恢复
│   └── harness.py           # 主入口：组合六大组件
├── demo.py                  # 完整演示
├── requirements.txt
└── README.md
```

---

## 💡 设计原则

1. **每个组件可独立使用** — 不需要 Harness 也能单独用任何一个组件
2. **可插拔** — 不需要压缩？不设 `summarize_fn` 即可，自动降级为截断
3. **无框架依赖** — 核心只依赖 Python 标准库 + sqlite3
4. **可观察** — Tracer 同时写控制台和 SQLite，既能实时看也能事后查

---

## 🔗 面试价值

这个项目直接对应面试中的系统设计题：「设计一个 Agent 系统」

答案就是这六大组件——你可以当场画出架构图，逐个解释设计考量。

---

*mini-harness — Agent 运行时六大组件 | MIT License*
