"""AgentHarness 集成测试"""

import pytest
from harness import AgentHarness, Message, Expert, Policy, GateRule


@pytest.fixture
def harness():
    h = AgentHarness(session_db=":memory:", trace_db=":memory:", verbose=False)
    yield h
    h.close()


def mock_llm(messages, tools_desc):
    last = messages[-1].content if messages else ""
    if "算" in last:
        return 'TOOL: calculator | args: {"expression": "2+3"}'
    if "结果" in str(last) or "=" in str(last):
        return "好的，计算完成。"
    return "请告诉我需要什么帮助？"


class TestAgentHarnessInit:
    def test_create_harness(self, harness):
        assert len(harness.tools) == 0
        assert len(harness.experts) == 0

    def test_register_tool(self, harness):
        t = harness.register_tool("calc", "计算器", {"expr": {"type": "string"}}, lambda x: x, "safe")
        assert t.name == "calc"
        assert len(harness.tools) == 1

    def test_register_expert(self, harness):
        def my_fn(task, context=None):
            return f"done: {task}"

        e = harness.register_expert(Expert(
            name="coder",
            description="代码专家",
            domain=["code"],
            capabilities=["review"],
            fn=my_fn,
        ))
        assert e.name == "coder"
        assert len(harness.experts) == 1
        # Expert should also be registered as a tool
        assert "coder" in harness.tools

    def test_unregister_expert(self, harness):
        harness.register_expert(Expert(name="coder", description="d", domain=["code"], fn=lambda t, c=None: "ok"))
        assert harness.unregister_expert("coder") is True
        assert harness.unregister_expert("coder") is False
        assert len(harness.experts) == 0

    def test_list_experts(self, harness):
        harness.register_expert(Expert(name="a", description="d", domain=["code"]))
        harness.register_expert(Expert(name="b", description="d", domain=["security"]))
        assert len(harness.list_experts()) == 2

    def test_set_llm(self, harness):
        harness.set_llm(mock_llm)
        assert harness._llm_fn is not None


class TestV1SingleAgent:
    def test_run_simple(self, harness):
        harness.set_llm(mock_llm)
        harness.start_session()
        result = harness.run("帮我算一下")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_run_creates_session_if_none(self, harness):
        harness.set_llm(mock_llm)
        result = harness.run("你好")
        assert harness.session is not None

    def test_run_with_tool_registered(self, harness):
        harness.set_llm(mock_llm)
        harness.register_tool("calculator", "计算", {"expression": {"type": "string"}}, lambda e: f"结果: {eval(e)}", "safe")
        harness.start_session()
        result = harness.run("帮我算一下")
        assert isinstance(result, str)

    def test_run_max_iterations(self, harness):
        """Should stop after max iterations even without final response"""
        def loop_llm(messages, tools_desc):
            return 'TOOL: calc | args: {"expr": "1+1"}'

        harness.set_llm(loop_llm)
        harness.register_tool("calc", "计算", {"expr": {"type": "string"}}, lambda e: "=2", "safe")
        harness.start_session()
        result = harness.run("loop", max_iterations=2)
        assert "最大迭代" in result

    def test_run_without_llm_raises(self, harness):
        harness.start_session()
        with pytest.raises(RuntimeError, match="set_llm"):
            harness.run("test")

    def test_stats(self, harness):
        harness.set_llm(mock_llm)
        harness.register_tool("calc", "计算", {"expr": {"type": "string"}}, lambda x: x, "safe")
        harness.start_session()
        harness.run("算一下")
        stats = harness.stats()
        assert "tools_registered" in stats
        assert "experts_registered" in stats
        assert stats["tools_registered"] == 1


class TestV2MultiAgent:
    def test_run_auto_upgrades_to_multi(self, harness):
        """When experts are registered, run() should auto-upgrade to run_multi()"""
        harness.set_llm(mock_llm)

        def coder_fn(task, context=None):
            return "[审查] 代码质量良好"

        harness.register_expert(Expert(
            name="coder", description="代码审查", domain=["code"], capabilities=["review"], fn=coder_fn
        ))
        harness.start_session()
        # The mock LLM will be used for decomposition and synthesis
        result = harness.run("审查代码")
        # Should return a dict (from run_multi) or string
        assert isinstance(result, (str, dict))

    def test_run_multi_with_experts(self, harness):
        harness.set_llm(mock_llm)

        def coder_fn(task, context=None):
            return "[审查] 完成"

        harness.register_expert(Expert(
            name="coder", description="代码审查专家", domain=["code"], capabilities=["review"], fn=coder_fn
        ))
        harness.start_session()
        result = harness.run_multi("审查代码")
        assert "report" in result
        assert "stats" in result
        assert "gaps" in result

    def test_run_multi_without_llm_raises(self, harness):
        harness.start_session()
        with pytest.raises(RuntimeError, match="set_llm"):
            harness.run_multi("test")

    def test_expert_performance(self, harness):
        harness.set_llm(mock_llm)
        harness.register_expert(Expert(name="coder", description="d", domain=["code"], fn=lambda t, c=None: "ok"))
        harness.start_session()
        harness.run_multi("审查代码")
        perf = harness.expert_performance()
        assert isinstance(perf, list)

    def test_allow_deny_agent_call(self, harness):
        harness.allow_agent_call("orch", "coder")
        harness.deny_agent_call("orch", "danger")
        rules = harness.gate.list_agent_rules()
        assert len(rules) == 2


class TestValidateToolArgs:
    def test_validate_valid_args(self, harness):
        from harness.tool_registry import Tool
        tool = Tool(name="test", description="d", parameters={"name": {"type": "string"}}, fn=lambda n: n)
        result = harness._validate_tool_args(tool, {"name": "Alice"})
        assert result["name"] == "Alice"

    def test_validate_unknown_arg_dropped(self, harness):
        from harness.tool_registry import Tool
        tool = Tool(name="test", description="d", parameters={"name": {"type": "string"}}, fn=lambda n: n)
        result = harness._validate_tool_args(tool, {"name": "Alice", "hack": "evil"})
        assert "name" in result
        assert "hack" not in result

    def test_validate_missing_required_raises(self, harness):
        from harness.tool_registry import Tool
        tool = Tool(name="test", description="d", parameters={"name": {"type": "string"}}, fn=lambda n: n)
        with pytest.raises(ValueError, match="缺少必填参数"):
            harness._validate_tool_args(tool, {})

    def test_validate_type_conversion(self, harness):
        from harness.tool_registry import Tool
        tool = Tool(name="test", description="d",
                    parameters={"count": {"type": "integer"}, "price": {"type": "number"}},
                    fn=lambda c, p: c)
        result = harness._validate_tool_args(tool, {"count": "5", "price": "9.99"})
        assert isinstance(result["count"], int)
        assert result["count"] == 5
        assert isinstance(result["price"], float)


class TestParseToolCall:
    def test_parse_tool_syntax(self, harness):
        result = harness._parse_tool_call('TOOL: calculator | args: {"expression": "2+3"}')
        assert result is not None
        name, args = result
        assert name == "calculator"
        assert args["expression"] == "2+3"

    def test_parse_json_block(self, harness):
        result = harness._parse_tool_call('```json\n{"tool": "search", "args": {"query": "AI"}}\n```')
        assert result is not None
        name, args = result
        assert name == "search"
        assert args["query"] == "AI"

    def test_parse_natural_language(self, harness):
        result = harness._parse_tool_call("我调用 calculator 工具来计算")
        assert result is not None
        name, args = result
        assert name == "calculator"

    def test_parse_no_tool_call(self, harness):
        result = harness._parse_tool_call("这是一条普通回复")
        assert result is None


class TestRedactMetadata:
    def test_redact_sensitive_keys(self, harness):
        meta = {"api_key": "sk-secret", "name": "test", "args": {"password": "123"}}
        redacted = harness._redact_metadata(meta)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["name"] == "test"
        # nested sensitive
        assert "args" in redacted  # args key itself is redacted

    def test_redact_empty(self, harness):
        assert harness._redact_metadata({}) == {}
        assert harness._redact_metadata(None) is None
