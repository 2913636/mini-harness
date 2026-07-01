"""
demo_v2.py — mini-harness v2 真实多 Agent 协作演示

基于 DeepSeek API，3 个真实专家 + 编排者协作完成任务。
场景：用户提交代码/架构问题 → 编排者拆解 → 3 专家并行分析 → 合成最终报告

用法：
    py demo_v2.py              # 默认：分析 mini-harness 自身
    py demo_v2.py --task "你的任务"
    py demo_v2.py --api-check  # 仅测试 API 连接
"""

import argparse
import os
import sys
import textwrap

# 确保能 import harness
sys.path.insert(0, os.path.dirname(__file__))

from harness import AgentHarness, Expert, Message
from llm_client import DeepSeekClient
from expert_functions import (
    create_code_reviewer,
    create_security_expert,
    create_test_writer,
    create_doc_writer,
)


# ═══════════════════════════════════════════════════
# Harness LLM 适配器
# ═══════════════════════════════════════════════════

def make_harness_llm(client: DeepSeekClient):
    """
    创建 harness 的 LLM 函数。

    harness 要求的签名: fn(messages: list[Message], prompt: str) -> str
    """
    def harness_llm(messages: list, prompt: str) -> str:
        # 将 harness Message 对象转为 API 格式
        api_messages = []
        for m in messages[-20:]:  # 最近 20 条，防 token 爆炸
            role = m.role if hasattr(m, "role") else "user"
            content = m.content if hasattr(m, "content") else str(m)
            if role == "orchestrator":
                role = "assistant"
            api_messages.append({"role": role, "content": content[:2000]})

        return client.chat(prompt, messages=api_messages)

    return harness_llm


# ═══════════════════════════════════════════════════
# 构建 Harness
# ═══════════════════════════════════════════════════

def build_harness(client: DeepSeekClient) -> AgentHarness:
    """构建接入了真实 DeepSeek 的 AgentHarness v2"""

    harness = AgentHarness(
        session_db=":memory:",
        trace_db=":memory:",
        max_tokens=16000,
        keep_recent=10,
        verbose=True,
    )

    # 注入 LLM
    harness.set_llm(make_harness_llm(client))

    # ── 注册专家 ──────────────────────
    harness.register_expert(Expert(
        name="code_reviewer",
        description="审查代码质量：可读性、正确性、性能、边界处理、可维护性",
        domain=["code", "quality"],
        capabilities=["代码审查", "Bug 检测", "性能分析", "重构建议"],
        fn=create_code_reviewer(client),
    ))

    harness.register_expert(Expert(
        name="security_expert",
        description="安全漏洞扫描：注入攻击、权限控制、敏感信息泄露、依赖安全",
        domain=["security"],
        capabilities=["注入检测", "权限审计", "敏感信息扫描", "OWASP 合规"],
        fn=create_security_expert(client),
    ))

    harness.register_expert(Expert(
        name="test_writer",
        description="基于代码和审查结果编写测试用例，覆盖正常/边界/异常路径",
        domain=["testing"],
        capabilities=["单元测试", "集成测试", "边界测试", "覆盖率分析"],
        fn=create_test_writer(client),
    ))

    harness.register_expert(Expert(
        name="doc_writer",
        description="根据分析结果生成技术文档、综合报告或 README",
        domain=["doc"],
        capabilities=["技术文档", "API 文档", "综合报告", "README"],
        fn=create_doc_writer(client),
    ))

    # ── 配置 Agent 间权限 ────────────
    harness.allow_agent_call("orchestrator", "code_reviewer")
    harness.allow_agent_call("orchestrator", "security_expert")
    harness.allow_agent_call("orchestrator", "test_writer")
    harness.allow_agent_call("orchestrator", "doc_writer")

    return harness


# ═══════════════════════════════════════════════════
# 演示主流程
# ═══════════════════════════════════════════════════

def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_subtask(st, index: int):
    icon = "[OK]" if st.status == "done" else "[X]" if st.status == "failed" else "[..]"
    expert = st.source_expert or st.assigned_expert or "LLM fallback"
    print(f"  {icon} Subtask {index}: {st.description[:80]}")
    print(f"      Expert: {expert}  |  Time: {st.duration_ms:.0f}ms")


def run_demo(client: DeepSeekClient, task: str):
    """运行完整的多 Agent 协作演示"""

    print_separator("mini-harness v2 — Multi-Agent Demo (DeepSeek)")

    # ── 1. 构建 Harness ──
    print("\n[1/5] Initializing Agent Harness v2...")
    harness = build_harness(client)
    print(f"      Registered {len(harness.experts)} experts: ", end="")
    print(", ".join(e.name for e in harness.list_experts()))

    # ── 2. 展示任务 ──
    print(f"\n[2/5] Task received:")
    for line in textwrap.wrap(task, width=60):
        print(f"      {line}")

    # ── 3. 运行多 Agent ──
    print(f"\n[3/5] Orchestrator decomposing -> Experts executing -> Synthesizing...")
    print(f"      (Waiting for DeepSeek API...)")

    result = harness.run_multi(
        task=task,
        user_priorities=["安全性", "代码质量"],
    )

    # ── 4. 执行统计 ──
    print_separator("Execution Stats")
    stats = result["stats"]
    print(f"  Total subtasks: {stats['total_subtasks']}")
    print(f"  Completed: {stats['completed']}  |  Failed: {stats['failed']}")
    print(f"  Capability gaps: {stats['gaps']} ")
    print(f"  Total time: {stats['duration_ms']:.0f}ms")

    print(f"\n  Subtask details:")
    for i, st in enumerate(result.get("subtasks", []), 1):
        print_subtask(st, i)

    # ── 5. 最终报告 ──
    print_separator("Final Report")
    report = result.get("report", "(No report)")
    # 显示前 80 行
    lines = report.split("\n")
    for line in lines[:80]:
        print(line)
    if len(lines) > 80:
        print(f"\n  ... ({len(lines)} lines total, truncated)")

    # ── 清理 ──
    harness.close()
    print(f"\n{'='*60}")
    print(f"  Demo complete!")
    print(f"{'='*60}")

    return result


def check_api(client: DeepSeekClient):
    """测试 DeepSeek API 连接"""
    print("Checking DeepSeek API connection...")
    result = client.check_connection()
    if result["status"] == "ok":
        print(f"  [OK] Connected")
        print(f"      Model: {result['model']}")
        print(f"      Endpoint: {result['base_url']}")
        print(f"      Test reply: {result['test_reply']}")
        return True
    else:
        print(f"  [FAIL] Connection failed: {result['error']}")
        return False


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="mini-harness v2 Multi-Agent Demo (DeepSeek powered)"
    )
    parser.add_argument(
        "--task", "-t",
        type=str,
        default="",
        help="Custom task (default: analyze mini-harness itself)",
    )
    parser.add_argument(
        "--api-check",
        action="store_true",
        help="Only test API connection, skip full demo",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek-chat",
        help="DeepSeek model name (default: deepseek-chat)",
    )
    args = parser.parse_args()

    # 创建客户端（密钥从 .env 自动读取）
    client = DeepSeekClient(model=args.model)

    # 仅 API 检查模式
    if args.api_check:
        ok = check_api(client)
        sys.exit(0 if ok else 1)

    # 检查 API
    print("[*] Checking DeepSeek API...")
    conn = client.check_connection()
    if conn["status"] != "ok":
        print(f"[FAIL] API not available: {conn['error']}")
        print("   Please verify DEEPSEEK_API_KEY in .env file")
        sys.exit(1)
    print(f"[OK] API connected ({conn['model']})\n")

    # 确定任务
    if args.task:
        task = args.task
    else:
        # 默认：分析 mini-harness 自身
        task = textwrap.dedent("""\
        请全面分析 mini-harness 项目的代码质量和安全性。

        mini-harness 是一个 Python Agent 运行时框架，包含 9 个核心组件：
        - ToolRegistry: 工具注册管理
        - PermissionGate: 权限门禁
        - SessionStore: SQLite 会话存储
        - Compressor: 上下文压缩
        - Tracer: 日志追踪
        - Recovery: 状态恢复
        - ExpertRegistry: 专家管理
        - Orchestrator: 编排引擎
        - ResultSynthesizer: 结果合成

        请从以下角度分析：
        1. 代码架构设计是否合理
        2. 存在哪些安全风险（重点关注 SQL 注入、权限控制、敏感信息泄露）
        3. 上下文压缩算法是否完善
        4. 写出针对核心组件（SessionStore、PermissionGate、Orchestrator）的测试用例
        5. 生成一份综合改进建议报告""").strip()

    run_demo(client, task)


if __name__ == "__main__":
    main()
