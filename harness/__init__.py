"""
mini-harness v2 — 从零搭建的多 Agent 运行时

六大组件（v1）：
  1. ToolRegistry  — 工具注册表（MCP 同款）
  2. PermissionGate — 权限门禁（危险操作需确认）
  3. SessionStore  — 会话存储（SQLite 持久化）
  4. Compressor    — 上下文压缩（防 token 爆炸）
  5. Tracer        — 日志追踪（每步全记录）
  6. Recovery      — 状态恢复（断点续跑）

v2 新增组件：
  7. ExpertRegistry  — 专家 Agent 注册表
  8. ResultSynthesizer — 多专家结果合成
  9. Orchestrator    — 编排者引擎（拆解→调度→合成）

用法（v1 兼容）：
    from harness import AgentHarness
    harness = AgentHarness()
    harness.register_tool(my_tool)
    result = harness.run("帮我分析这个数据")

用法（v2 多 Agent）：
    from harness import AgentHarness, Expert
    harness = AgentHarness()
    harness.set_llm(my_llm)
    harness.register_expert(Expert(
        name="code_reviewer",
        description="审查代码质量",
        domain=["code"],
        capabilities=["代码审查", "Bug 检测"],
        fn=my_review_fn,
    ))
    result = harness.run_multi("审查这段代码")
"""

from .tool_registry import ToolRegistry, Tool
from .permission import PermissionGate, Policy, GateRule, AgentRule
from .session import SessionStore, Session, Message
from .compressor import Compressor, CompressResult
from .tracer import Tracer, TraceStep
from .recovery import Recovery, Checkpoint
from .expert import ExpertRegistry, Expert
from .orchestrator import Orchestrator, SubTask
from .synthesizer import ResultSynthesizer, SourceBlock
from .harness import AgentHarness

__all__ = [
    # v1
    "ToolRegistry", "Tool",
    "PermissionGate", "Policy", "GateRule",
    "SessionStore", "Session", "Message",
    "Compressor", "CompressResult",
    "Tracer", "TraceStep",
    "Recovery", "Checkpoint",
    # v2
    "ExpertRegistry", "Expert",
    "Orchestrator", "SubTask",
    "ResultSynthesizer", "SourceBlock",
    "AgentRule",
    "AgentHarness",
]
