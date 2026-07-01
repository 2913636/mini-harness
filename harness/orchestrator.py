"""
组件 9：编排者引擎（Orchestrator）— v2 核心新增

编排者→专家（Orchestrator-Expert）拓扑。

职责：
  1. 意图解析 — 分析用户任务
  2. 任务拆解 — 拆为子任务 DAG
  3. 专家匹配 — 匹配子任务到专家
  4. 缺口检测 — 缺少专家时告知用户
  5. 调度执行 — 按依赖顺序派发子任务
  6. 结果合成 — 调用 Synthesizer 生成最终报告
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .expert import ExpertRegistry, Expert
from .synthesizer import ResultSynthesizer


def _call_with_context(fn: Callable, task: str, context: dict) -> str:
    """用统一约定调用函数 fn(task, context)，通过 TypeError 降级兼容不同签名。

    约定签名: fn(task: str, context: dict) -> str
    降级顺序: fn(task, context) → fn(task) → fn()
    """
    try:
        return fn(task, context)
    except TypeError:
        try:
            return fn(task)
        except TypeError:
            return fn()


@dataclass
class SubTask:
    """一个子任务"""
    id: str
    description: str
    required_domains: list[str] = field(default_factory=list)
    assigned_expert: str = ""       # 指派给哪个专家
    dependencies: list[str] = field(default_factory=list)  # 依赖的子任务 ID
    priority: str = "P0"            # P0/P1/P2
    result: str = ""                # 执行结果
    source_expert: str = ""         # 实际执行的专家
    status: str = "pending"         # pending/running/done/failed
    duration_ms: float = 0.0


class Orchestrator:
    """
    编排者引擎 —— 多 Agent 协作的指挥中心。

    工作流：
      decompose → match → [detect_gaps] → execute → synthesize

    用法：
        orch = Orchestrator(
            expert_registry=registry,
            llm_fn=my_llm,
            synthesizer=synth,
        )
        result = orch.run("分析代码安全性并写报告")
    """

    def __init__(
        self,
        expert_registry: ExpertRegistry,
        llm_fn: Callable,
        synthesizer: Optional[ResultSynthesizer] = None,
        default_expert_llm: Optional[Callable] = None,
    ):
        """
        Args:
            expert_registry: 专家注册表
            llm_fn: 编排者自己的 LLM（用于拆解和匹配）
            synthesizer: 结果合成器（None 则自动创建）
            default_expert_llm: 专家的默认 LLM（当专家自己没有 LLM 时使用）
        """
        self.registry = expert_registry
        self._llm_fn = llm_fn
        self.synthesizer = synthesizer or ResultSynthesizer(llm_fn=llm_fn)
        self._default_expert_llm = default_expert_llm
        self._history: list[dict] = []  # 执行历史

    # ── 主流程 ──────────────────────────

    def run(
        self,
        task: str,
        user_priorities: Optional[list[str]] = None,
        max_iterations: int = 10,
    ) -> dict:
        """
        执行完整的多 Agent 编排流程。

        Args:
            task: 用户任务
            user_priorities: 用户关注重点
            max_iterations: 最大迭代次数

        Returns:
            {
                "success": bool,
                "report": str,           # 最终报告
                "subtasks": [...],       # 子任务和结果
                "gaps": [...],           # 能力缺口
                "stats": {...},          # 统计
            }
        """
        t0 = time.perf_counter()

        # 步骤 1：拆解任务
        subtasks = self.decompose(task)

        # 步骤 2：检测能力缺口
        gaps = self.detect_gaps(subtasks)

        # 步骤 3：匹配专家
        subtasks = self.match_experts(subtasks)

        # 步骤 4：调度执行
        subtasks = self._execute_dag(subtasks, max_iterations)

        # 步骤 5：合成结果
        results_for_synth = [
            {
                "expert": st.source_expert or st.assigned_expert,
                "subtask": st.description,
                "result": st.result,
                "confidence": "",
            }
            for st in subtasks
            if st.status == "done" and st.result
        ]
        report = self.synthesizer.synthesize(
            task=task,
            results=results_for_synth,
            user_priorities=user_priorities,
        )

        elapsed = (time.perf_counter() - t0) * 1000

        return {
            "success": len(gaps) == 0 or any(st.status == "done" for st in subtasks),
            "report": report,
            "subtasks": subtasks,
            "gaps": gaps,
            "stats": {
                "total_subtasks": len(subtasks),
                "completed": sum(1 for st in subtasks if st.status == "done"),
                "failed": sum(1 for st in subtasks if st.status == "failed"),
                "gaps": len(gaps),
                "duration_ms": elapsed,
            },
        }

    # ── 步骤 1：拆解 ────────────────────

    # 合法子任务 ID 和优先级的白名单
    _VALID_ID_PATTERN = None  # lazily compiled
    _VALID_PRIORITIES = {"P0", "P1", "P2"}

    @classmethod
    def _validate_subtask(cls, item: dict, seen_ids: set) -> SubTask | None:
        """验证并清洗 LLM 返回的子任务数据，非法数据返回 None"""
        import re
        if cls._VALID_ID_PATTERN is None:
            cls._VALID_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,32}$')

        raw_id = str(item.get("id", ""))
        # 校验 ID 格式：仅允许字母数字、下划线、连字符，最长 32 字符
        if not cls._VALID_ID_PATTERN.match(raw_id):
            return None
        if raw_id in seen_ids:
            return None

        desc = str(item.get("description", "")).strip()
        # 描述不能为空，且限制长度防止注入
        if not desc or len(desc) > 2000:
            return None

        # 领域白名单校验（只保留已知领域）
        known_domains = {
            "code", "security", "doc", "data", "search", "testing",
            "quality", "general", "devops", "frontend", "backend",
        }
        raw_domains = item.get("required_domains", [])
        if not isinstance(raw_domains, list):
            raw_domains = []
        domains = [str(d).lower() for d in raw_domains if str(d).lower() in known_domains]

        # 依赖 ID 校验
        raw_deps = item.get("dependencies", [])
        if not isinstance(raw_deps, list):
            raw_deps = []
        deps = [str(d) for d in raw_deps if cls._VALID_ID_PATTERN.match(str(d))]

        priority = str(item.get("priority", "P0")).upper()
        if priority not in cls._VALID_PRIORITIES:
            priority = "P0"

        seen_ids.add(raw_id)
        return SubTask(
            id=raw_id,
            description=desc,
            required_domains=domains,
            dependencies=deps,
            priority=priority,
        )

    def decompose(self, task: str) -> list[SubTask]:
        """
        用 LLM 将用户任务拆解为子任务。

        如果 LLM 不可用，用规则兜底：整个任务作为一个子任务。
        """
        try:
            return self._llm_decompose(task)
        except Exception:
            return self._rule_decompose(task)

    def _llm_decompose(self, task: str) -> list[SubTask]:
        """LLM 拆解"""
        expert_catalog = self.registry.describe_all()

        prompt = f"""你是一个任务编排专家。请将以下用户任务拆解为可并行/串行的子任务。

{expert_catalog}

用户任务：{task}

请以 JSON 格式输出子任务列表（不要有其他文字）：
```json
[
  {{
    "id": "1",
    "description": "子任务描述",
    "required_domains": ["需要的领域标签"],
    "dependencies": [],
    "priority": "P0"
  }}
]
```

规则：
- 每个子任务尽量只涉及一个领域，便于指派给对应专家
- 如果子任务之间有依赖（B 需要 A 的结果），在 dependencies 中标注
- 最多拆 5 个子任务
- 如果某个子任务需要的领域没有对应专家，仍然列出来
"""
        response = self._llm_fn([], prompt)

        # 解析 LLM 返回的 JSON
        import re
        import json as _json

        # 加固正则：先找代码块 JSON 数组，使用贪婪匹配避免嵌套括号截断
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', response, re.DOTALL)
        if match:
            raw = match.group(1).strip()
            # 找到最外层的 JSON 数组
            arr_match = re.search(r'\[.*\]', raw, re.DOTALL)
            if arr_match:
                raw = arr_match.group(0)
            else:
                return self._rule_decompose(task)
        else:
            # 尝试在全文直接找 JSON 数组
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                raw = match.group(0)
            else:
                return self._rule_decompose(task)

        try:
            items = _json.loads(raw)
        except _json.JSONDecodeError:
            return self._rule_decompose(task)

        if not isinstance(items, list):
            return self._rule_decompose(task)

        # 使用验证器清洗数据
        seen_ids: set = set()
        subtasks = []
        for item in items:
            if not isinstance(item, dict):
                continue
            st = self._validate_subtask(item, seen_ids)
            if st is not None:
                subtasks.append(st)

        return subtasks if subtasks else self._rule_decompose(task)

    def _rule_decompose(self, task: str) -> list[SubTask]:
        """规则兜底：整个任务作为一个子任务，尝试匹配专家"""
        # 根据领域关键词自动拆
        domain_keywords = {
            "code": ["代码", "编程", "bug", "重构", "review", "代码审查", "测试"],
            "security": ["安全", "漏洞", "攻击", "加密", "权限"],
            "doc": ["文档", "报告", "说明", "README", "简报", "写"],
            "data": ["数据", "分析", "统计", "报表", "挖掘"],
            "search": ["搜索", "检索", "查询", "查找"],
            "testing": ["测试", "单元测试", "集成测试", "用例"],
        }

        task_lower = task.lower()
        found_domains = []
        for domain, keywords in domain_keywords.items():
            for kw in keywords:
                if kw in task_lower or kw in task:
                    found_domains.append(domain)
                    break

        if not found_domains:
            found_domains = ["general"]

        return [
            SubTask(
                id="1",
                description=task,
                required_domains=found_domains,
                priority="P0",
            )
        ]

    # ── 步骤 2：缺口检测 ─────────────────

    def detect_gaps(self, subtasks: list[SubTask]) -> list[str]:
        """
        检测能力缺口：列出有子任务需求但无专家覆盖的领域。

        Returns:
            缺失的领域/能力描述列表
        """
        gaps = []
        all_expert_domains: set[str] = set()
        for expert in self.registry.list_all():
            all_expert_domains.update(d.lower() for d in expert.domain)

        for st in subtasks:
            for domain in st.required_domains:
                if domain.lower() not in all_expert_domains:
                    gap_desc = f"缺少 '{domain}' 领域的专家（子任务: {st.description[:50]}）"
                    if gap_desc not in gaps:
                        gaps.append(gap_desc)

        return gaps

    # ── 步骤 3：专家匹配 ─────────────────

    def match_experts(self, subtasks: list[SubTask]) -> list[SubTask]:
        """为每个子任务匹配最佳专家"""
        for st in subtasks:
            # 综合 description 和 required_domains 做匹配
            search_text = st.description + " " + " ".join(st.required_domains)
            matches = self.registry.match(search_text)

            if matches:
                # 选择得分最高的专家
                best_expert, best_score = matches[0]
                st.assigned_expert = best_expert.name
            else:
                st.assigned_expert = ""  # 无匹配专家

        return subtasks

    # ── 步骤 4：DAG 调度执行 ─────────────

    def _execute_dag(
        self,
        subtasks: list[SubTask],
        max_iterations: int,
    ) -> list[SubTask]:
        """
        按 DAG 依赖顺序执行子任务。

        有依赖的子任务，等依赖完成后才执行，并将上游结果传入 context。
        没有依赖的子任务可以并行执行。
        """
        completed_ids: set[str] = set()
        # 收集已完成子任务的结果，供下游专家使用
        completed_results: dict[str, str] = {}
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            all_done = True

            for st in subtasks:
                if st.status == "done" or st.status == "failed":
                    continue

                all_done = False

                # 检查依赖是否全部完成
                deps_ready = all(dep in completed_ids for dep in st.dependencies)
                if not deps_ready:
                    continue

                # 构建上下文：包含当前子任务描述 + 依赖子任务的结果
                context = {"subtask": st.description}
                if st.dependencies:
                    context["dependencies"] = {
                        dep_id: completed_results.get(dep_id, "")
                        for dep_id in st.dependencies
                    }

                # 执行子任务
                st.status = "running"
                try:
                    result = self._execute_subtask(st, context)
                    st.result = result
                    st.status = "done"
                    completed_ids.add(st.id)
                    completed_results[st.id] = result
                except Exception:
                    st.result = "子任务执行失败，已自动降级处理。"
                    st.status = "failed"

            if all_done:
                break

        return subtasks

    def _execute_subtask(self, subtask: SubTask, context: dict | None = None) -> str:
        """执行单个子任务：调用匹配的专家或 LLM 兜底。

        专家函数统一约定签名 fn(task: str, context: dict) -> str。
        通过 TypeError 降级兼容不同参数数量的函数，不再使用
        inspect.signature 做脆弱判断。

        Args:
            subtask: 要执行的子任务
            context: 执行上下文，包含 {"subtask": ..., "dependencies": {...}}
        """
        expert_name = subtask.assigned_expert
        ctx = context or {"subtask": subtask.description}

        if expert_name:
            expert = self.registry.get(expert_name)

            if expert and expert.fn:
                t0 = time.perf_counter()
                try:
                    result = _call_with_context(expert.fn, subtask.description, ctx)
                    subtask.source_expert = expert_name
                except Exception:
                    # 专家执行失败 → LLM 兜底
                    result = self._fallback_llm(subtask)
                    subtask.source_expert = f"{expert_name}(fallback)"
                subtask.duration_ms = (time.perf_counter() - t0) * 1000
                return result
            elif expert and expert.llm_fn:
                t0 = time.perf_counter()
                try:
                    result = _call_with_context(expert.llm_fn, subtask.description, ctx)
                    subtask.source_expert = expert_name
                except Exception:
                    result = self._fallback_llm(subtask)
                    subtask.source_expert = f"{expert_name}(fallback)"
                subtask.duration_ms = (time.perf_counter() - t0) * 1000
                return result

        # LLM 兜底
        t0 = time.perf_counter()
        result = self._fallback_llm(subtask)
        subtask.source_expert = "llm_fallback"
        subtask.duration_ms = (time.perf_counter() - t0) * 1000
        return result

    def _fallback_llm(self, subtask: SubTask) -> str:
        """LLM 通用兜底"""
        if self._default_expert_llm:
            try:
                result = self._default_expert_llm(subtask.description)
                return result
            except Exception:
                pass

        try:
            prompt = f"""你是一个通用 AI 助手。请完成以下任务：

{subtask.description}

请直接给出结果，不需要询问更多信息。"""
            result = self._llm_fn([], prompt)
            return result
        except Exception:
            return f"（无法完成子任务 '{subtask.id}'：{subtask.description[:100]}... —— 请注册对应领域的专家或配置 LLM）"

    # ── 历史记录 ────────────────────────

    @property
    def history(self) -> list[dict]:
        return self._history
