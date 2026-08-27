"""Tests for HITL Manager Module."""
import json
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from hitl_manager import (
    InterventionMode,
    InterventionRequest,
    InterventionResponse,
    HITLManager,
)


class TestInterventionMode:
    def test_modes(self):
        assert InterventionMode.DIRECTION == "direction"
        assert InterventionMode.DESIGN == "design"
        assert InterventionMode.DECISION == "decision"
        assert InterventionMode.REVIEW == "review"
        assert InterventionMode.APPROVAL == "approval"
        assert InterventionMode.EMERGENCY == "emergency"

    def test_six_modes(self):
        assert len(InterventionMode) == 6


class TestInterventionRequest:
    def test_creation(self):
        req = InterventionRequest(
            mode=InterventionMode.DIRECTION,
            stage="step1",
            question="Choose direction",
            options=["option1", "option2"],
        )
        assert req.mode == InterventionMode.DIRECTION
        assert req.stage == "step1"
        assert req.options == ["option1", "option2"]

    def test_to_dict(self):
        req = InterventionRequest(
            mode=InterventionMode.DESIGN,
            stage="step2",
            question="Review design",
        )
        d = req.to_dict()
        assert d["mode"] == "design"
        assert d["stage"] == "step2"

    def test_from_dict(self):
        data = {
            "mode": "decision",
            "stage": "step3",
            "question": "What next?",
            "options": ["continue", "pivot"],
            "context": {},
            "timestamp": 1234567890.0,
            "request_id": "req-001",
        }
        req = InterventionRequest.from_dict(data)
        assert req.mode == InterventionMode.DECISION
        assert req.request_id == "req-001"


class TestInterventionResponse:
    def test_creation(self):
        resp = InterventionResponse(
            request_id="req-001",
            selected_option="approve",
            feedback="Looks good",
        )
        assert resp.request_id == "req-001"
        assert resp.selected_option == "approve"
        assert resp.feedback == "Looks good"

    def test_to_dict(self):
        resp = InterventionResponse(
            request_id="req-001",
            selected_option="reject",
            custom_input="Needs work",
        )
        d = resp.to_dict()
        assert d["request_id"] == "req-001"
        assert d["selected_option"] == "reject"
        assert d["custom_input"] == "Needs work"


class TestHITLManager:
    def test_auto_mode_direction(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        response = manager.request_intervention(
            mode=InterventionMode.DIRECTION,
            stage="step1",
            question="Choose direction",
            options=["option1", "option2"],
        )
        assert response.selected_option == "continue_with_default"

    def test_auto_mode_design(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        response = manager.request_intervention(
            mode=InterventionMode.DESIGN,
            stage="step1",
            question="Approve design?",
        )
        assert response.selected_option == "approve"

    def test_auto_mode_decision(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        response = manager.request_intervention(
            mode=InterventionMode.DECISION,
            stage="step1",
            question="What next?",
        )
        assert response.selected_option == "continue"

    def test_auto_mode_review(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        response = manager.request_intervention(
            mode=InterventionMode.REVIEW,
            stage="step1",
            question="Review paper?",
        )
        assert response.selected_option == "approve"

    def test_auto_mode_approval(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        response = manager.request_intervention(
            mode=InterventionMode.APPROVAL,
            stage="step1",
            question="Final approve?",
        )
        assert response.selected_option == "approve"

    def test_auto_mode_emergency(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        response = manager.request_intervention(
            mode=InterventionMode.EMERGENCY,
            stage="step1",
            question="Critical error!",
        )
        assert response.selected_option == "retry_with_defaults"

    def test_request_saves_to_disk(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        manager.request_intervention(
            mode=InterventionMode.DIRECTION,
            stage="step1",
            question="Test",
        )
        requests_path = tmp_path / "hitl" / "intervention_requests.jsonl"
        assert requests_path.exists()
        lines = requests_path.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_response_saves_to_disk(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        manager.request_intervention(
            mode=InterventionMode.DIRECTION,
            stage="step1",
            question="Test",
        )
        responses_path = tmp_path / "hitl" / "intervention_responses.jsonl"
        assert responses_path.exists()
        lines = responses_path.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_get_response(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        response = manager.request_intervention(
            mode=InterventionMode.DIRECTION,
            stage="step1",
            question="Test",
        )
        fetched = manager.get_response(response.request_id)
        assert fetched is not None
        assert fetched.request_id == response.request_id

    def test_convenience_direction(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        result = manager.request_direction_choice(
            stage="step1",
            directions=["A", "B", "C"],
        )
        assert result == "continue_with_default"

    def test_convenience_design_approval(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        result = manager.request_design_approval(
            stage="step1",
            design={"method": "test"},
        )
        assert result is True

    def test_convenience_pivot_decision(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        result = manager.request_pivot_decision(
            stage="step1",
            results={"score": 0.5},
        )
        assert result == "continue"

    def test_convenience_paper_review(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        approved, feedback = manager.request_paper_review(
            stage="step1",
            paper_summary="Test paper",
        )
        assert approved is True

    def test_convenience_final_approval(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        result = manager.request_final_approval(
            stage="step1",
            deliverables=["paper.pdf"],
        )
        assert result is True

    def test_convenience_emergency_help(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        result = manager.request_emergency_help(
            stage="step1",
            error="API failed",
        )
        assert result == "retry_with_defaults"

    def test_get_history(self, tmp_path):
        manager = HITLManager(tmp_path / "hitl", auto_mode=True)
        manager.request_intervention(
            mode=InterventionMode.DIRECTION,
            stage="step1",
            question="Test",
        )
        history = manager.get_history()
        assert len(history) == 1
        assert history[0][0].stage == "step1"
        assert history[0][1] is not None
