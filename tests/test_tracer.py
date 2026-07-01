"""组件 5: Tracer 单元测试"""

import time
import pytest
from harness.tracer import Tracer, TraceStep


class TestTraceStep:
    def test_create_step(self):
        ts = TraceStep(step_id="abc", step_type="llm_call")
        assert ts.step_id == "abc"
        assert ts.step_type == "llm_call"
        assert ts.error == ""
        assert ts.expert_id == ""

    def test_step_v2_fields(self):
        ts = TraceStep(step_id="1", step_type="expert_call", expert_id="coder", parent_step_id="root")
        assert ts.expert_id == "coder"
        assert ts.parent_step_id == "root"


class TestTracer:
    @pytest.fixture
    def tracer(self):
        t = Tracer(":memory:", verbose=False)
        yield t
        t.close()

    def test_span_records_step(self, tracer):
        with tracer.span("llm_call", session_id="s1") as step:
            step.token_used = 100
            step.output_summary = "response text"

        rows = tracer.query(session_id="s1")
        assert len(rows) == 1
        assert rows[0]["step_type"] == "llm_call"
        assert rows[0]["token_used"] == 100
        assert rows[0]["duration_ms"] > 0

    def test_span_captures_error(self, tracer):
        with pytest.raises(ValueError):
            with tracer.span("tool_call", session_id="s1"):
                raise ValueError("test error")

        rows = tracer.query(session_id="s1")
        assert len(rows) == 1
        assert "test error" in rows[0]["error"]

    def test_record_quick(self, tracer):
        step = tracer.record(
            "gate_check", session_id="s2",
            input_summary="checking calc",
            output_summary="ALLOW",
            duration_ms=5.0,
        )
        rows = tracer.query(session_id="s2")
        assert len(rows) == 1
        assert rows[0]["output_summary"] == "ALLOW"

    def test_query_by_session(self, tracer):
        tracer.record("llm_call", session_id="A")
        tracer.record("tool_call", session_id="A")
        tracer.record("llm_call", session_id="B")
        assert len(tracer.query(session_id="A")) == 2
        assert len(tracer.query(session_id="B")) == 1

    def test_query_by_type(self, tracer):
        tracer.record("llm_call", session_id="s1")
        tracer.record("llm_call", session_id="s1")
        tracer.record("tool_call", session_id="s1")
        assert len(tracer.query(step_type="llm_call")) == 2
        assert len(tracer.query(step_type="tool_call")) == 1

    def test_query_limit(self, tracer):
        for i in range(10):
            tracer.record("llm_call", session_id="s1")
        assert len(tracer.query(session_id="s1", limit=3)) == 3

    def test_stats(self, tracer):
        tracer.record("llm_call", session_id="s1", token_used=50, duration_ms=100)
        tracer.record("tool_call", session_id="s1", token_used=0, duration_ms=50, error="fail")
        tracer.record("llm_call", session_id="s2", token_used=30, duration_ms=80)

        stats_all = tracer.stats()
        assert stats_all["total_steps"] == 3
        assert stats_all["total_tokens"] == 80
        assert stats_all["errors"] >= 1

        stats_s1 = tracer.stats(session_id="s1")
        assert stats_s1["total_steps"] == 2
        assert stats_s1["total_tokens"] == 50

    def test_redact_sensitive(self):
        # Test key=value format
        result = Tracer._redact_sensitive("api_key=sk-abc123")
        assert "[REDACTED]" in result
        assert "sk-abc123" not in result

        # Test key: value format (JSON-like)
        result = Tracer._redact_sensitive('"api_key": "sk-abc123"')
        assert "[REDACTED]" in result

        # Test password pattern
        result = Tracer._redact_sensitive("password=secret123")
        assert "[REDACTED]" in result
        assert "secret123" not in result

        # Test non-sensitive text passes through
        result = Tracer._redact_sensitive("hello world")
        assert result == "hello world"

    def test_redact_sensitive_empty(self):
        assert Tracer._redact_sensitive("") == ""
        assert Tracer._redact_sensitive(None) is None

    def test_query_by_expert(self, tracer):
        tracer.record("expert_call", session_id="s1", expert_id="coder")
        tracer.record("expert_call", session_id="s1", expert_id="coder")
        tracer.record("expert_call", session_id="s1", expert_id="security")
        rows = tracer.query_by_expert("coder")
        assert len(rows) == 2

    def test_query_causal_chain(self, tracer):
        # Create a chain: root -> child -> grandchild
        root = tracer.record("orchestrate", session_id="s1")
        child = tracer.record("expert_call", session_id="s1", parent_step_id=root.step_id)
        gc = tracer.record("synthesize", session_id="s1", parent_step_id=child.step_id)

        chain = tracer.query_causal_chain(gc.step_id)
        assert len(chain) == 3

    def test_expert_stats(self, tracer):
        tracer.record("expert_call", session_id="s1", token_used=10, duration_ms=50, expert_id="coder", error="")
        tracer.record("expert_call", session_id="s1", token_used=20, duration_ms=30, expert_id="coder", error="")
        tracer.record("expert_call", session_id="s1", token_used=5, duration_ms=10, expert_id="security", error="err")

        stats = tracer.expert_stats(session_id="s1")
        assert len(stats) == 2
        # coder should be first (more calls)
        assert stats[0]["expert_id"] == "coder"
        assert stats[0]["calls"] == 2
        assert stats[0]["total_tokens"] == 30

    def test_empty_stats(self, tracer):
        stats = tracer.stats()
        assert stats["total_steps"] == 0
        assert stats["total_tokens"] == 0
        assert stats["errors"] == 0
