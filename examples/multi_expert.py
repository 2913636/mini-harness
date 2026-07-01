"""
示例 3：多专家协作 —— 代码审查 + 安全扫描
演示 v2 的 Orchestrator-Expert 拓扑
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness import AgentHarness, Expert


# ── 专家函数 ──
def code_review_expert(task: str, context: dict | None = None) -> str:
    """模拟代码审查专家"""
    ctx = context or {}
    deps = ctx.get("dependencies", {})
    dep_info = ""
    if deps:
        dep_info = f"（上游结果: {'; '.join(f'{k}: {v[:60]}' for k, v in deps.items())}）"
    return f"[代码审查] 已审查代码，发现 3 个问题：\n  1. 变量命名不规范\n  2. 缺少异常处理\n  3. 循环可优化{dep_info}"


def security_expert(task: str, context: dict | None = None) -> str:
    """模拟安全专家"""
    return "[安全扫描] 扫描完成：\n  1. 未发现 SQL 注入\n  2. 未发现 XSS 漏洞\n  3. 建议加强输入校验"


# ── 模拟 LLM ──
MOCK_DECOMPOSE_RESPONSE = """```json
[
  {"id": "1", "description": "审查代码质量和规范", "required_domains": ["code"], "dependencies": [], "priority": "P0"},
  {"id": "2", "description": "扫描安全漏洞", "required_domains": ["security"], "dependencies": [], "priority": "P0"},
  {"id": "3", "description": "编写审查报告", "required_domains": ["doc"], "dependencies": ["1", "2"], "priority": "P1"}
]
```"""


def mock_llm(messages, prompt):
    if "请将以下用户任务拆解" in prompt:
        return MOCK_DECOMPOSE_RESPONSE
    if "请基于以上各专家的分析结果" in prompt:
        return "# 代码审查报告\n\n综合两位专家意见，代码质量良好，建议修复 3 个命名和异常处理问题。安全方面无重大漏洞。"
    if "完成以下任务" in prompt:
        return "[doc_writer] 已生成审查报告草稿。"
    return "收到。"


def main():
    harness = AgentHarness(verbose=True)

    # 注册专家
    harness.register_expert(Expert(
        name="code_reviewer",
        description="审查代码质量",
        domain=["code", "quality"],
        capabilities=["代码审查", "Bug 检测"],
        fn=code_review_expert,
    ))
    harness.register_expert(Expert(
        name="security_scanner",
        description="扫描安全漏洞",
        domain=["security"],
        capabilities=["漏洞扫描", "安全审计"],
        fn=security_expert,
    ))

    harness.set_llm(mock_llm)
    harness.start_session()

    result = harness.run_multi("审查代码安全性并写报告")
    print(f"\n{'='*50}")
    print(f"最终报告:\n{result['report']}")
    print(f"统计: {result['stats']}")

    harness.close()


if __name__ == "__main__":
    main()
