"""
示例 2：权限门禁 —— 三层规则演示
演示 PermissionGate 的精确规则>通配规则>分类策略
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness import AgentHarness, Policy, GateRule


def mock_search(query: str) -> str:
    return f"搜索结果：关于「{query}」的信息..."

def mock_write(path: str, content: str) -> str:
    return f"已写入 {path}"


def mock_llm(messages, tools_desc):
    last = messages[-1].content if messages else ""
    if last == "hi":
        return 'TOOL: search | args: {"query": "AI"}'
    return f"收到：{last[:50]}"


def main():
    harness = AgentHarness(verbose=False)

    # 注册工具
    harness.register_tool("search", "网络搜索", {"query": {"type": "string"}}, mock_search, "network")
    harness.register_tool("write_file", "写文件", {"path": {"type": "string"}, "content": {"type": "string"}}, mock_write, "file")
    harness.register_tool("admin", "管理员操作", {"action": {"type": "string"}}, lambda action: "done", "system")

    # 权限规则（优先级由高到低）
    harness.gate.add_rule(GateRule(pattern="search", policy=Policy.ALLOW))       # 精确：放行搜索
    harness.gate.add_rule(GateRule(pattern="file:*", policy=Policy.ASK))          # 通配：文件需确认
    harness.gate.add_rule(GateRule(pattern="system:*", policy=Policy.DENY))       # 通配：系统默认拒

    harness.set_llm(mock_llm)

    # 模拟确认回调
    def confirm(tool, reason):
        print(f"  [权限请求] {tool}: {reason}")
        return True  # 实际场景这里问用户

    harness.set_confirm_callback(confirm)
    harness.start_session()

    print("=== 场景 1: 搜索（ALLOW → 自动放行）===")
    harness.run("hi")

    print("\n=== 场景 2: 写文件（ASK → 确认后放行）===")
    harness.run("hi")

    print("\n=== 场景 3: 管理员命令（DENY → 拒绝）===")
    harness.run("hi")

    harness.close()


if __name__ == "__main__":
    main()
