"""
mini-harness — 从零搭建的 Agent 运行时

六大组件：
  1. ToolRegistry  — 工具注册表（MCP 同款）
  2. PermissionGate — 权限门禁（危险操作需确认）
  3. SessionStore  — 会话存储（SQLite 持久化）
  4. Compressor    — 上下文压缩（防 token 爆炸）
  5. Tracer        — 日志追踪（每步全记录）
  6. Recovery      — 状态恢复（断点续跑）

用法：
    from harness import AgentHarness
    harness = AgentHarness()
    harness.register_tool(my_tool)
    result = harness.run("帮我分析这个数据")
"""

from .tool_registry import ToolRegistry, Tool
from .permission import PermissionGate, Policy
from .session import SessionStore, Session, Message
from .compressor import Compressor
from .tracer import Tracer, TraceStep
from .recovery import Recovery
from .harness import AgentHarness

__all__ = [
    "ToolRegistry", "Tool",
    "PermissionGate", "Policy",
    "SessionStore", "Session", "Message",
    "Compressor",
    "Tracer", "TraceStep",
    "Recovery",
    "AgentHarness",
]
