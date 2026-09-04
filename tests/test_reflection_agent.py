"""Tests for reflection_agent.py - LLM reflection + rule gate."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from reflection_agent import (
    ReflectionAgent,
    ReflectionIssue,
    ReflexReport,
    RuleGate,
    rule_extract_fallback,
    VAGUE_KEYWORDS,
)


def make_llm(content: str):
    async def _llm(system_prompt, user_prompt, **kwargs):
        return {"content": content}
    return _llm


class TestReflectionIssue:
    def test_creation(self):
        issue = ReflectionIssue(
            category="experiment",
            description="VRPTW solver times out above 50 nodes",
            root_cause="brute-force enumeration",
            suggestion="use ortools with time_limit=60",
            affected_stages=["step2", "step3"],
            specificity=4,
            testability=5,
        )
        assert issue.category == "experiment"
        assert issue.testability == 5
        assert issue.to_dict()["root_cause"] == "brute-force enumeration"

    def test_from_dict_defaults(self):
        issue = ReflectionIssue.from_dict({"description": "no category"})
        assert issue.category == "pipeline"
        assert issue.specificity == 0
        assert issue.affected_stages == []


class TestRuleGate:
    def test_rejects_vague(self):
        gate = RuleGate()
        issue = ReflectionIssue(
            category="writing",
            description="需注意写作质量",
            suggestion="要更仔细一些",
            specificity=1,
            testability=1,
        )
        assert gate.filter([issue]) == []

    def test_rejects_too_short(self):
        gate = RuleGate()
        issue = ReflectionIssue(
            category="experiment",
            description="太短",
            suggestion="太短",
            specificity=5,
            testability=5,
        )
        assert gate.filter([issue]) == []

    def test_accepts_specific(self):
        gate = RuleGate()
        issue = ReflectionIssue(
            category="experiment",
            description="VRPTW 使用暴力枚举在 50 节点以上严重超时",
            suggestion="改用 ortools.constraint_solver 并设置 time_limit=60 秒",
            affected_stages=["step3"],
            specificity=5,
            testability=5,
        )
        result = gate.filter([issue])
        assert len(result) == 1

    def test_top5_limit(self):
        gate = RuleGate(max_lessons=2)
        issues = [
            ReflectionIssue(
                category="experiment",
                description=f"Specific issue number {i} with enough length here",
                suggestion=f"Actionable fix for issue number {i}",
                specificity=5,
                testability=5,
            )
            for i in range(6)
        ]
        assert len(gate.filter(issues)) == 2

    def test_vague_keywords_defined(self):
        assert "更仔细" in VAGUE_KEYWORDS
        assert "be careful" in VAGUE_KEYWORDS


class TestReflectionAgent:
    @pytest.mark.asyncio
    async def test_reflect_parses_json(self):
        valid_json = {
            "issues": [{
                "category": "experiment",
                "description": "VRPTW 使用暴力枚举在 50 节点以上超时",
                "root_cause": "未用时间窗约束",
                "suggestion": "改用 ortools 并限制 time_limit",
                "affected_stages": ["step2", "step3"],
                "specificity": 5,
                "testability": 5,
            }],
            "success_patterns": ["matplotlib Agg 后端避免乱码"],
            "quality_trajectory": {"direction": "up", "notes": "3.1 -> 3.8"},
        }
        agent = ReflectionAgent(llm_fn=make_llm(
            f"```json\n{json.dumps(valid_json, ensure_ascii=False)}\n```"
        ))
        report = await agent.reflect({}, run_id="run1")
        assert isinstance(report, ReflexReport)
        assert len(report.issues) == 1
        assert report.issues[0].category == "experiment"
        assert report.success_patterns == ["matplotlib Agg 后端避免乱码"]

    @pytest.mark.asyncio
    async def test_reflect_applies_rule_gate(self):
        # LLM returns mixture of specific + vague issues
        payload = {
            "issues": [
                {
                    "category": "experiment",
                    "description": "really specific and long problem description here",
                    "suggestion": "a concrete actionable fix for the above",
                    "specificity": 5,
                    "testability": 5,
                },
                {
                    "category": "experiment",
                    "description": "注意提高质量",
                    "suggestion": "要更小心",
                    "specificity": 1,
                    "testability": 1,
                },
            ],
            "success_patterns": [],
        }
        agent = ReflectionAgent(llm_fn=make_llm(json.dumps(payload, ensure_ascii=False)))
        report = await agent.reflect({}, run_id="run1")
        assert len(report.issues) == 1

    @pytest.mark.asyncio
    async def test_reflect_fallback_on_llm_failure(self):
        async def _fail(system_prompt, user_prompt, **kwargs):
            raise RuntimeError("API down")
        agent = ReflectionAgent(llm_fn=_fail)
        report = await agent.reflect(
            {"step1": {"status": "failed", "error": "ImportError: No module named numpy", "score": None}},
            run_id="run1",
        )
        # fallback produces rule-extracted lessons, source="rule"
        assert report.fallback_used is True
        assert all(i.source == "rule" for i in report.issues)
        assert any("numpy" in i.description for i in report.issues)

    @pytest.mark.asyncio
    async def test_reflect_without_llm_and_no_errors(self):
        agent = ReflectionAgent(llm_fn=None)
        report = await agent.reflect(
            {"step1": {"status": "completed", "error": "", "score": 0.9}},
            run_id="run1",
        )
        assert report.issues == []


class TestRuleFragment:
    def test_rule_extract_fallback_produces_issues(self):
        issues = rule_extract_fallback(
            {"step1": {"status": "failed", "error": "RuntimeError: traceback", "score": 0.2}}
        )
        assert isinstance(issues, list)
        assert len(issues) >= 1