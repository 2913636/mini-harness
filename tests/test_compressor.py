"""组件 4: Compressor 单元测试"""

import pytest
from harness.compressor import Compressor, CompressResult
from harness.session import Message


def make_msgs(count: int, prefix: str = "msg") -> list[Message]:
    """Helper: create a list of messages"""
    return [Message(role="user", content=f"{prefix} {i} " + "extra text " * 10) for i in range(count)]


class TestTokenEstimation:
    def test_estimate_tokens_non_empty(self):
        tokens = Compressor.estimate_tokens("hello world")
        assert tokens >= 1

    def test_estimate_tokens_empty(self):
        tokens = Compressor.estimate_tokens("")
        assert tokens >= 0  # tiktoken returns 0 for empty string; fallback returns 1

    def test_estimate_tokens_batch(self):
        msgs = [
            Message(role="user", content="hello"),
            Message(role="assistant", content="world"),
        ]
        tokens = Compressor.estimate_tokens_batch(msgs)
        # Each message: content tokens + 4 role overhead + 2 boundary
        assert tokens > 0

    def test_estimate_tokens_batch_empty(self):
        tokens = Compressor.estimate_tokens_batch([])
        assert tokens == 2  # Only boundary tokens


class TestCompressor:
    def test_needs_compression_false(self):
        comp = Compressor(max_tokens=100000)
        msgs = make_msgs(3)
        assert comp.needs_compression(msgs) is False

    def test_needs_compression_true(self):
        comp = Compressor(max_tokens=10)  # Very low threshold
        msgs = make_msgs(20, "long message with many words to exceed token limit")
        assert comp.needs_compression(msgs) is True

    def test_compress_no_need_returns_unchanged(self):
        comp = Compressor(max_tokens=100000)
        msgs = make_msgs(3)
        result = comp.compress(msgs)
        assert result.strategy == "none"
        assert result.messages == msgs

    def test_truncate_reduces_count(self):
        comp = Compressor(max_tokens=10, keep_recent=1)
        msgs = make_msgs(30, "very long message text " * 5)
        result = comp.compress(msgs, strategy="truncate")
        assert len(result.messages) < len(msgs)
        assert result.strategy == "truncate"

    def test_summarize_without_fn_falls_back_to_truncate(self):
        comp = Compressor(max_tokens=10, keep_recent=1)
        msgs = make_msgs(20, "long " * 20)
        result = comp.compress(msgs, strategy="summarize")
        assert len(result.messages) < len(msgs)

    def test_summarize_with_fn(self):
        def mock_summarize(old_msgs):
            return "摘要：" + "; ".join(m.content[:20] for m in old_msgs)

        comp = Compressor(max_tokens=10, keep_recent=2, summarize_fn=mock_summarize)
        msgs = make_msgs(15, "long " * 20)
        result = comp.compress(msgs, strategy="summarize")
        assert len(result.messages) < len(msgs)
        # Should have a summary message
        summaries = [m for m in result.messages if "摘要" in m.content]
        assert len(summaries) >= 1

    def test_hybrid_with_summarize_fn(self):
        def mock_summarize(old_msgs):
            return "摘要内容"

        comp = Compressor(max_tokens=10, keep_recent=2, summarize_fn=mock_summarize)
        msgs = make_msgs(15, "long " * 20)
        result = comp.compress(msgs, strategy="hybrid")
        assert len(result.messages) < len(msgs)

    def test_hybrid_preserves_system_prompt(self):
        def mock_summarize(old_msgs):
            return "摘要"

        comp = Compressor(max_tokens=10, keep_recent=2, summarize_fn=mock_summarize)
        msgs = [Message(role="system", content="You are helpful")] + make_msgs(15, "long " * 20)
        result = comp.compress(msgs, strategy="hybrid")
        assert result.messages[0].role == "system"
        assert "You are helpful" in result.messages[0].content

    def test_set_summarize_fn(self):
        comp = Compressor(max_tokens=100000)
        called = []

        def fn(msgs):
            called.append(1)
            return "summary"

        comp.set_summarize_fn(fn)
        msgs = make_msgs(20, "long " * 20)
        result = comp.compress(msgs, strategy="summarize")
        # If compression was needed, fn should have been called
        if result.strategy != "none":
            assert len(called) > 0

    def test_compress_result_fields(self):
        comp = Compressor(max_tokens=100000)
        msgs = make_msgs(5)
        result = comp.compress(msgs)
        assert result.original_count == 5
        assert result.estimated_tokens_before > 0
        assert result.estimated_tokens_after > 0

    # ── 分支级压缩 ──

    def test_compress_branch_filters_correctly(self):
        def mock_summarize(old_msgs):
            return "branch summary"

        comp = Compressor(max_tokens=10, keep_recent=1, summarize_fn=mock_summarize)
        msgs = [
            Message(role="user", content="task"),
            Message(role="expert", content="long " * 50, branch_id="b1"),
            Message(role="expert", content="long " * 50, branch_id="b1"),
            Message(role="expert", content="result", branch_id="b2"),
        ]
        result = comp.compress_branch(msgs, branch_id="b1", strategy="hybrid")
        assert result.strategy == "branch_hybrid"
        # b2 message should remain untouched
        b2_msgs = [m for m in result.messages if getattr(m, "branch_id", "") == "b2"]
        assert len(b2_msgs) == 1
