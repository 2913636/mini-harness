"""
AgentHarness v2 —— 集成多 Agent 编排的 Agent 运行时

v2 新增：
  - ExpertRegistry: 专家 Agent 注册表
  - Orchestrator: 任务拆解→专家调度→结果合成
  - ResultSynthesizer: 多专家结果合成
  - 六组件全面升级以支持多 Agent 场景

调用流程（v2 新增多 Agent 路径）：
  用户输入
    → [Orchestrator] 拆解任务、匹配专家、调度执行
    → [PermissionGate] 检查 Agent 间调用权限
    → [ExpertRegistry] 专家执行
    → [ResultSynthesizer] 合成最终报告
    → [SessionStore] 树形消息存储
    → [Compressor] 分支级压缩
    → [Tracer] 多 Agent 因果追踪
    → [Recovery] 分支级恢复
"""

from typing import Callable, Optional

from .tool_registry import ToolRegistry, Tool
from .permission import PermissionGate, Policy, GateRule, AgentRule
from .session import SessionStore, Session, Message
from .compressor import Compressor, CompressResult
from .tracer import Tracer, TraceStep
from .recovery import Recovery, Checkpoint
from .expert import ExpertRegistry, Expert
from .orchestrator import Orchestrator
from .synthesizer import ResultSynthesizer


class AgentHarness:
    """
    Agent 运行时 v2 —— 多 Agent 编排的统一入口。

    用法（v1 兼容）：
        harness = AgentHarness(session_db="sessions.db", trace_db="trace.db")
        harness.register_tool(name="calculator", ...)
        harness.set_llm(my_llm)
        result = harness.run("帮我算 123 * 456")

    用法（v2 多 Agent）：
        harness = AgentHarness()
        harness.set_llm(my_llm)

        # 注册专家
        harness.register_expert(Expert(
            name="code_reviewer",
            description="审查代码质量",
            domain=["code"],
            capabilities=["代码审查", "Bug 检测"],
            fn=my_code_review_fn,
        ))

        # 多 Agent 运行
        result = harness.run_multi("审查这段代码的安全性并写测试")
        print(result["report"])

        # 查看专家性能
        perf = harness.expert_performance()
    """

    def __init__(
        self,
        session_db: str = ":memory:",
        trace_db: str = ":memory:",
        max_tokens: int = 8000,
        keep_recent: int = 6,
        verbose: bool = True,
    ):
        # ── 六大组件（v1 兼容）─────────
        self.tools = ToolRegistry()
        self.gate = PermissionGate()
        self.session_store = SessionStore(session_db)
        self.compressor = Compressor(max_tokens=max_tokens, keep_recent=keep_recent)
        self.tracer = Tracer(trace_db, verbose=verbose)
        self.recovery = Recovery()

        # ── v2 新增组件 ────────────────
        self.experts = ExpertRegistry()
        self._orchestrator: Optional[Orchestrator] = None
        self._synthesizer: Optional[ResultSynthesizer] = None

        # ── 联动配置 ─────────────────
        self.gate.set_category_resolver(lambda name: self._tool_category(name))

        # ── LLM 调用函数 ──────────────
        self._llm_fn: Optional[Callable] = None
        self._summarize_fn: Optional[Callable] = None

        # ── 当前会话 ─────────────────
        self._session: Optional[Session] = None
        self._verbose = verbose

        self._log("[INIT] AgentHarness v2 初始化完成（多 Agent 就绪）")

    # ═══════════════════════════════════════════
    # 配置方法
    # ═══════════════════════════════════════════

    def set_llm(self, fn: Callable):
        """
        设置 LLM 调用函数。
        签名为 fn(messages: list[Message], tools_desc: str) -> str
        """
        self._llm_fn = fn

    def set_summarize_fn(self, fn: Callable):
        """设置摘要函数。签名为 fn(messages: list[Message]) -> str"""
        self._summarize_fn = fn
        self.compressor.set_summarize_fn(fn)

    def set_confirm_callback(self, callback: Callable):
        """设置权限确认回调"""
        self.gate.set_confirm_callback(callback)

    # ═══════════════════════════════════════════
    # 工具管理（v1 兼容）
    # ═══════════════════════════════════════════

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        fn: Callable,
        category: str = "general",
        tags: list | None = None,
    ) -> Tool:
        """注册工具"""
        return self.tools.register(name, description, parameters, fn, category, tags)

    def _tool_category(self, tool_name: str) -> str:
        tool = self.tools.get(tool_name)
        return tool.category if tool else "general"

    # ═══════════════════════════════════════════
    # 专家管理（v2 新增）
    # ═══════════════════════════════════════════

    def register_expert(self, expert: Expert) -> Expert:
        """
        注册专家 Agent（v2 新增）。

        Example:
            harness.register_expert(Expert(
                name="code_reviewer",
                description="审查代码质量，发现潜在 bug 和性能问题",
                domain=["code", "quality"],
                capabilities=["代码审查", "安全扫描", "性能分析"],
                fn=my_review_function,
            ))
        """
        expert = self.experts.register(expert)
        # 同时注册为工具，允许编排者通过工具调用机制派发
        if expert.fn:
            self.tools.register_expert_as_tool(
                expert_name=expert.name,
                expert_fn=lambda task, ctx=None, e=expert: e.fn(task, ctx or {}) if e.fn else "Expert not available",
                description=expert.description,
            )
        self._log(f"[EXPERT] 已注册: {expert.name} ({', '.join(expert.domain)})")
        return expert

    def unregister_expert(self, name: str) -> bool:
        """注销专家（v2 新增）"""
        if self.experts.unregister(name):
            self.tools.unregister(name)
            self._log(f"[EXPERT] 已注销: {name}")
            return True
        return False

    def list_experts(self) -> list[Expert]:
        """列出所有专家（v2 新增）"""
        return self.experts.list_all()

    def expert_performance(self) -> list[dict]:
        """专家性能统计（v2 新增）"""
        sid = self._session.id if self._session else ""
        return self.tracer.expert_stats(sid)

    # ═══════════════════════════════════════════
    # Agent 间权限（v2 新增）
    # ═══════════════════════════════════════════

    def allow_agent_call(self, caller: str, callee: str):
        """允许 caller 调用 callee"""
        self.gate.add_agent_rule(AgentRule(caller=caller, callee=callee, policy=Policy.ALLOW))

    def deny_agent_call(self, caller: str, callee: str):
        """禁止 caller 调用 callee"""
        self.gate.add_agent_rule(AgentRule(caller=caller, callee=callee, policy=Policy.DENY))

    # ═══════════════════════════════════════════
    # 会话管理
    # ═══════════════════════════════════════════

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

    # ═══════════════════════════════════════════
    # 核心运行（v1 兼容）
    # ═══════════════════════════════════════════

    def run(self, user_input: str, max_iterations: int = 5) -> str:
        """
        运行一次 Agent 交互（ReAct 循环）— v1 兼容。

        如果注册了专家，自动升级为多 Agent 模式。
        """
        if len(self.experts) > 0:
            # v2 多 Agent 模式
            result = self.run_multi(user_input)
            return result.get("report", str(result))

        # v1 单 Agent 模式
        return self._run_single_agent(user_input, max_iterations)

    def _run_single_agent(self, user_input: str, max_iterations: int = 5) -> str:
        """v1 单 Agent ReAct 循环（保持向后兼容）"""
        if not self._session:
            self.start_session()

        sid = self._session.id

        user_msg = Message(role="user", content=user_input)
        self.session_store.add_message(sid, user_msg)
        self._session.messages.append(user_msg)

        self.recovery.save(
            "before_run",
            messages=self._session.messages,
            state=self._session.state,
        )

        iteration = 0
        final_response = ""

        while iteration < max_iterations:
            iteration += 1

            with self.tracer.span("compress", session_id=sid) as step:
                if self.compressor.needs_compression(self._session.messages):
                    result = self.compressor.compress(
                        self._session.messages, strategy="hybrid"
                    )
                    self._session.messages = result.messages
                    step.input_summary = f"压缩前{result.original_count}条->后{result.compressed_count}条"

            tools_desc = self.tools.describe_all()

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
                    cp = self.recovery.restore()
                    if cp:
                        self._session.messages = cp.messages_snapshot
                        self._session.state = cp.state
                        self._log(f"[RECOVER] 恢复检查点: {cp.name}")
                        continue
                    else:
                        raise

            assistant_msg = Message(role="assistant", content=llm_output)
            self.session_store.add_message(sid, assistant_msg)
            self._session.messages.append(assistant_msg)

            tool_call = self._parse_tool_call(llm_output)

            if tool_call is None:
                final_response = llm_output
                break

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

            self.recovery.save(
                f"after_iteration_{iteration}",
                messages=self._session.messages,
                state=self._session.state,
            )

        if not final_response:
            final_response = "Agent 达到最大迭代次数，未能完成任务。"

        self.session_store.save_state(sid, self._session.state)
        self.recovery.clear("before_run")

        return final_response

    # ═══════════════════════════════════════════
    # 多 Agent 运行（v2 新增）
    # ═══════════════════════════════════════════

    def run_multi(
        self,
        task: str,
        user_priorities: Optional[list[str]] = None,
    ) -> dict:
        """
        运行多 Agent 编排（v2 新增）。

        Args:
            task: 用户任务
            user_priorities: 用户关注重点（如 ["安全性", "性能"]）

        Returns:
            {
                "success": bool,
                "report": str,
                "subtasks": [...],
                "gaps": [...],
                "stats": {...},
            }
        """
        if not self._llm_fn:
            raise RuntimeError("请先调用 harness.set_llm() 设置 LLM 函数")

        if not self._session:
            self.start_session()

        sid = self._session.id

        # 初始化 Orchestrator 和 Synthesizer
        if self._orchestrator is None:
            self._synthesizer = ResultSynthesizer(llm_fn=self._llm_fn)
            self._orchestrator = Orchestrator(
                expert_registry=self.experts,
                llm_fn=lambda msgs, prompt: self._llm_fn(msgs, prompt),
                synthesizer=self._synthesizer,
                default_expert_llm=lambda task: self._llm_fn([], f"完成以下任务，直接给结果：{task}"),
            )

        # 记录用户消息
        user_msg = Message(role="user", content=task)
        self.session_store.add_message(sid, user_msg)
        self._session.messages.append(user_msg)

        # 保存检查点
        self.recovery.save("before_multi_run", messages=self._session.messages, state=self._session.state)

        # 编排执行
        self._log(f"[ORCH] 开始编排，任务: {task[:80]}...")
        with self.tracer.span("orchestrate", session_id=sid) as step:
            step.input_summary = task[:200]
            try:
                result = self._orchestrator.run(task, user_priorities=user_priorities)
                step.output_summary = f"子任务: {result['stats']['completed']}/{result['stats']['total_subtasks']} 完成"
            except Exception as e:
                step.error = str(e)[:200]
                result = {
                    "success": False,
                    "report": f"编排执行失败：{e}",
                    "subtasks": [],
                    "gaps": [],
                    "stats": {},
                }

        # 记录每个专家的执行追踪
        for st in result.get("subtasks", []):
            if st.status == "done":
                with self.tracer.span(
                    "expert_call",
                    session_id=sid,
                    expert_id=st.source_expert or st.assigned_expert,
                ) as exp_step:
                    exp_step.input_summary = st.description[:200]
                    exp_step.output_summary = (st.result or "")[:200]
                    exp_step.metadata["subtask_id"] = st.id

        # 记录合成
        if result.get("report"):
            with self.tracer.span("synthesize", session_id=sid) as synth_step:
                synth_step.output_summary = result["report"][:200]

        # 保存树形消息
        for st in result.get("subtasks", []):
            if st.status == "done" and st.result:
                msg = Message(
                    role="expert",
                    content=st.result,
                    expert_id=st.source_expert or st.assigned_expert,
                    branch_id=st.id,
                    metadata={"subtask_id": st.id, "subtask": st.description},
                )
                self.session_store.add_message(sid, msg)
                self._session.messages.append(msg)

        # 能力缺口提醒
        gaps = result.get("gaps", [])
        if gaps:
            gap_msg = Message(
                role="system",
                content=f"[能力缺口] 以下领域缺少对应专家，已用 LLM 通用能力兜底：\n" + "\n".join(f"  - {g}" for g in gaps),
                metadata={"type": "gap_warning"},
            )
            self.session_store.add_message(sid, gap_msg)

        # 清理
        self.session_store.save_state(sid, self._session.state)
        self.recovery.clear("before_multi_run")

        return result

    # ═══════════════════════════════════════════
    # 工具调用解析
    # ═══════════════════════════════════════════

    def _parse_tool_call(self, llm_output: str) -> Optional[tuple[str, dict]]:
        """
        从 LLM 输出中解析工具调用。

        支持的格式（按优先级）：
          1. 代码块 JSON
          2. 内联 TOOL 语法
          3. 自然语言调用模式
        """
        import json as _json
        import re

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

        match = re.search(r'TOOL:\s*(\w+)(?:\s*\|\s*args:\s*(\{.*?\}))?', llm_output, re.DOTALL)
        if match:
            tool_name = match.group(1)
            args_str = match.group(2)
            try:
                args = _json.loads(args_str) if args_str else {}
            except _json.JSONDecodeError:
                args = {}
            return tool_name, args

        match = re.search(r'(?:调用|使用|call)\s*["「]?(\w+)["」]?\s*(?:工具|tool|专家|expert)', llm_output, re.IGNORECASE)
        if match:
            return match.group(1), {}

        return None

    # ═══════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════

    def _log(self, msg: str):
        if self._verbose:
            print(f"  {msg}")

    def stats(self) -> dict:
        """获取当前会话的统计信息"""
        sid = self._session.id if self._session else ""
        return {
            "tools_registered": len(self.tools),
            "experts_registered": len(self.experts),
            "gate_rules": len(self.gate.list_rules()),
            "agent_rules": len(self.gate.list_agent_rules()),
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
