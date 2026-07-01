"""组件 1: ToolRegistry 单元测试"""

import pytest
from harness.tool_registry import ToolRegistry, Tool


class TestTool:
    def test_create_tool(self):
        t = Tool(name="calc", description="计算器", parameters={"expr": {"type": "string"}}, fn=lambda x: x)
        assert t.name == "calc"
        assert t.category == "general"
        assert t.tags == []

    def test_to_schema(self):
        t = Tool(name="search", description="搜索", parameters={"query": {"type": "string"}}, fn=lambda x: x)
        schema = t.to_schema()
        assert schema["name"] == "search"
        assert schema["inputSchema"]["type"] == "object"
        assert "query" in schema["inputSchema"]["properties"]

    def test_tool_with_tags(self):
        t = Tool(name="admin", description="管理", parameters={}, fn=lambda: None, category="system", tags=["dangerous"])
        assert t.category == "system"
        assert "dangerous" in t.tags


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        reg.register("greet", "打招呼", {"name": {"type": "string"}}, lambda name: f"Hi {name}")
        assert len(reg) == 1
        assert "greet" in reg
        t = reg.get("greet")
        assert t is not None
        assert t.name == "greet"

    def test_register_overwrite(self):
        reg = ToolRegistry()
        reg.register("t1", "v1", {}, lambda: 1)
        reg.register("t1", "v2", {}, lambda: 2)
        assert len(reg) == 1
        assert reg.get("t1").description == "v2"

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register("t1", "d", {}, lambda: None)
        assert reg.unregister("t1") is True
        assert reg.unregister("t1") is False
        assert len(reg) == 0

    def test_list_all(self):
        reg = ToolRegistry()
        reg.register("a", "d", {}, lambda: None)
        reg.register("b", "d", {}, lambda: None)
        assert len(reg.list_all()) == 2

    def test_list_by_category(self):
        reg = ToolRegistry()
        reg.register("a", "d", {}, lambda: None, category="safe")
        reg.register("b", "d", {}, lambda: None, category="network")
        reg.register("c", "d", {}, lambda: None, category="safe")
        safe_tools = reg.list_by_category("safe")
        assert len(safe_tools) == 2
        assert all(t.category == "safe" for t in safe_tools)

    def test_describe_all_empty(self):
        reg = ToolRegistry()
        assert "无可用工具" in reg.describe_all()

    def test_describe_all(self):
        reg = ToolRegistry()
        reg.register("calc", "计算器", {"expr": {"type": "string"}}, lambda x: x)
        desc = reg.describe_all()
        assert "calc" in desc
        assert "计算器" in desc

    def test_describe_for_llm(self):
        reg = ToolRegistry()
        reg.register("calc", "计算", {"expr": {"type": "string"}}, lambda x: x, category="safe")
        tools = reg.describe_for_llm()
        assert len(tools) == 1
        assert tools[0]["name"] == "calc"

    def test_register_expert_as_tool(self):
        reg = ToolRegistry()
        t = reg.register_expert_as_tool("code_reviewer", lambda task: "reviewed", "审查代码")
        assert t.category == "agent"
        assert "expert" in t.tags
        assert "code_reviewer" in t.tags
        assert "task" in t.parameters

    def test_get_missing(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None
