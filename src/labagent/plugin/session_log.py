"""Session log - append-only event log with v1 versioning.

DSH 不变式 "Model-visible means logged": anything that reaches a model
request must be reconstructable from the log.

File format: `sessions/{session_id}/session.v1.jsonl` (lowercase, version-prefixed
per DSH convention). v1 reserved; migrations to v2 only add a new file with
an adjacent migration package, never rename the source.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union


class EventKind(str, Enum):
    """Canonical session event kinds. Wire format uses slash-names.

    Covers the minimum needed for 7-step paper generation + self-evolution v2.
    """

    # Session lifecycle
    SESSION_START = "session/start"
    SESSION_END = "session/end"
    TURN_START = "turn/start"
    TURN_END = "turn/end"

    # Step lifecycle (7-step pipeline)
    STEP_START = "step/start"
    STEP_END = "step/end"

    # LLM/model-facing content
    USER_MESSAGE = "user/message"
    ASSISTANT_MESSAGE = "assistant/message"
    ASSISTANT_ATTEMPT = "assistant/attempt"

    # Tool activity
    TOOL_CALL = "tool/call"
    TOOL_RESULT = "tool/result"

    # Quality / self-evolution
    QUALITY_DECISION = "quality/decision"
    EVOLUTION_LESSON = "evolution/lesson"
    SELF_CHECK = "self/check"


CURRENT_VERSION = 1  # session.v1.jsonl


@dataclass
class SessionEvent:
    """A single durable event in the session log."""

    kind: EventKind
    session_id: str
    payload: dict[str, Any]
    seq: int = 0
    timestamp: float = field(default_factory=time.time)
    run_id: str = ""

    def to_jsonl(self) -> str:
        return json.dumps(
            {
                "kind": self.kind.value,
                "session_id": self.session_id,
                "seq": self.seq,
                "timestamp": self.timestamp,
                "run_id": self.run_id,
                "payload": self.payload,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_jsonl(cls, line: str) -> "SessionEvent":
        data = json.loads(line)
        return cls(
            kind=EventKind(data["kind"]),
            session_id=data["session_id"],
            payload=data.get("payload", {}),
            seq=int(data.get("seq", 0)),
            timestamp=float(data.get("timestamp", 0.0)),
            run_id=data.get("run_id", ""),
        )

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "session_id": self.session_id,
            "seq": self.seq,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionEvent":
        return cls(
            kind=EventKind(data["kind"]),
            session_id=data["session_id"],
            payload=data.get("payload", {}),
            seq=int(data.get("seq", 0)),
            timestamp=float(data.get("timestamp", 0.0)),
            run_id=data.get("run_id", ""),
        )


class SessionLog:
    """Append-only JSONL event log keyed by session id.

    On-disk layout:
        <root>/<session_id>/session.v1.jsonl

    All appends go through `_append` which auto-assigns the next seq number
    by reading the current file size. Concurrent appends to the same session
    are NOT safe (single-writer per session).
    """

    def __init__(self, session_id: str, root: Path | str) -> None:
        self.session_id = session_id
        self.root = Path(root)
        self._dir = self.root / session_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"session.v{CURRENT_VERSION}.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    @property
    def dir(self) -> Path:
        return self._dir

    def append(self, kind: EventKind, payload: dict[str, Any], *, run_id: str = "") -> SessionEvent:
        """Append an event with auto-incremented seq."""
        seq = self._next_seq()
        event = SessionEvent(
            kind=kind,
            session_id=self.session_id,
            payload=payload,
            seq=seq,
            run_id=run_id,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(event.to_jsonl() + "\n")
        return event

    def read_all(self) -> list[SessionEvent]:
        if not self._path.exists():
            return []
        events: list[SessionEvent] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(SessionEvent.from_jsonl(line))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return events

    def _next_seq(self) -> int:
        """Return the next seq number by counting existing lines."""
        if not self._path.exists():
            return 0
        count = 0
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                count += 1
        return count


def derive_session_id(template_id: str, problem: str, ts: Optional[float] = None) -> str:
    """Deterministic session id from (template, problem, timestamp)."""
    if ts is None:
        ts = time.time()
    raw = f"{template_id}::{problem}::{ts}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    safe_tpl = "".join(c if c.isalnum() else "_" for c in template_id)[:16]
    return f"{safe_tpl}-{h}"
