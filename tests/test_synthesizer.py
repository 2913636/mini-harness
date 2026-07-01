"""P0-3: ResultSynthesizer 核心路径测试"""
import pytest
from harness import ResultSynthesizer, SourceBlock


class TestResultSynthesizer:
    """ResultSynthesizer 核心路径测试"""

    def test_synthesize_empty_results(self):
        synth = ResultSynthesizer()
        report = synth.synthesize("task", [])
        assert "无专家结果" in report

    def test_synthesize_single_result(self):
        synth = ResultSynthesizer()
        report = synth.synthesize(
            "analyze code",
            [{"expert": "code_reviewer", "subtask": "review", "result": "Code looks good"}],
        )
        assert "code_reviewer" in report
        assert "Code looks good" in report
        assert "[来源]" in report or "来源" in report

    def test_synthesize_multiple_results_with_source_annotation(self):
        synth = ResultSynthesizer()
        report = synth.synthesize(
            "security audit",
            [
                {"expert": "code_reviewer", "subtask": "code review", "result": "Code quality: OK"},
                {"expert": "security_expert", "subtask": "security scan", "result": "Found 2 issues"},
            ],
        )
        assert "code_reviewer" in report
        assert "security_expert" in report
        assert "Code quality" in report
        assert "Found 2 issues" in report

    def test_prioritize_security_over_other(self):
        synth = ResultSynthesizer()
        sources = [
            SourceBlock(content="Code is readable", source_expert="code_reviewer"),
            SourceBlock(content="SQL injection found", source_expert="security_expert"),
        ]
        ordered = synth._prioritize(sources, ["security"])
        # Security-related should come first
        assert ordered[0].source_expert == "security_expert"

    def test_prioritize_no_priorities_keeps_order(self):
        synth = ResultSynthesizer()
        sources = [
            SourceBlock(content="AAA", source_expert="expert1"),
            SourceBlock(content="BBB", source_expert="expert2"),
        ]
        ordered = synth._prioritize(sources, [])
        assert ordered == sources  # no reordering

    def test_deduplicate_similar_content(self):
        synth = ResultSynthesizer()
        sources = [
            SourceBlock(
                content="SQL injection vulnerability found in login form needs immediate fix",
                source_expert="security_expert",
            ),
            SourceBlock(
                content="SQL injection vulnerability found in login form needs urgent fix",
                source_expert="code_reviewer",
            ),
        ]
        deduped = synth._deduplicate(sources)
        assert len(deduped) == 1
        # Merged source names
        assert "security_expert" in deduped[0].source_expert
        assert "code_reviewer" in deduped[0].source_expert

    def test_deduplicate_unique_content_kept_separate(self):
        synth = ResultSynthesizer()
        sources = [
            SourceBlock(content="Code quality is excellent", source_expert="code_reviewer"),
            SourceBlock(content="No security vulnerabilities found", source_expert="security_expert"),
        ]
        deduped = synth._deduplicate(sources)
        assert len(deduped) == 2  # different content, both kept

    def test_rule_synthesize_format(self):
        synth = ResultSynthesizer()
        sources = [
            SourceBlock(content="Result A", source_expert="A", subtask="Task A"),
            SourceBlock(content="Result B", source_expert="B", subtask="Task B"),
        ]
        report = synth._rule_synthesize("test task", sources, ["security"])
        assert "最终报告" in report
        assert "Task A" in report
        assert "Task B" in report
        assert "来源" in report
        assert "security" in report  # priority mentioned
