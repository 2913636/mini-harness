"""
demo_v2.py — mini-harness v2 真实多 Agent 协作演示

基于 DeepSeek API，4 个真实专家 + 编排者协作完成任务。
场景：用户提交代码/架构问题 → 编排者拆解 → 4 专家并行分析 → 合成最终报告

用法：
    py demo_v2.py                          # 默认：分析 mini-harness 自身
    py demo_v2.py --stream                 # 流式输出（逐字显示）
    py demo_v2.py --task "你的任务"
    py demo_v2.py --api-check              # 仅测试 API 连接
    py demo_v2.py --quick                  # 快速演示（小任务）
"""

import argparse
import os
import sys
import textwrap
import threading
import time

# 修复 Windows 终端中文乱码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
# 进度显示器（线程安全）
# ═══════════════════════════════════════════════════

class ProgressDisplay:
    """多专家并行时的进度显示器"""

    def __init__(self, stream: bool = False):
        self._lock = threading.Lock()
        self._expert_status: dict[str, str] = {}  # expert_name -> status
        self._stream = stream
        self._streaming_expert: str = ""  # 当前正在流式输出的专家
        self._chars_in_line = 0

    def expert_start(self, name: str, task_preview: str):
        with self._lock:
            self._expert_status[name] = "thinking..."
            if self._stream:
                print(f"\n  [{name}] thinking...", end="", flush=True)
            else:
                print(f"  [{name}] {task_preview[:60]}...", flush=True)

    def expert_chunk(self, name: str, text: str):
        if not self._stream:
            return
        with self._lock:
            if self._streaming_expert != name:
                if self._streaming_expert:
                    print()  # 换行结束上一个专家的输出
                self._streaming_expert = name
                print(f"\n  ── {name} ──")
            print(text, end="", flush=True)

    def expert_done(self, name: str):
        with self._lock:
            self._expert_status[name] = "done"
            if self._stream and self._streaming_expert == name:
                print()  # 结束时换行
                self._streaming_expert = ""

    def phase(self, msg: str):
        with self._lock:
            if self._streaming_expert:
                print()
                self._streaming_expert = ""
            print(f"\n  >> {msg}", flush=True)


# ═══════════════════════════════════════════════════
# Harness LLM 适配器
# ═══════════════════════════════════════════════════

def make_harness_llm(client: DeepSeekClient, progress: ProgressDisplay = None):
    """
    创建 harness 的 LLM 函数。
    harness 签名: fn(messages: list[Message], prompt: str) -> str
    """

    def harness_llm(messages: list, prompt: str) -> str:
        api_messages = []
        for m in messages[-20:]:
            role = m.role if hasattr(m, "role") else "user"
            content = m.content if hasattr(m, "content") else str(m)
            if role == "orchestrator":
                role = "assistant"
            api_messages.append({"role": role, "content": content[:2000]})

        # 判断调用阶段
        if "JSON" in prompt and ("子任务" in prompt or "拆解" in prompt):
            if progress:
                progress.phase("Decomposing task...")
            return client.chat(prompt, messages=api_messages)

        if progress:
            progress.phase("Synthesizing final report...")

        # 合成报告时流式输出
        if progress and progress._stream:
            def on_chunk(text: str):
                progress.expert_chunk("report", text)
            return client.chat(prompt, messages=api_messages, on_chunk=on_chunk)

        return client.chat(prompt, messages=api_messages)

    return harness_llm


# ═══════════════════════════════════════════════════
# 构建 Harness
# ═══════════════════════════════════════════════════

def build_harness(client: DeepSeekClient, progress: ProgressDisplay = None) -> AgentHarness:
    """构建接入了真实 DeepSeek 的 AgentHarness v2"""

    harness = AgentHarness(
        session_db=":memory:",
        trace_db=":memory:",
        max_tokens=16000,
        keep_recent=10,
        verbose=False,  # 关掉内置日志，用 progress 替代
    )

    harness.set_llm(make_harness_llm(client, progress))

    # 每个专家各自创建一个 DeepSeek 客户端 + 进度回调
    def expert_progress(name: str):
        def cb(status: str):
            if status == "thinking":
                pass  # expert_start 已经打印了
            elif status == "done":
                progress.expert_done(name) if progress else None
            else:
                progress.expert_chunk(name, status) if progress else None
        return cb

    harness.register_expert(Expert(
        name="code_reviewer",
        description="审查代码质量：可读性、正确性、性能、边界处理、可维护性",
        domain=["code", "quality"],
        capabilities=["代码审查", "Bug 检测", "性能分析", "重构建议"],
        fn=create_code_reviewer(
            DeepSeekClient(),
            on_progress=expert_progress("code_reviewer") if progress else None,
        ),
    ))

    harness.register_expert(Expert(
        name="security_expert",
        description="安全漏洞扫描：注入攻击、权限控制、敏感信息泄露、依赖安全",
        domain=["security"],
        capabilities=["注入检测", "权限审计", "敏感信息扫描", "OWASP 合规"],
        fn=create_security_expert(
            DeepSeekClient(),
            on_progress=expert_progress("security_expert") if progress else None,
        ),
    ))

    harness.register_expert(Expert(
        name="test_writer",
        description="基于代码和审查结果编写测试用例，覆盖正常/边界/异常路径",
        domain=["testing"],
        capabilities=["单元测试", "集成测试", "边界测试", "覆盖率分析"],
        fn=create_test_writer(
            DeepSeekClient(),
            on_progress=expert_progress("test_writer") if progress else None,
        ),
    ))

    harness.register_expert(Expert(
        name="doc_writer",
        description="根据分析结果生成技术文档、综合报告",
        domain=["doc"],
        capabilities=["技术文档", "API 文档", "综合报告"],
        fn=create_doc_writer(
            DeepSeekClient(),
            on_progress=expert_progress("doc_writer") if progress else None,
        ),
    ))

    # Agent 间权限
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


def run_demo(client: DeepSeekClient, task: str, stream: bool = False):
    """运行完整的多 Agent 协作演示"""

    print_separator("mini-harness v2 — Multi-Agent Demo (DeepSeek)")

    progress = ProgressDisplay(stream=stream)

    # ── 1. 构建 Harness ──
    print("\n[1/5] Initializing Agent Harness v2...")
    harness = build_harness(client, progress)
    print(f"      Registered {len(harness.experts)} experts: ", end="")
    print(", ".join(e.name for e in harness.list_experts()))

    # ── 2. 展示任务 ──
    print(f"\n[2/5] Task:")
    for line in textwrap.wrap(task, width=60):
        print(f"      {line}")

    # ── 3. 运行多 Agent ──
    print(f"\n[3/5] Orchestrating...")
    t0 = time.perf_counter()

    result = harness.run_multi(
        task=task,
        user_priorities=["安全性", "代码质量"],
    )

    elapsed = (time.perf_counter() - t0)

    # ── 4. 执行统计 ──
    print_separator("Execution Stats")
    stats = result["stats"]
    print(f"  Total subtasks: {stats['total_subtasks']}")
    print(f"  Completed: {stats['completed']}  |  Failed: {stats['failed']}")
    print(f"  Capability gaps: {stats['gaps']}")
    print(f"  Wall-clock time: {elapsed:.1f}s")

    print(f"\n  Subtask details:")
    for i, st in enumerate(result.get("subtasks", []), 1):
        print_subtask(st, i)

    # ── 5. 最终报告 ──
    if not stream:  # 流式模式已经边生成边显示了，非流式才重新打印
        print_separator("Final Report")
        report = result.get("report", "(No report)")
        lines = report.split("\n")
        for line in lines[:80]:
            print(line)
        if len(lines) > 80:
            print(f"\n  ... ({len(lines)} lines total, truncated)")

    harness.close()
    print(f"\n{'='*60}")
    print(f"  Demo complete! ({elapsed:.1f}s)")
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
# 默认任务模板
# ═══════════════════════════════════════════════════

DEFAULT_TASK = textwrap.dedent("""\
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
2. 存在哪些安全风险
3. 上下文压缩算法是否完善
4. 写出核心组件的测试用例
5. 生成综合改进建议报告""").strip()

QUICK_TASK = "用 Python 写一个简单的 LRU 缓存类，然后审查这段代码的安全性和正确性，并写出测试用例。"


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="mini-harness v2 Multi-Agent Demo (DeepSeek powered)"
    )
    parser.add_argument("--task", "-t", type=str, default="",
                        help="Custom task")
    parser.add_argument("--api-check", action="store_true",
                        help="Only test API connection")
    parser.add_argument("--model", type=str, default="deepseek-chat",
                        help="DeepSeek model name")
    parser.add_argument("--stream", action="store_true",
                        help="Stream expert output in real-time")
    parser.add_argument("--quick", action="store_true",
                        help="Run a quick demo (smaller task)")
    args = parser.parse_args()

    client = DeepSeekClient(model=args.model)

    if args.api_check:
        ok = check_api(client)
        sys.exit(0 if ok else 1)

    print("[*] Checking DeepSeek API...")
    conn = client.check_connection()
    if conn["status"] != "ok":
        print(f"[FAIL] API not available: {conn['error']}")
        print("   Please verify DEEPSEEK_API_KEY in .env file")
        sys.exit(1)
    print(f"[OK] API connected ({conn['model']})")

    if args.task:
        task = args.task
    elif args.quick:
        task = QUICK_TASK
    else:
        task = DEFAULT_TASK

    run_demo(client, task, stream=args.stream)


if __name__ == "__main__":
    main()
