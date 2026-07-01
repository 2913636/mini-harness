"""
组件 7：专家注册表（Expert Registry）— v2 新增

管理多 Agent 系统中的专家 Agent。
专家 != 工具：工具是「给参数→执行」，专家是「给任务→思考→执行→返回」。
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Expert:
    """一个专家 Agent 的定义"""

    name: str
    description: str              # 自然语言描述，编排者用
    domain: list[str] = field(default_factory=list)  # 擅长领域标签
    capabilities: list[str] = field(default_factory=list)  # 具体能力
    fn: Optional[Callable] = None  # 执行函数: fn(task: str, context: dict) -> str
    llm_fn: Optional[Callable] = None  # 专用 LLM（可选，无则用系统默认 LLM）
    metadata: dict = field(default_factory=dict)

    def describe(self) -> str:
        """专家能力摘要"""
        domains = ", ".join(self.domain) if self.domain else "通用"
        caps = "; ".join(self.capabilities[:5]) if self.capabilities else "待补充"
        return f"[{self.name}] 领域: {domains} | 能力: {caps} | {self.description}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
        }


class ExpertRegistry:
    """
    专家注册表 —— 管理所有可用的专家 Agent。

    职责：
      - 注册/注销专家
      - 按领域/名称查找专家
      - 为编排者生成专家目录
      - 任务-专家匹配度计算（基于领域和能力的文本匹配）

    用法：
        registry = ExpertRegistry()
        registry.register(Expert(
            name="code_reviewer",
            description="审查代码质量，发现潜在 bug",
            domain=["code", "quality"],
            capabilities=["代码审查", "安全扫描", "性能分析"],
            fn=my_code_review_function,
        ))
        matches = registry.match("审查这段 Python 代码有没有内存泄漏")
    """

    def __init__(self):
        self._experts: dict[str, Expert] = {}

    # ── 注册 / 注销 ─────────────────────

    def register(self, expert: Expert) -> Expert:
        """注册一个专家。同名覆盖旧注册。"""
        if not expert.name:
            raise ValueError("Expert name cannot be empty")
        if not expert.description:
            raise ValueError(f"Expert '{expert.name}' requires a description")
        self._experts[expert.name] = expert
        return expert

    def unregister(self, name: str) -> bool:
        """注销专家，返回是否成功"""
        if name in self._experts:
            del self._experts[name]
            return True
        return False

    # ── 查询 ────────────────────────────

    def get(self, name: str) -> Optional[Expert]:
        """按名称查找"""
        return self._experts.get(name)

    def list_all(self) -> list[Expert]:
        """列出所有专家"""
        return list(self._experts.values())

    def find_by_domain(self, domain: str) -> list[Expert]:
        """按领域查找"""
        return [
            e for e in self._experts.values()
            if domain.lower() in [d.lower() for d in e.domain]
        ]

    def __len__(self) -> int:
        return len(self._experts)

    def __contains__(self, name: str) -> bool:
        return name in self._experts

    # ── 匹配（文本相似度）───────────────

    def match(self, task_description: str) -> list[tuple[Expert, float]]:
        """
        根据任务描述匹配最合适的专家。

        匹配策略：
          1. 领域关键词匹配（domain 命中 +0.3/个）
          2. 能力关键词匹配（capability 命中 +0.2/个）
          3. 描述语义匹配（description 关键词命中 +0.1/个）

        Returns:
            [(expert, score), ...] 按分数降序排列
        """
        task_lower = task_description.lower()
        scored: list[tuple[Expert, float]] = []

        for expert in self._experts.values():
            score = 0.0

            # 领域匹配
            for d in expert.domain:
                if d.lower() in task_lower:
                    score += 0.3

            # 能力匹配
            for c in expert.capabilities:
                if c.lower() in task_lower:
                    score += 0.2

            # 描述匹配
            desc_words = set(expert.description.lower().split())
            task_words = set(task_lower.split())
            overlap = desc_words & task_words
            score += len(overlap) * 0.05

            if score > 0:
                scored.append((expert, min(score, 1.0)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    # ── 给编排者用的目录 ────────────────

    def describe_all(self) -> str:
        """生成所有专家的能力目录，供编排者拆解任务时参考"""
        if not self._experts:
            return "（无可用专家）"
        lines = ["## 可用专家目录"]
        for i, e in enumerate(self._experts.values(), 1):
            domains = ", ".join(e.domain) if e.domain else "通用"
            caps = "; ".join(e.capabilities) if e.capabilities else "待补充"
            lines.append(f"{i}. **{e.name}** [{domains}]")
            lines.append(f"   {e.description}")
            if e.capabilities:
                lines.append(f"   能力: {caps}")
        return "\n".join(lines)

    def describe_for_llm(self) -> list[dict]:
        """导出为 LLM 可用的 JSON 列表"""
        return [e.to_dict() for e in self._experts.values()]
