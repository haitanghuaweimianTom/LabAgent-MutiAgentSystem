"""Tests for SessionLog (P2)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from labagent.plugin.session_log import (
    SessionLog,
    SessionEvent,
    EventKind,
    derive_session_id,
)


class TestSessionEvent:
    def test_basic(self):
        e = SessionEvent(
            kind=EventKind.TURN_START,
            session_id="sess-1",
            payload={"topic": "test"},
        )
        assert e.kind == EventKind.TURN_START
        assert e.session_id == "sess-1"
        assert e.timestamp > 0
        assert e.seq == 0  # auto-assigned

    def test_to_jsonl(self):
        e = SessionEvent(
            kind=EventKind.USER_MESSAGE,
            session_id="s1",
            payload={"text": "hello"},
        )
        line = e.to_jsonl()
        data = json.loads(line)
        assert data["kind"] == "user/message"
        assert data["session_id"] == "s1"
        assert data["payload"]["text"] == "hello"

    def test_seq_assigned_by_log(self, tmp_path):
        # seq is a log-level concept, assigned by SessionLog.append
        log = SessionLog(session_id="s1", root=tmp_path)
        e1 = log.append(EventKind.TURN_START, {})
        e2 = log.append(EventKind.TURN_END, {})
        assert e1.seq == 0
        assert e2.seq == e1.seq + 1


class TestSessionLog:
    def test_creates_directory(self, tmp_path):
        log = SessionLog(session_id="abc", root=tmp_path)
        log_path = log.path
        assert log_path.parent.exists()

    def test_append_writes_to_v1_file(self, tmp_path):
        log = SessionLog(session_id="abc", root=tmp_path)
        log.append(EventKind.TURN_START, {"foo": 1})
        log.append(EventKind.TURN_END, {"foo": 2})
        # DSH convention: session.v1.jsonl (lowercase, version-prefixed)
        log_path = tmp_path / "abc" / "session.v1.jsonl"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["kind"] == "turn/start"
        assert first["seq"] == 0
        second = json.loads(lines[1])
        assert second["seq"] == 1

    def test_read_all(self, tmp_path):
        log = SessionLog(session_id="abc", root=tmp_path)
        log.append(EventKind.TURN_START, {"foo": 1})
        log.append(EventKind.STEP_START, {"step": "research"})
        events = log.read_all()
        assert len(events) == 2
        assert events[0].kind == EventKind.TURN_START
        assert events[1].kind == EventKind.STEP_START

    def test_persists_across_instances(self, tmp_path):
        log1 = SessionLog(session_id="abc", root=tmp_path)
        log1.append(EventKind.TURN_START, {"foo": 1})
        log1.append(EventKind.TURN_END, {"foo": 2})
        # New instance, same session_id — should read existing events
        log2 = SessionLog(session_id="abc", root=tmp_path)
        log2.append(EventKind.TURN_START, {"foo": 3})
        events = log2.read_all()
        # 3 events total, last has higher seq
        assert len(events) == 3
        assert events[0].seq == 0
        assert events[1].seq == 1
        assert events[2].seq == 2

    def test_session_id_derivation(self):
        sid = derive_session_id("math_modeling", "Solve VRPTW", ts=1234567890.0)
        assert isinstance(sid, str) and len(sid) > 0
        # Determinism
        assert sid == derive_session_id("math_modeling", "Solve VRPTW", ts=1234567890.0)
        # Different problem gives different id
        assert sid != derive_session_id("math_modeling", "Different", ts=1234567890.0)
