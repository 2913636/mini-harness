"""
组件 8：结果合成器（Result Synthesizer）— v2 新增

多专家输出汇总，按用户意图加权，生成带来源标记的最终报告。
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class SourceBlock:
    """一个带来源标记的内容块"""
    content: str
    source_expert: str       # 来自哪个专家
    subtask: str = ""        # 对应哪个子任务
    confidence: str = ""     # 置信度标注（可选）


class ResultSynthesizer:
    """
    结果合成器 —— 将多个专家的输出合并为最终报告。

    核心能力：
      1. 按用户意图加权（用户说「重点看安全」→ 安全专家结论权重更高）
      2. 去重合并（两个专家说了同一件事，只呈现一次）
      3. 来源标注（每段结论标记来自哪个专家）

    用法：
        synth = ResultSynthesizer(llm_fn=my_llm)
        report = synth.synthesize(
            task="分析代码安全性",
            results=[
                {"expert": "code_reviewer", "subtask": "代码审查", "result": "..."},
                {"expert": "security_expert", "subtask": "安全分析", "result": "..."},
            ],
            user_priorities=["安全性"],
        )
    """

    def __init__(self, llm_fn: Optional[Callable] = None):
        """
        Args:
            llm_fn: LLM 调用函数，用于智能去重和合并。
                    签名为 fn(prompt: str) -> str。
                    如果为 None，使用基于规则的简单合并。
        """
        self._llm_fn = llm_fn

    # ── 核心合成 ────────────────────────

    def synthesize(
        self,
        task: str,
        results: list[dict],
        user_priorities: Optional[list[str]] = None,
    ) -> str:
        """
        合成多个专家的结果。

        Args:
            task: 用户原始任务
            results: [
                {"expert": str, "subtask": str, "result": str},
                ...
            ]
            user_priorities: 用户强调的重点（如 ["安全性", "性能"]）

        Returns:
            带来源标记的最终报告（Markdown 格式）
        """
        if not results:
            return "（无专家结果可合成）"

        # 1. 解析结果，提取来源块
        sources = self._extract_sources(results)

        # 2. 去重
        deduped = self._deduplicate(sources)

        # 3. 按优先级排序
        ordered = self._prioritize(deduped, user_priorities or [])

        # 4. 生成最终报告
        if self._llm_fn:
            report = self._llm_synthesize(task, ordered, user_priorities)
        else:
            report = self._rule_synthesize(task, ordered, user_priorities)

        return report

    # ── 内部步骤 ────────────────────────

    def _extract_sources(self, results: list[dict]) -> list[SourceBlock]:
        """从各专家结果中提取来源块"""
        sources = []
        for r in results:
            expert = r.get("expert", "unknown")
            subtask = r.get("subtask", "")
            result = r.get("result", "")
            sources.append(SourceBlock(
                content=result,
                source_expert=expert,
                subtask=subtask,
                confidence=r.get("confidence", ""),
            ))
        return sources

    def _deduplicate(self, sources: list[SourceBlock]) -> list[SourceBlock]:
        """简单去重：基于内容相似度的 block 合并"""
        if len(sources) <= 1:
            return sources

        # 基于 Jaccard 相似度的简单去重
        kept = [sources[0]]
        for s in sources[1:]:
            is_dup = False
            s_words = set(s.content.lower().split())
            for k in kept:
                if not s_words:
                    continue
                k_words = set(k.content.lower().split())
                if not k_words:
                    continue
                overlap = len(s_words & k_words)
                union = len(s_words | k_words)
                similarity = overlap / union if union > 0 else 0
                if similarity > 0.7:
                    # 相似度高，合并来源
                    if s.source_expert not in k.source_expert:
                        k.source_expert += f", {s.source_expert}"
                    is_dup = True
                    break
            if not is_dup:
                kept.append(s)
        return kept

    def _prioritize(
        self,
        sources: list[SourceBlock],
        priorities: list[str],
    ) -> list[SourceBlock]:
        """按用户优先级重新排序"""
        if not priorities:
            return sources

        def priority_score(block: SourceBlock) -> int:
            score = 0
            content_lower = block.content.lower()
            source_lower = block.source_expert.lower()
            for i, p in enumerate(priorities):
                p_lower = p.lower()
                # 内容命中优先级关键词
                if p_lower in content_lower:
                    score += (len(priorities) - i) * 10
                # 来源命中
                if p_lower in source_lower:
                    score += (len(priorities) - i) * 5
            return score

        return sorted(sources, key=priority_score, reverse=True)

    # ── 生成策略 ────────────────────────

    def _rule_synthesize(
        self,
        task: str,
        sources: list[SourceBlock],
        priorities: Optional[list[str]],
    ) -> str:
        """基于规则的合成（无 LLM 时使用）"""
        lines = [
            "# 最终报告",
            "",
            f"> 原始任务：{task}",
        ]
        if priorities:
            lines.append(f"> 用户关注重点：{', '.join(priorities)}")
        lines.append(f"> 参与专家：{len(sources)} 个")
        lines.append("")
        lines.append("---")
        lines.append("")

        for i, s in enumerate(sources, 1):
            lines.append(f"## {i}. {s.subtask or '专家分析'}")
            lines.append(f"> 来源：**{s.source_expert}**")
            if s.confidence:
                lines.append(f"> 置信度：{s.confidence}")
            lines.append("")
            lines.append(s.content.strip())
            lines.append("")
            lines.append("---")
            lines.append("")

        lines.append("## 综合结论")
        lines.append("")
        lines.append(f"以上分析由 {', '.join(set(s.source_expert for s in sources))} 共同完成。")
        if priorities:
            lines.append(f"报告已按用户指定的重点（{', '.join(priorities)}）调整权重。")

        return "\n".join(lines)

    def _llm_synthesize(
        self,
        task: str,
        sources: list[SourceBlock],
        priorities: Optional[list[str]],
    ) -> str:
        """用 LLM 智能合成"""
        prompt_parts = [
            "请根据以下多位专家的分析结果，生成一份综合性报告。",
            "",
            f"原始任务：{task}",
        ]
        if priorities:
            prompt_parts.append(f"用户特别关注：{', '.join(priorities)}，请在这些方面加大权重。")
        prompt_parts.append("")
        prompt_parts.append("## 专家分析结果：")
        for i, s in enumerate(sources, 1):
            prompt_parts.append(f"### 专家 {i}：{s.source_expert}（子任务：{s.subtask}）")
            prompt_parts.append(s.content[:2000])  # 限制长度
            prompt_parts.append("")
        prompt_parts.append("## 要求：")
        prompt_parts.append("1. 合并重复观点，每个结论只出现一次")
        prompt_parts.append("2. 每段结论标注来源：[来源: 专家名]")
        prompt_parts.append("3. 用户强调的重点结论放在前面")

        prompt = "\n".join(prompt_parts)

        try:
            llm_result = self._llm_fn(prompt)
            return llm_result
        except Exception:
            # LLM 失败时降级到规则合成
            return self._rule_synthesize(task, sources, priorities)
