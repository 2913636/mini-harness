"""P0-2: ExpertRegistry 核心路径测试"""
import pytest
from harness import ExpertRegistry, Expert


class TestExpert:
    """Expert 数据类测试"""

    def test_create_valid_expert(self):
        e = Expert(
            name="test_expert",
            description="A test expert",
            domain=["test"],
            capabilities=["testing"],
        )
        assert e.name == "test_expert"
        assert e.domain == ["test"]

    def test_describe_output(self):
        e = Expert(
            name="code_reviewer",
            description="Review code quality",
            domain=["code", "quality"],
            capabilities=["code review", "bug detection"],
        )
        desc = e.describe()
        assert "code_reviewer" in desc
        assert "code" in desc
        assert "bug detection" in desc

    def test_to_dict(self):
        e = Expert(
            name="x",
            description="desc",
            domain=["a"],
            capabilities=["b"],
            metadata={"key": "val"},
        )
        d = e.to_dict()
        assert d["name"] == "x"
        assert d["domain"] == ["a"]
        assert d["metadata"]["key"] == "val"


class TestExpertRegistry:
    """ExpertRegistry 核心路径测试"""

    def test_register_and_get(self):
        reg = ExpertRegistry()
        e = Expert(name="e1", description="desc", domain=["code"])
        reg.register(e)
        assert reg.get("e1") is e
        assert len(reg) == 1
        assert "e1" in reg

    def test_register_empty_name_raises(self):
        reg = ExpertRegistry()
        with pytest.raises(ValueError, match="name cannot be empty"):
            reg.register(Expert(name="", description="desc"))

    def test_register_no_description_raises(self):
        reg = ExpertRegistry()
        with pytest.raises(ValueError, match="requires a description"):
            reg.register(Expert(name="x", description=""))

    def test_unregister(self):
        reg = ExpertRegistry()
        reg.register(Expert(name="e1", description="desc"))
        assert reg.unregister("e1") is True
        assert reg.unregister("e1") is False
        assert len(reg) == 0

    def test_find_by_domain(self):
        reg = ExpertRegistry()
        reg.register(Expert(name="code", description="d", domain=["code", "quality"]))
        reg.register(Expert(name="security", description="d", domain=["security"]))
        reg.register(Expert(name="tester", description="d", domain=["testing", "code"]))
        code_experts = reg.find_by_domain("code")
        assert len(code_experts) == 2

    def test_match_by_domain_keywords(self):
        reg = ExpertRegistry()
        reg.register(Expert(name="code", description="d", domain=["code", "quality"]))
        reg.register(Expert(name="security", description="d", domain=["security"]))
        matches = reg.match("review this code for bugs")
        assert len(matches) > 0
        assert matches[0][0].name == "code"  # code domain matches

    def test_match_by_capability_keywords(self):
        reg = ExpertRegistry()
        reg.register(Expert(
            name="security",
            description="d",
            domain=["security"],
            capabilities=["SQL injection"],
        ))
        matches = reg.match("check for SQL injection vulnerabilities")
        assert len(matches) > 0
        assert matches[0][0].name == "security"

    def test_match_empty_registry(self):
        reg = ExpertRegistry()
        matches = reg.match("some task")
        assert matches == []

    def test_describe_all(self):
        reg = ExpertRegistry()
        reg.register(Expert(name="e1", description="First expert", domain=["code"]))
        reg.register(Expert(name="e2", description="Second expert", domain=["security"]))
        desc = reg.describe_all()
        assert "e1" in desc
        assert "e2" in desc
        assert "code" in desc

    def test_register_overwrite(self):
        reg = ExpertRegistry()
        e1 = Expert(name="e1", description="first", domain=["code"])
        e2 = Expert(name="e1", description="second", domain=["security"])
        reg.register(e1)
        reg.register(e2)
        assert reg.get("e1").description == "second"
        assert len(reg) == 1
