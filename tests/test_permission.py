"""组件 2: PermissionGate 单元测试"""

import pytest
from harness.permission import PermissionGate, Policy, GateRule, AgentRule


class TestGateRule:
    def test_create_rule(self):
        r = GateRule(tool_name="calculator", policy=Policy.ALLOW, reason="安全工具")
        assert r.tool_name == "calculator"
        assert r.policy == Policy.ALLOW

    def test_create_wildcard_rule(self):
        r = GateRule(tool_name="*", policy=Policy.DENY, reason="默认拒绝")
        assert r.tool_name == "*"


class TestAgentRule:
    def test_create_agent_rule(self):
        r = AgentRule(caller="orchestrator", callee="code_reviewer", policy=Policy.ALLOW)
        assert r.caller == "orchestrator"
        assert r.callee == "code_reviewer"
        assert r.policy == Policy.ALLOW


class TestPermissionGate:
    def test_default_category_policy_safe(self):
        gate = PermissionGate()
        assert gate.check("calculator", "safe") == Policy.ALLOW

    def test_default_category_policy_network(self):
        gate = PermissionGate()
        assert gate.check("search", "network") == Policy.ASK

    def test_default_category_policy_system(self):
        gate = PermissionGate()
        assert gate.check("exec", "system") == Policy.DENY

    def test_default_category_policy_general(self):
        gate = PermissionGate()
        assert gate.check("unknown", "general") == Policy.ASK

    def test_exact_rule_takes_priority(self):
        gate = PermissionGate()
        gate.add_rule(GateRule(tool_name="calculator", policy=Policy.ALLOW))
        # Even if category says ASK, exact rule should win
        gate.set_category_policy("safe", Policy.ASK)
        assert gate.check("calculator", "safe") == Policy.ALLOW

    def test_wildcard_rule(self):
        gate = PermissionGate()
        gate.add_rule(GateRule(tool_name="*", policy=Policy.DENY))
        assert gate.check("anything", "safe") == Policy.DENY

    def test_exact_overrides_wildcard(self):
        gate = PermissionGate()
        gate.add_rule(GateRule(tool_name="*", policy=Policy.DENY))
        gate.add_rule(GateRule(tool_name="calculator", policy=Policy.ALLOW))
        assert gate.check("calculator", "safe") == Policy.ALLOW
        assert gate.check("other", "safe") == Policy.DENY

    def test_remove_rule(self):
        gate = PermissionGate()
        gate.add_rule(GateRule(tool_name="calc", policy=Policy.DENY))
        gate.remove_rule("calc")
        assert gate.check("calc", "safe") == Policy.ALLOW  # back to category default

    def test_gate_allow(self):
        gate = PermissionGate()
        gate.add_rule(GateRule(tool_name="calc", policy=Policy.ALLOW))
        assert gate.gate("calc", "safe") is True

    def test_gate_deny(self):
        gate = PermissionGate()
        gate.add_rule(GateRule(tool_name="exec", policy=Policy.DENY))
        assert gate.gate("exec", "system") is False

    def test_gate_ask_without_callback_denies(self):
        gate = PermissionGate()
        assert gate.gate("search", "network") is False  # No callback = deny

    def test_gate_ask_with_callback_allows(self):
        def always_allow(tool_name, reason):
            return True

        gate = PermissionGate(confirm_callback=always_allow)
        assert gate.gate("search", "network") is True

    def test_gate_ask_with_callback_denies(self):
        def always_deny(tool_name, reason):
            return False

        gate = PermissionGate(confirm_callback=always_deny)
        assert gate.gate("search", "network") is False

    def test_set_category_policy(self):
        gate = PermissionGate()
        gate.set_category_policy("safe", Policy.DENY)
        assert gate.check("calc", "safe") == Policy.DENY

    def test_category_resolver(self):
        gate = PermissionGate()
        # Mock resolver: all tools are "system"
        gate.set_category_resolver(lambda name: "system")
        assert gate.check("anything", "safe") == Policy.DENY

    def test_list_rules(self):
        gate = PermissionGate()
        gate.add_rule(GateRule(tool_name="a", policy=Policy.ALLOW))
        gate.add_rule(GateRule(tool_name="b", policy=Policy.DENY))
        assert len(gate.list_rules()) == 2

    # ── Agent 间调用规则 ──

    def test_agent_call_default_deny(self):
        gate = PermissionGate()
        assert gate.check_agent_call("orch", "expert_a") == Policy.DENY

    def test_agent_call_exact_match(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="orch", callee="coder", policy=Policy.ALLOW))
        assert gate.check_agent_call("orch", "coder") == Policy.ALLOW

    def test_agent_call_wildcard_caller(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="*", callee="coder", policy=Policy.ALLOW))
        assert gate.check_agent_call("anyone", "coder") == Policy.ALLOW

    def test_agent_call_wildcard_callee(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="orch", callee="*", policy=Policy.ALLOW))
        assert gate.check_agent_call("orch", "anyone") == Policy.ALLOW

    def test_agent_call_wildcard_both(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="*", callee="*", policy=Policy.ALLOW))
        assert gate.check_agent_call("a", "b") == Policy.ALLOW

    def test_agent_call_exact_overrides_wildcard(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="*", callee="*", policy=Policy.ALLOW))
        gate.add_agent_rule(AgentRule(caller="orch", callee="danger", policy=Policy.DENY))
        assert gate.check_agent_call("orch", "danger") == Policy.DENY
        assert gate.check_agent_call("orch", "safe") == Policy.ALLOW

    def test_gate_agent_call_allow(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="orch", callee="coder", policy=Policy.ALLOW))
        assert gate.gate_agent_call("orch", "coder") is True

    def test_gate_agent_call_deny(self):
        gate = PermissionGate()
        assert gate.gate_agent_call("orch", "coder") is False  # Default DENY

    def test_remove_agent_rule(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="a", callee="b", policy=Policy.ALLOW))
        assert gate.check_agent_call("a", "b") == Policy.ALLOW
        gate.remove_agent_rule("a", "b")
        assert gate.check_agent_call("a", "b") == Policy.DENY

    def test_list_agent_rules(self):
        gate = PermissionGate()
        gate.add_agent_rule(AgentRule(caller="a", callee="b", policy=Policy.ALLOW))
        assert len(gate.list_agent_rules()) == 1
