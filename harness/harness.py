"""
AgentHarness —— 组合六大组件的 Agent 运行时

夹在 Agent 代码和 LLM 之间：
  Agent 代码定义「做什么」，Harness 管「怎么做才稳定」

调用流程：
  用户输入
    → [权限门禁] 检查
    → [工具注册表] 拼到 prompt
    → [上下文压缩] token 超限？压缩
    → [会话存储] 加载/保存消息
    → [日志追踪] 每步记录
    → [状态恢复] 出错回退
    → LLM 回复
"""

from typing import Callable, Optional

from .tool_registry import ToolRegistry, Tool
from .permission import PermissionGate, Policy, GateRule
from .session import SessionStore, Session, Message
from .compressor import Compressor, CompressResult
from .tracer import Tracer, TraceStep
from .recovery import Recovery, Checkpoint


class AgentHarness:
    """
    Agent 运行时 —— 六大组件的统一入口。

    用法：
        harness = AgentHarness(session_db="sessions.db", trace_db="trace.db")

        # 注册工具
        harness.register_tool(
            name="calculator",
            description="执行数学计算",
            parameters={"expression": {"type": "string", "description": "算式"}},
            fn=lambda expression: str(eval(expression)),
            category="safe",
        )

        # 设置 LLM 调用函数
        harness.set_llm(my_llm_function)

        # 运行
        result = harness.run("帮我算 123 * 456")
    """

    def __init__(
        self,
        session_db: str = ":memory:",
        trace_db: str = ":memory:",
        max_tokens: int = 8000,
        keep_recent: int = 6,
        verbose: bool = True,
    ):
        # ── 六大组件 ─────────────────
        self.tools = ToolRegistry()
        self.gate = PermissionGate()
        self.session_store = SessionStore(session_db)
        self.compressor = Compressor(max_tokens=max_tokens, keep_recent=keep_recent)
        self.tracer = Tracer(trace_db, verbose=verbose)
        self.recovery = Recovery()

        # ── 联动配置 ─────────────────
        # 权限门禁 ↔ 工具注册表（根据工具分类自动判断策略）
        self.gate.set_category_resolver(lambda name: self._tool_category(name))

        # ── LLM 调用函数（外部注入）───
        self._llm_fn: Optional[Callable] = None
        self._summarize_fn: Optional[Callable] = None

        # ── 当前会话 ─────────────────
        self._session: Optional[Session] = None
        self._verbose = verbose

        self._log("[INIT] AgentHarness 初始化完成（6 组件就绪）")

    # ── 配置方法 ────────────────────────

    def set_llm(self, fn: Callable):
        """
        设置 LLM 调用函数。
        签名为 fn(messages: list[Message], tools_desc: str) -> str
        """
        self._llm_fn = fn

    def set_summarize_fn(self, fn: Callable):
        """
        设置摘要函数。
        签名为 fn(messages: list[Message]) -> str
        """
        self._summarize_fn = fn
        self.compressor.set_summarize_fn(fn)

    def set_confirm_callback(self, callback: Callable):
        """设置权限确认回调（ASK 策略时调用）"""
        self.gate.set_confirm_callback(callback)

    # ── 工具管理 ────────────────────────

    def register_tool(self, name: str, description: str, parameters: dict, fn: Callable, category: str = "general", tags: list | None = None) -> Tool:
        """注册工具"""
        return self.tools.register(name, description, parameters, fn, category, tags)

    def _tool_category(self, tool_name: str) -> str:
        tool = self.tools.get(tool_name)
        return tool.category if tool else "general"

    # ── 会话管理 ────────────────────────

    def start_session(self, session_id: str | None = None) -> Session:
        """创建或加载会话"""
        if session_id:
            existing = self.session_store.get(session_id)
            if existing:
                self._session = existing
                self._log(f"[LOAD] 加载会话: {session_id}（{len(existing.messages)} 条消息）")
                return existing

        self._session = self.session_store.create(session_id)
        self._log(f"[NEW] 新建会话: {self._session.id}")
        return self._session

    @property
    def session(self) -> Optional[Session]:
        return self._session

    # ── 核心运行循环 ────────────────────

    def run(self, user_input: str, max_iterations: int = 5) -> str:
        """
        运行一次 Agent 交互（ReAct 循环）。

        Args:
            user_input: 用户输入
            max_iterations: 最大循环次数（防止死循环）

        Returns:
            Agent 的最终回复
        """
        if not self._session:
            self.start_session()

        sid = self._session.id

        # ── 步骤 1：添加用户消息 ──────────
        user_msg = Message(role="user", content=user_input)
        self.session_store.add_message(sid, user_msg)
        self._session.messages.append(user_msg)

        # ── 步骤 2：保存恢复检查点 ────────
        self.recovery.save(
            "before_run",
            messages=self._session.messages,
            state=self._session.state,
        )

        # ── 步骤 3：ReAct 循环 ────────────
        iteration = 0
        final_response = ""

        while iteration < max_iterations:
            iteration += 1

            # 3.1 上下文压缩检查
            with self.tracer.span("compress", session_id=sid) as step:
                if self.compressor.needs_compression(self._session.messages):
                    result = self.compressor.compress(
                        self._session.messages, strategy="hybrid"
                    )
                    self._session.messages = result.messages
                    step.input_summary = f"压缩前{result.original_count}条→后{result.compressed_count}条"
                    self._log(f"[COMPRESS] 上下文压缩: {result.original_count}->{result.compressed_count}条, token {result.estimated_tokens_before}->{result.estimated_tokens_after}")

            # 3.2 生成工具描述
            tools_desc = self.tools.describe_all()

            # 3.3 调用 LLM
            if not self._llm_fn:
                raise RuntimeError("请先调用 harness.set_llm() 设置 LLM 函数")

            step_input = f"第{iteration}轮, {len(self._session.messages)}条消息"
            with self.tracer.span("llm_call", session_id=sid) as step:
                step.input_summary = step_input
                try:
                    llm_output = self._llm_fn(self._session.messages, tools_desc)
                    step.output_summary = llm_output[:200]
                except Exception as e:
                    step.error = str(e)[:200]
                    # 尝试恢复
                    cp = self.recovery.restore()
                    if cp:
                        self._session.messages = cp.messages_snapshot
                        self._session.state = cp.state
                        self._log(f"[RECOVER] 恢复检查点: {cp.name}")
                        continue
                    else:
                        raise

            # 3.4 解析 LLM 输出（判断是否调工具）
            assistant_msg = Message(role="assistant", content=llm_output)
            self.session_store.add_message(sid, assistant_msg)
            self._session.messages.append(assistant_msg)

            tool_call = self._parse_tool_call(llm_output)

            if tool_call is None:
                # 没有工具调用 → 最终回复
                final_response = llm_output
                break

            # 3.5 权限门禁检查
            tool_name, tool_args = tool_call
            with self.tracer.span("gate_check", session_id=sid) as step:
                step.input_summary = f"tool={tool_name}"
                allowed = self.gate.gate(tool_name, self._tool_category(tool_name))
                step.output_summary = "ALLOW" if allowed else "DENY"

            if not allowed:
                denied_msg = Message(
                    role="tool",
                    content=f"工具 '{tool_name}' 被权限门禁拒绝执行。",
                    metadata={"tool_name": tool_name, "status": "denied"},
                )
                self.session_store.add_message(sid, denied_msg)
                self._session.messages.append(denied_msg)
                final_response = f"抱歉，'{tool_name}' 操作需要额外权限，无法执行。"
                break

            # 3.6 执行工具
            with self.tracer.span("tool_call", session_id=sid) as step:
                step.input_summary = f"{tool_name}({tool_args})"
                tool = self.tools.get(tool_name)

                if tool is None:
                    tool_result = f"错误：工具 '{tool_name}' 未注册"
                    step.error = tool_result
                else:
                    try:
                        tool_result = str(tool.fn(**tool_args))
                        step.output_summary = tool_result[:200]
                    except Exception as e:
                        tool_result = f"工具执行错误：{e}"
                        step.error = tool_result

            tool_msg = Message(
                role="tool",
                content=tool_result,
                metadata={"tool_name": tool_name, "args": tool_args},
            )
            self.session_store.add_message(sid, tool_msg)
            self._session.messages.append(tool_msg)

            # 3.7 保存检查点（每轮循环后）
            self.recovery.save(
                f"after_iteration_{iteration}",
                messages=self._session.messages,
                state=self._session.state,
            )

        # ── 步骤 4：结果兜底 ──────────────
        if not final_response:
            final_response = "Agent 达到最大迭代次数，未能完成任务。"

        # ── 步骤 5：保存会话 ──────────────
        self.session_store.save_state(sid, self._session.state)
        self.recovery.clear("before_run")

        return final_response

    # ── 工具调用解析 ─────────────────────

    def _parse_tool_call(self, llm_output: str) -> Optional[tuple[str, dict]]:
        """
        从 LLM 输出中解析工具调用。

        支持的格式（按优先级）：
          1. 代码块 JSON: ```json\n{"tool": "name", "args": {...}}\n```
          2. 内联 TOOL: TOOL: name | args: {...}
          3. 自然语言调用模式

        Returns:
            (tool_name, args_dict) 或 None（表示最终回复）
        """
        import json as _json
        import re

        # 格式 1：代码块中的 JSON
        match = re.search(r'```(?:json)?\s*\n?\s*\{[^`]+\}\s*\n?\s*```', llm_output)
        if match:
            try:
                data = _json.loads(match.group(0).strip("`").strip())
                if "tool" in data:
                    return data["tool"], data.get("args", {})
                if "name" in data:
                    return data["name"], data.get("parameters", data.get("args", {}))
            except _json.JSONDecodeError:
                pass

        # 格式 2：TOOL: 语法
        match = re.search(r'TOOL:\s*(\w+)(?:\s*\|\s*args:\s*(\{.*?\}))?', llm_output, re.DOTALL)
        if match:
            tool_name = match.group(1)
            args_str = match.group(2)
            try:
                args = _json.loads(args_str) if args_str else {}
            except _json.JSONDecodeError:
                args = {}
            return tool_name, args

        # 格式 3：自然语言"调用XXX工具"
        match = re.search(r'(?:调用|使用|call)\s*[「「]?(\w+)[」」]?\s*(?:工具|tool)', llm_output, re.IGNORECASE)
        if match:
            return match.group(1), {}

        # 没有工具调用 → 最终回复
        return None

    # ── 辅助方法 ────────────────────────

    def _log(self, msg: str):
        if self._verbose:
            print(f"  {msg}")

    def stats(self) -> dict:
        """获取当前会话的统计信息"""
        sid = self._session.id if self._session else ""
        return {
            "tools_registered": len(self.tools),
            "gate_rules": len(self.gate.list_rules()),
            "session_messages": len(self._session.messages) if self._session else 0,
            "checkpoints": self.recovery.checkpoint_count,
            "recoveries": self.recovery.recovery_count,
            "trace": self.tracer.stats(sid) if sid else {},
        }

    def close(self):
        """关闭所有资源"""
        self.session_store.close()
        self.tracer.close()
        self._log("[CLOSE] Harness 已关闭")
