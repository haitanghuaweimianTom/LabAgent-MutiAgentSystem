"""
HITL (Human-in-the-Loop) Module - 6 Intervention Modes

Inspired by AutoResearchClaw's Co-Pilot mode with 6 intervention types.
Provides structured human intervention at critical decision points.

Intervention Modes:
1. DIRECTION: Choose research direction from options
2. DESIGN: Review and approve experiment design
3. DECISION: PIVOT/REFINE/CONTINUE after results
4. REVIEW: Review paper quality and suggest changes
5. APPROVAL: Approve final output before delivery
6. EMERGENCY: Handle critical errors requiring human input
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "InterventionMode",
    "InterventionRequest",
    "InterventionResponse",
    "HITLManager",
]


class InterventionMode(str, Enum):
    """6 intervention modes for human-in-the-loop."""

    DIRECTION = "direction"      # Choose research direction
    DESIGN = "design"            # Review experiment design
    DECISION = "decision"        # PIVOT/REFINE/CONTINUE
    REVIEW = "review"            # Review paper quality
    APPROVAL = "approval"        # Approve final output
    EMERGENCY = "emergency"      # Handle critical errors


@dataclass
class InterventionRequest:
    """Request for human intervention."""

    mode: InterventionMode
    stage: str
    question: str
    options: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "stage": self.stage,
            "question": self.question,
            "options": self.options,
            "context": self.context,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterventionRequest:
        return cls(
            mode=InterventionMode(data.get("mode", "direction")),
            stage=data.get("stage", "unknown"),
            question=data.get("question", ""),
            options=data.get("options", []),
            context=data.get("context", {}),
            timestamp=data.get("timestamp", 0.0),
            request_id=data.get("request_id", ""),
        )


@dataclass
class InterventionResponse:
    """Response from human intervention."""

    request_id: str
    selected_option: str
    custom_input: str = ""
    feedback: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "selected_option": self.selected_option,
            "custom_input": self.custom_input,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterventionResponse:
        return cls(
            request_id=data.get("request_id", ""),
            selected_option=data.get("selected_option", ""),
            custom_input=data.get("custom_input", ""),
            feedback=data.get("feedback", ""),
            timestamp=data.get("timestamp", 0.0),
        )


class HITLManager:
    """Human-in-the-Loop manager for structured intervention.

    Supports both interactive and file-based intervention modes.
    For autonomous mode, uses auto-response rules.
    """

    def __init__(
        self,
        workspace_dir: Path | str,
        *,
        auto_mode: bool = False,
        timeout_seconds: int = 300,
    ) -> None:
        self._dir = Path(workspace_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._requests_path = self._dir / "intervention_requests.jsonl"
        self._responses_path = self._dir / "intervention_responses.jsonl"
        self._auto_mode = auto_mode
        self._timeout = timeout_seconds
        self._pending: dict[str, InterventionRequest] = {}

    def request_intervention(
        self,
        mode: InterventionMode,
        stage: str,
        question: str,
        options: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> InterventionResponse:
        """Request human intervention and wait for response.

        In auto_mode, returns a default response based on mode.
        """
        import uuid

        request = InterventionRequest(
            mode=mode,
            stage=stage,
            question=question,
            options=options or [],
            context=context or {},
            request_id=str(uuid.uuid4())[:8],
        )

        # Save request
        with self._requests_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(request.to_dict(), ensure_ascii=False) + "\n")

        self._pending[request.request_id] = request

        # Auto mode: return default response
        if self._auto_mode:
            response = self._auto_response(request)
            self._save_response(response)
            return response

        # Interactive mode: print and wait for input
        return self._interactive_prompt(request)

    def _auto_response(self, request: InterventionRequest) -> InterventionResponse:
        """Generate automatic response based on intervention mode."""
        auto_rules = {
            InterventionMode.DIRECTION: "continue_with_default",
            InterventionMode.DESIGN: "approve",
            InterventionMode.DECISION: "continue",
            InterventionMode.REVIEW: "approve",
            InterventionMode.APPROVAL: "approve",
            InterventionMode.EMERGENCY: "retry_with_defaults",
        }

        selected = auto_rules.get(request.mode, "continue")
        return InterventionResponse(
            request_id=request.request_id,
            selected_option=selected,
            feedback="[AUTO] Auto-mode response",
        )

    def _interactive_prompt(self, request: InterventionRequest) -> InterventionResponse:
        """Interactive terminal prompt for human intervention."""
        print("\n" + "=" * 60)
        print(f"🔴 HUMAN INTERVENTION REQUIRED [{request.mode.value.upper()}]")
        print(f"Stage: {request.stage}")
        print(f"Question: {request.question}")
        print("=" * 60)

        if request.options:
            print("\nOptions:")
            for i, opt in enumerate(request.options, 1):
                print(f"  {i}. {opt}")
            print(f"  c. Custom input")

        print("\n" + "-" * 60)

        try:
            choice = input("Your choice: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "c"

        if choice.lower() == "c":
            try:
                custom = input("Custom input: ").strip()
            except (EOFError, KeyboardInterrupt):
                custom = ""
            response = InterventionResponse(
                request_id=request.request_id,
                selected_option="custom",
                custom_input=custom,
            )
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(request.options):
                    selected = request.options[idx]
                else:
                    selected = request.options[0] if request.options else "continue"
            except (ValueError, IndexError):
                selected = request.options[0] if request.options else "continue"
            response = InterventionResponse(
                request_id=request.request_id,
                selected_option=selected,
            )

        self._save_response(response)
        return response

    def _save_response(self, response: InterventionResponse) -> None:
        """Save response to disk."""
        with self._responses_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(response.to_dict(), ensure_ascii=False) + "\n")
        self._pending.pop(response.request_id, None)

    def get_response(self, request_id: str) -> InterventionResponse | None:
        """Get response for a specific request."""
        if not self._responses_path.exists():
            return None
        for line in self._responses_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                resp = InterventionResponse.from_dict(data)
                if resp.request_id == request_id:
                    return resp
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def get_pending(self) -> list[InterventionRequest]:
        """Get all pending intervention requests."""
        return list(self._pending.values())

    def get_history(self) -> list[tuple[InterventionRequest, InterventionResponse | None]]:
        """Get all past interventions with their responses."""
        requests = self._load_requests()
        responses = self._load_responses()
        response_map = {r.request_id: r for r in responses}

        history = []
        for req in requests:
            resp = response_map.get(req.request_id)
            history.append((req, resp))
        return history

    def _load_requests(self) -> list[InterventionRequest]:
        """Load all requests from disk."""
        if not self._requests_path.exists():
            return []
        requests = []
        for line in self._requests_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                requests.append(InterventionRequest.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                continue
        return requests

    def _load_responses(self) -> list[InterventionResponse]:
        """Load all responses from disk."""
        if not self._responses_path.exists():
            return []
        responses = []
        for line in self._responses_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                responses.append(InterventionResponse.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                continue
        return responses

    def request_direction_choice(
        self,
        stage: str,
        directions: list[str],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Convenience: Request research direction choice."""
        response = self.request_intervention(
            mode=InterventionMode.DIRECTION,
            stage=stage,
            question="Choose research direction:",
            options=directions,
            context=context,
        )
        return response.selected_option

    def request_design_approval(
        self,
        stage: str,
        design: dict[str, Any],
    ) -> bool:
        """Convenience: Request experiment design approval."""
        response = self.request_intervention(
            mode=InterventionMode.DESIGN,
            stage=stage,
            question="Review experiment design. Approve?",
            options=["approve", "reject", "modify"],
            context=design,
        )
        return response.selected_option == "approve"

    def request_pivot_decision(
        self,
        stage: str,
        results: dict[str, Any],
    ) -> str:
        """Convenience: Request PIVOT/REFINE/CONTINUE decision."""
        response = self.request_intervention(
            mode=InterventionMode.DECISION,
            stage=stage,
            question="Results analysis. What should we do next?",
            options=["continue", "refine", "pivot"],
            context=results,
        )
        return response.selected_option

    def request_paper_review(
        self,
        stage: str,
        paper_summary: str,
    ) -> tuple[bool, str]:
        """Convenience: Request paper review. Returns (approved, feedback)."""
        response = self.request_intervention(
            mode=InterventionMode.REVIEW,
            stage=stage,
            question="Review paper. Approve?",
            options=["approve", "needs_revision", "reject"],
            context={"summary": paper_summary},
        )
        approved = response.selected_option == "approve"
        return approved, response.feedback or response.custom_input

    def request_final_approval(
        self,
        stage: str,
        deliverables: list[str],
    ) -> bool:
        """Convenience: Request final output approval."""
        response = self.request_intervention(
            mode=InterventionMode.APPROVAL,
            stage=stage,
            question="Final deliverables ready. Approve?",
            options=["approve", "reject"],
            context={"deliverables": deliverables},
        )
        return response.selected_option == "approve"

    def request_emergency_help(
        self,
        stage: str,
        error: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Convenience: Request emergency help for critical errors."""
        response = self.request_intervention(
            mode=InterventionMode.EMERGENCY,
            stage=stage,
            question=f"Critical error: {error}. How should we proceed?",
            options=["retry_with_defaults", "skip_stage", "abort_pipeline", "manual_fix"],
            context=context or {"error": error},
        )
        return response.selected_option
