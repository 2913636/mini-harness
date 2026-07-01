"""
组件 4：上下文压缩（Context Compressor）

聊太长了自动压缩旧消息，防止 token 爆炸。
→ 对应 Claude Code 的自动压缩
→ 对应 token 爆炸专题的压缩方案汇总
"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class CompressResult:
    """压缩结果"""
    messages: list  # 压缩后的消息列表
    original_count: int
    compressed_count: int
    estimated_tokens_before: int
    estimated_tokens_after: int
    strategy: str  # "none" | "truncate" | "summarize"


class Compressor:
    """
    上下文压缩器 —— 当 token 超限时自动压缩旧消息。

    三种压缩策略（按激进程度）：
      1. truncate  — 删最旧消息（最简单，可能丢上下文）
      2. summarize — 用 LLM 摘要旧消息（折中方案）
      3. hybrid    — 摘要旧消息 + 保留最近 N 条原文

    触发条件：
      - estimated_tokens > threshold 时自动触发
      - 或者手动调用 compress()

    用法：
        comp = Compressor(max_tokens=8000, summarize_fn=my_llm_summarize)
        result = comp.compress(messages)
    """

    def __init__(
        self,
        max_tokens: int = 8000,
        keep_recent: int = 6,  # hybrid 模式下保留最近 N 条原文
        summarize_fn: Optional[Callable] = None,  # 摘要函数：fn(messages) -> str
    ):
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent
        self._summarize_fn = summarize_fn

    # ── Token 估算 ──────────────────────

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        估算文本的 token 数。
        优先用 tiktoken（精确），不可用时用字符数 / 2.5 估算。
        """
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except (ImportError, Exception):
            # 中英文混合：大约 1 token ≈ 2.5 字符
            return max(1, len(text) // 2)

    @staticmethod
    def estimate_tokens_batch(messages: list) -> int:
        """估算消息列表的总 token 数"""
        total = 0
        for msg in messages:
            content = msg.content if hasattr(msg, "content") else str(msg)
            total += Compressor.estimate_tokens(content)
            total += 4  # 每条消息的角色标记约 4 token
        return total + 2  # 对话边界标记

    # ── 压缩 ────────────────────────────

    def needs_compression(self, messages: list) -> bool:
        """判断是否需要压缩"""
        return self.estimate_tokens_batch(messages) > self.max_tokens

    def compress(
        self,
        messages: list,
        strategy: str = "hybrid",
    ) -> CompressResult:
        """
        执行压缩。

        Args:
            messages: 消息列表
            strategy: "truncate" | "summarize" | "hybrid"

        Returns:
            CompressResult 包含压缩后的消息和统计信息
        """
        tokens_before = self.estimate_tokens_batch(messages)
        original_count = len(messages)

        if not self.needs_compression(messages):
            return CompressResult(
                messages=messages,
                original_count=original_count,
                compressed_count=original_count,
                estimated_tokens_before=tokens_before,
                estimated_tokens_after=tokens_before,
                strategy="none",
            )

        if strategy == "truncate":
            result_msgs = self._truncate(messages)
        elif strategy == "summarize":
            result_msgs = self._summarize(messages)
        else:  # hybrid
            result_msgs = self._hybrid(messages)

        tokens_after = self.estimate_tokens_batch(result_msgs)
        return CompressResult(
            messages=result_msgs,
            original_count=original_count,
            compressed_count=len(result_msgs),
            estimated_tokens_before=tokens_before,
            estimated_tokens_after=tokens_after,
            strategy=strategy,
        )

    # ── 三种策略实现 ─────────────────────

    def _truncate(self, messages: list) -> list:
        """旧消息从头部删除，直到 token 不超限"""
        result = list(messages)
        while self.estimate_tokens_batch(result) > self.max_tokens and len(result) > 2:
            # 至少保留 system prompt + 最后一条消息
            if result[0].role == "system" if hasattr(result[0], "role") else False:
                result.pop(1)  # 保留 system prompt，删下一条
            else:
                result.pop(0)
        return result

    def _summarize(self, messages: list) -> list:
        """用 LLM 摘要旧消息，压缩成一条 system 消息"""
        if not self._summarize_fn:
            return self._truncate(messages)

        # 保留最后 keep_recent 条，其余的做摘要
        if len(messages) <= self.keep_recent:
            return messages

        old = messages[:-self.keep_recent]
        recent = messages[-self.keep_recent:]

        summary_text = self._summarize_fn(old)
        from .session import Message
        summary_msg = Message(
            role="system",
            content=f"[上下文摘要] {summary_text}",
            metadata={"compressed": True, "original_count": len(old)},
        )
        return [summary_msg] + recent

    def _hybrid(self, messages: list) -> list:
        """
        混合策略：
          1. 保留 system prompt（如果有）
          2. 保留最近 keep_recent 条
          3. 中间的做摘要
        """
        if len(messages) <= self.keep_recent + 2:
            return messages

        # 找 system prompt
        sys_msg = None
        rest = list(messages)
        for i, m in enumerate(rest):
            role = m.role if hasattr(m, "role") else ""
            if role == "system":
                sys_msg = m
                rest.pop(i)
                break

        if len(rest) <= self.keep_recent:
            result = [sys_msg] + rest if sys_msg else rest
            return result

        # 分隔：旧消息 + 最近消息
        old = rest[:-self.keep_recent]
        recent = rest[-self.keep_recent:]

        # 摘要旧消息
        if self._summarize_fn:
            summary_text = self._summarize_fn(old)
            from .session import Message
            summary_msg = Message(
                role="system",
                content=f"[对话摘要] {summary_text}",
                metadata={"compressed": True, "original_count": len(old)},
            )
            result = [summary_msg] + recent
        else:
            # 无摘要函数时用截断：只保留最近的关键消息
            result = old[-2:] + recent  # 旧消息保留最后 2 条做上下文

        if sys_msg:
            result = [sys_msg] + result

        return result

    def set_summarize_fn(self, fn: Callable):
        """设置摘要函数"""
        self._summarize_fn = fn

    # ── 分支级压缩（v2 新增）────────────

    def compress_branch(
        self,
        messages: list,
        branch_id: str,
        strategy: str = "hybrid",
    ) -> CompressResult:
        """
        按分支压缩消息（v2 多 Agent 支持）。

        每个分支/专家有自己的上下文窗口。
        过滤出该分支的消息，压缩后再合并回去。

        Args:
            messages: 全部消息
            branch_id: 要压缩的分支 ID
            strategy: 压缩策略

        Returns:
            CompressResult
        """
        # 分离：该分支的消息 vs 其他消息
        branch_msgs = []
        other_msgs = []
        for m in messages:
            bid = getattr(m, "branch_id", "")
            if bid == branch_id:
                branch_msgs.append(m)
            else:
                other_msgs.append(m)

        # 只压缩该分支
        branch_compressed = self.compress(branch_msgs, strategy=strategy)

        # 合并结果
        result_msgs = other_msgs + branch_compressed.messages

        tokens_before = self.estimate_tokens_batch(messages)
        tokens_after = self.estimate_tokens_batch(result_msgs)

        return CompressResult(
            messages=result_msgs,
            original_count=len(messages),
            compressed_count=len(result_msgs),
            estimated_tokens_before=tokens_before,
            estimated_tokens_after=tokens_after,
            strategy=f"branch_{strategy}",
        )
