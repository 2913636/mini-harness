"""
示例 1：最简 Agent —— 注册工具 + 运行
演示 ToolRegistry + PermissionGate 核心流程
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness import AgentHarness


# ── 定义工具 ──
def greet(name: str) -> str:
    """打招呼"""
    return f"你好，{name}！"


# ── 模拟 LLM ──
def mock_llm(messages, tools_desc):
    last = messages[-1].content if messages else ""
    if "你好" in last or "hello" in last.lower():
        return 'TOOL: greet | args: {"name": "World"}'
    if "算" in last:
        return "请提供具体算式，我会帮你计算。"
    return f"收到：{last[:50]}。你可以试试说「你好」。"


def main():
    harness = AgentHarness(verbose=False)
    harness.register_tool(
        name="greet",
        description="向指定的人打招呼",
        parameters={"name": {"type": "string", "description": "名字"}},
        fn=greet,
        category="safe",
    )
    harness.set_llm(mock_llm)
    harness.start_session()

    result = harness.run("你好，帮我打个招呼")
    print(f"Agent: {result}")

    harness.close()


if __name__ == "__main__":
    main()
