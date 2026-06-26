#!/usr/bin/env python3
"""
mini-harness 演示：六大组件协同工作的完整流程

场景：用户让 Agent 帮忙算账、查天气、写文件
  - 计算器 → 安全工具，自动放行
  - 天气查询 → 网络工具，需要用户确认
  - 文件写入 → 文件工具，需要用户确认
  - 系统命令 → 默认拒绝

运行：
    py demo.py
"""

import os
import sys

# 确保能 import harness
sys.path.insert(0, os.path.dirname(__file__))

from harness import AgentHarness, Message


# ═══════════════════════════════════════
# 1. 模拟 LLM（因为本地没有真实 LLM）
# ═══════════════════════════════════════

def mock_llm(messages: list[Message], tools_desc: str) -> str:
    """
    模拟 LLM 的决策逻辑。
    真实场景替换为 DeepSeek API 调用。

    关键逻辑：如果最后一条消息是工具返回结果，停止调工具，给最终回复。
    """
    if not messages:
        return "你好，有什么可以帮你的？"

    last = messages[-1]

    # 工具已经返回结果 → 不要再调工具了，直接回复
    if last.role == "tool" and "计算结果" in last.content:
        return f"根据计算，{last.content}。还有其他需要吗？"
    if last.role == "tool" and "搜索结果" in last.content:
        return f"搜索结果：{last.content}。还需要了解更多吗？"
    if last.role == "tool" and "文件已写入" in last.content:
        return f"{last.content}。任务完成！"
    if last.role == "tool":
        return f"收到工具结果：{last.content[:100]}。任务完成。"

    content = last.content

    # 计算请求
    if any(op in content for op in ["+", "-", "*", "/", "算", "计算", "="]):
        import re
        nums = re.findall(r'\d+', content)
        if len(nums) >= 2:
            expr = f"{nums[-2]} + {nums[-1]}"
            return f'TOOL: calculator | args: {{"expression": "{expr}"}}'
        return f'TOOL: calculator | args: {{"expression": "{content}"}}'

    # 天气查询
    if "天气" in content or "weather" in content.lower():
        import re
        city_match = re.search(r'(?:在|查|的)?(北京|上海|深圳|长沙|杭州|南京\w*)', content)
        city = city_match.group(1) if city_match else "长沙"
        return f'TOOL: search | args: {{"query": "{city}天气"}}'

    # 搜索
    if "搜索" in content or "查一下" in content or "搜" in content:
        query = content.split("搜索")[-1].split("查一下")[-1].strip("：: ")
        return f'TOOL: search | args: {{"query": "{query}"}}'

    # 写文件
    if "写" in content or "保存" in content or "写入" in content:
        return f'TOOL: write_file | args: {{"path": "output.txt", "content": "这是 Agent 自动生成的内容。\\n基于用户请求：{content[:50]}"}}'

    # 系统命令（危险）
    if "执行" in content or "运行命令" in content:
        return f'TOOL: execute_command | args: {{"command": "echo hello"}}'

    # 默认：直接回复
    return f"收到你的消息：「{content}」。可用工具：计算器、天气查询、文件写入。需要我做什么？"


def mock_summarize(messages: list[Message]) -> str:
    """模拟摘要函数。真实场景替换为 LLM 调用。"""
    summary_parts = []
    for m in messages[:10]:  # 最多取 10 条做摘要
        role = "用户" if m.role == "user" else "助手" if m.role == "assistant" else m.role
        summary_parts.append(f"[{role}]: {m.content[:60]}")
    return "；".join(summary_parts) + "（旧对话摘要）"


# ═══════════════════════════════════════
# 2. 工具函数
# ═══════════════════════════════════════

def tool_calculator(expression: str) -> str:
    """安全计算器"""
    try:
        result = eval(expression, {"__builtins__": {}})  # 沙箱
        return f"计算结果: {expression} = {result}"
    except Exception as e:
        return f"计算错误: {e}"


def tool_search(query: str) -> str:
    """模拟搜索"""
    results = {
        "长沙天气": "长沙今日多云转晴，25-32°C，风力 3 级。",
        "北京天气": "北京今日晴，20-28°C，空气质量良。",
        "AI Agent": "AI Agent（人工智能代理）是一种能自主感知环境、做出决策、调用工具完成任务的智能系统。",
    }
    return results.get(query, f"搜索结果：「{query}」相关网页约 1,280,000 条。第一条：{query}是一个重要概念...")


def tool_write_file(path: str, content: str) -> str:
    """写文件（安全沙箱：只写 /tmp）"""
    safe_path = os.path.join(os.path.dirname(__file__), "output", os.path.basename(path))
    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
    with open(safe_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"文件已写入: {safe_path} ({len(content)} 字符)"


def tool_execute_command(command: str) -> str:
    """执行系统命令（高风险，默认被门禁拒绝）"""
    return f"命令已执行: {command}"


# ═══════════════════════════════════════
# 3. 组装 Harness
# ═══════════════════════════════════════

def build_harness():
    """构建完整的 Agent Harness"""
    harness = AgentHarness(
        session_db="demo_sessions.db",
        trace_db="demo_traces.db",
        max_tokens=2000,  # 设小一点，方便演示压缩
        keep_recent=4,
    )

    # 注册工具
    harness.register_tool(
        name="calculator",
        description="执行数学计算，支持 + - * /",
        parameters={"expression": {"type": "string", "description": "数学表达式，如 2+3*4"}},
        fn=tool_calculator,
        category="safe",
    )
    harness.register_tool(
        name="search",
        description="联网搜索信息",
        parameters={"query": {"type": "string", "description": "搜索关键词"}},
        fn=tool_search,
        category="network",
    )
    harness.register_tool(
        name="write_file",
        description="将内容写入文件",
        parameters={
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
        },
        fn=tool_write_file,
        category="file",
    )
    harness.register_tool(
        name="execute_command",
        description="执行系统命令（危险操作）",
        parameters={"command": {"type": "string", "description": "要执行的命令"}},
        fn=tool_execute_command,
        category="system",
    )

    # 设置 LLM
    harness.set_llm(mock_llm)
    harness.set_summarize_fn(mock_summarize)

    # 设置用户确认回调（自动拒绝，方便自动化演示）
    def confirm_callback(tool_name: str, reason: str) -> bool:
        print(f"      [GATE] 权限请求: {tool_name} | {reason}")
        print(f"      [GATE] 自动模式: 拒绝 (输入 N)")
        return False  # 自动拒绝，演示权限门禁效果

    harness.set_confirm_callback(confirm_callback)

    return harness


# ═══════════════════════════════════════
# 4. 演示场景
# ═══════════════════════════════════════

def main():
    print("=" * 60)
    print("  mini-harness 演示 —— Agent 运行时六大组件")
    print("=" * 60)

    harness = build_harness()
    harness.start_session()

    # ── 场景 1：安全工具自动放行 ──
    print("\n" + "─" * 60)
    print(">> 场景 1：计算器（safe 类 → 自动放行）")
    print("─" * 60)
    result = harness.run("帮我算一下 123 + 456")
    print(f"\n  [OK] Agent 回复: {result}")

    # ── 场景 2：网络工具需确认 ──
    print("\n" + "─" * 60)
    print(">> 场景 2：天气查询（network 类 → 需要确认）")
    print("─" * 60)
    result = harness.run("查一下长沙今天天气怎么样")
    print(f"\n  [OK] Agent 回复: {result}")

    # ── 场景 3：继续对话（触发上下文压缩）──
    print("\n" + "─" * 60)
    print(">> 场景 3：多次对话后触发上下文压缩")
    print("─" * 60)
    for i, query in enumerate([
        "什么是 AI Agent？",
        "Agent 有哪些核心组件？",
        "LangGraph 是什么？",
        "MCP 协议怎么用？",
        "RAG 的检索流程是怎样的？",
    ]):
        print(f"\n  [{i+1}/5] 用户: {query}")
        result = harness.run(query)
        print(f"       Agent: {result[:100]}...")

    # ── 场景 4：系统命令被拒绝 ──
    print("\n" + "─" * 60)
    print(">> 场景 4：系统命令（system 类 → 默认拒绝）")
    print("─" * 60)
    result = harness.run("帮我执行命令 echo hello")
    print(f"\n  [DENY] Agent 回复: {result}")

    # ── 场景 5：查看追踪统计 ──
    print("\n" + "─" * 60)
    print("== 场景 5：追踪统计")
    print("─" * 60)
    stats = harness.stats()
    trace = stats.pop("trace", {})
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  trace_steps: {trace.get('total_steps', 0)}")
    print(f"  trace_tokens: {trace.get('total_tokens', 0)}")
    print(f"  trace_time_ms: {trace.get('total_time_ms', 0):.0f}")
    print(f"  trace_errors: {trace.get('errors', 0)}")

    # ── 查看追踪明细 ──
    print("\n" + "─" * 60)
    print("-- 追踪明细（最近 10 条）")
    print("─" * 60)
    for row in harness.tracer.query(limit=10):
        print(f"  [{row['step_type']}] {row['input_summary'][:60]} | {row['duration_ms']:.1f}ms")

    harness.close()

    # 清理演示数据库
    for f in ["demo_sessions.db", "demo_traces.db"]:
        if os.path.exists(f):
            os.remove(f)

    print("\n" + "=" * 60)
    print("  *** 演示完成！六大组件全部运作正常")
    print("=" * 60)


if __name__ == "__main__":
    main()
