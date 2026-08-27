"""Tests for Enhanced Debate Module."""
import asyncio
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from enhanced_debate import (
    DebatePersona,
    DebateRound,
    DebateResult,
    EnhancedDebate,
    DEFAULT_PERSONAS,
)


class TestDebatePersona:
    def test_creation(self):
        persona = DebatePersona(
            name="Test",
            system_prompt="You are a test persona",
            focus_areas=["test1", "test2"],
            weight=1.5,
        )
        assert persona.name == "Test"
        assert persona.focus_areas == ["test1", "test2"]
        assert persona.weight == 1.5

    def test_to_dict(self):
        persona = DebatePersona(
            name="Test",
            system_prompt="Test prompt",
            focus_areas=["test"],
        )
        d = persona.to_dict()
        assert d["name"] == "Test"
        assert d["focus_areas"] == ["test"]
        assert d["weight"] == 1.0  # default


class TestDebateRound:
    def test_creation(self):
        round_obj = DebateRound(round_num=1)
        assert round_obj.round_num == 1
        assert round_obj.responses == []

    def test_to_dict(self):
        round_obj = DebateRound(
            round_num=1,
            responses=[{"name": "Planner", "feedback": "Test"}],
            synthesis="Synthesis text",
        )
        d = round_obj.to_dict()
        assert d["round_num"] == 1
        assert len(d["responses"]) == 1
        assert d["synthesis"] == "Synthesis text"


class TestDebateResult:
    def test_creation(self):
        result = DebateResult(topic="Test topic")
        assert result.topic == "Test topic"
        assert result.rounds == []

    def test_to_dict(self):
        result = DebateResult(
            topic="Test",
            consensus_score=0.8,
            key_issues=["issue1"],
            recommendations=["rec1"],
        )
        d = result.to_dict()
        assert d["topic"] == "Test"
        assert d["consensus_score"] == 0.8
        assert d["key_issues"] == ["issue1"]
        assert d["recommendations"] == ["rec1"]


class TestDefaultPersonas:
    def test_six_personas(self):
        assert len(DEFAULT_PERSONAS) == 6

    def test_persona_names(self):
        names = [p.name for p in DEFAULT_PERSONAS]
        assert "Planner" in names
        assert "Experimenter" in names
        assert "Critic" in names
        assert "Skeptic" in names
        assert "Writer" in names
        assert "Editor" in names

    def test_persona_weights(self):
        weights = {p.name: p.weight for p in DEFAULT_PERSONAS}
        assert weights["Planner"] == 1.2
        assert weights["Critic"] == 1.3
        assert weights["Editor"] == 0.8


class TestEnhancedDebate:
    @pytest.fixture
    def mock_call_fn(self):
        async def mock_call(system, user, max_tokens=4000):
            return {"content": f"Mock response for {system[:50]}"}
        return mock_call

    @pytest.mark.asyncio
    async def test_debate_basic(self, mock_call_fn):
        debate = EnhancedDebate(call_fn=mock_call_fn, rounds=1)
        result = await debate.debate("Test topic", "Test context")
        assert result.topic == "Test topic"
        assert len(result.rounds) == 1
        assert result.rounds[0].round_num == 1

    @pytest.mark.asyncio
    async def test_debate_multiple_rounds(self, mock_call_fn):
        debate = EnhancedDebate(call_fn=mock_call_fn, rounds=3)
        result = await debate.debate("Test topic", "Test context")
        assert len(result.rounds) == 3
        assert result.rounds[2].round_num == 3

    @pytest.mark.asyncio
    async def test_debate_all_personas_respond(self, mock_call_fn):
        debate = EnhancedDebate(call_fn=mock_call_fn, rounds=1)
        result = await debate.debate("Test topic", "Test context")
        assert len(result.rounds[0].responses) == 6
        persona_names = [r["name"] for r in result.rounds[0].responses]
        assert "Planner" in persona_names
        assert "Skeptic" in persona_names

    @pytest.mark.asyncio
    async def test_debate_has_synthesis(self, mock_call_fn):
        debate = EnhancedDebate(call_fn=mock_call_fn, rounds=1)
        result = await debate.debate("Test topic", "Test context")
        assert result.final_synthesis != ""
        assert "Final Debate Synthesis" in result.final_synthesis

    @pytest.mark.asyncio
    async def test_debate_consensus_score(self, mock_call_fn):
        debate = EnhancedDebate(call_fn=mock_call_fn, rounds=1)
        result = await debate.debate("Test topic", "Test context")
        assert 0.0 <= result.consensus_score <= 1.0

    @pytest.mark.asyncio
    async def test_debate_with_custom_personas(self, mock_call_fn):
        custom = [
            DebatePersona(
                name="Custom",
                system_prompt="Custom prompt",
                focus_areas=["custom"],
            )
        ]
        debate = EnhancedDebate(call_fn=mock_call_fn, personas=custom, rounds=1)
        result = await debate.debate("Test", "Context")
        assert len(result.rounds[0].responses) == 1
        assert result.rounds[0].responses[0]["name"] == "Custom"

    @pytest.mark.asyncio
    async def test_debate_handles_error(self):
        async def failing_call(system, user, max_tokens=4000):
            raise RuntimeError("API error")

        debate = EnhancedDebate(call_fn=failing_call, rounds=1)
        result = await debate.debate("Test", "Context")
        assert len(result.rounds) == 1
        assert "评估失败" in result.rounds[0].responses[0]["feedback"]
