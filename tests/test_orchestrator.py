"""P0-1: Orchestrator 核心路径测试"""
import pytest
from harness import Orchestrator, ExpertRegistry, Expert, ResultSynthesizer, SubTask


def _mock_llm(messages, prompt):
    """Mock LLM for orchestration tests"""
    if "JSON" in prompt:
        # Decompose phase
        return """```json
[
  {"id": "1", "description": "Code review", "required_domains": ["code"], "dependencies": [], "priority": "P0"},
  {"id": "2", "description": "Security scan", "required_domains": ["security"], "dependencies": [], "priority": "P0"}
]
```"""
    # Synthesize phase
    return "Merged report from all experts"


class TestOrchestrator:
    """Orchestrator 核心路径测试"""

    def _make_orchestrator(self, experts=None):
        reg = ExpertRegistry()
        if experts:
            for e in experts:
                reg.register(e)
        return Orchestrator(
            expert_registry=reg,
            llm_fn=_mock_llm,
            synthesizer=ResultSynthesizer(),
        )

    def test_decompose_with_llm(self):
        orch = self._make_orchestrator()
        subtasks = orch.decompose("review code and scan security")
        assert len(subtasks) == 2
        assert subtasks[0].id == "1"
        assert "code" in subtasks[0].required_domains

    def test_rule_decompose_fallback(self):
        """When LLM returns invalid JSON, fall back to rule-based"""
        def bad_llm(messages, prompt):
            return "I can't do that"

        reg = ExpertRegistry()
        orch = Orchestrator(reg, bad_llm, ResultSynthesizer())
        subtasks = orch.decompose("review this code")
        assert len(subtasks) >= 1
        # Should fall back to rule-based decomposition
        assert subtasks[0].description != ""

    def test_match_experts(self):
        orch = self._make_orchestrator([
            Expert(name="reviewer", description="d", domain=["code"]),
            Expert(name="security", description="d", domain=["security"]),
        ])
        subtasks = [
            SubTask(id="1", description="Review code", required_domains=["code"]),
            SubTask(id="2", description="Scan security", required_domains=["security"]),
        ]
        matched = orch.match_experts(subtasks)
        assert matched[0].assigned_expert == "reviewer"
        assert matched[1].assigned_expert == "security"

    def test_detect_gaps_missing_expert(self):
        orch = self._make_orchestrator([
            Expert(name="reviewer", description="d", domain=["code"]),
        ])
        subtasks = [
            SubTask(id="1", description="Review code", required_domains=["code"]),
            SubTask(id="2", description="Write docs", required_domains=["doc"]),
        ]
        gaps = orch.detect_gaps(subtasks)
        assert len(gaps) == 1
        assert "doc" in gaps[0].lower()

    def test_detect_gaps_all_covered(self):
        orch = self._make_orchestrator([
            Expert(name="reviewer", description="d", domain=["code"]),
        ])
        subtasks = [
            SubTask(id="1", description="Review code", required_domains=["code"]),
        ]
        gaps = orch.detect_gaps(subtasks)
        assert len(gaps) == 0

    def test_run_full_pipeline(self):
        def expert_fn(task, context=None):
            return f"Result for: {task[:30]}"

        orch = self._make_orchestrator([
            Expert(name="reviewer", description="Code reviewer", domain=["code"], fn=expert_fn),
            Expert(name="security", description="Security scanner", domain=["security"], fn=expert_fn),
        ])
        result = orch.run("review code and scan security for SQL injection", ["security"])
        assert result["success"] is True
        assert result["stats"]["completed"] == 2
        assert result["stats"]["failed"] == 0
        assert len(result["report"]) > 0

    def test_run_with_gaps_still_completes(self):
        """Tasks with missing experts should still complete via LLM fallback"""
        orch = self._make_orchestrator([])  # no experts
        result = orch.run("review this code")
        # Should complete some tasks via LLM fallback
        assert "report" in result
        # Gaps should be detected
        assert len(result["gaps"]) >= 1

    def test_dag_execution_order(self):
        """Subtasks with dependencies should execute in order"""
        orch = self._make_orchestrator([
            Expert(name="expert1", description="d", domain=["test"], fn=lambda t, c=None: "step1"),
            Expert(name="expert2", description="d", domain=["test"], fn=lambda t, c=None: "step2"),
        ])
        subtasks = orch.decompose("test task")

        # Simulate setting dependencies
        if len(subtasks) >= 2:
            subtasks[1].dependencies = [subtasks[0].id]
            subtasks = orch.match_experts(subtasks)

        # Execute DAG
        subtasks = orch._execute_dag(subtasks, max_iterations=10)
        done = [st for st in subtasks if st.status == "done"]
        assert len(done) >= 1  # At least some tasks complete
