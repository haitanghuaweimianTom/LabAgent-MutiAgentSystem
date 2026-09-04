"""Tests for the example hello-world plugin (P2).

Demonstrates the full plugin authoring flow:
  - listens to step/start, step/end
  - writes to a session log
  - registers a service for downstream plugins
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from labagent.plugin import (
    Context,
    EventBus,
    PluginManager,
    SessionLog,
    EventKind,
    load_plugin_instance,
)


def test_hello_plugin_logs_lifecycle(tmp_path):
    """The hello plugin should write step events into the session log."""
    from labagent_hello_plugin.plugin import HelloPlugin

    log = SessionLog(session_id="demo", root=tmp_path)
    ctx = Context()
    ctx.register("session_log", log)
    ctx.register("greet", lambda name: f"hello, {name}")  # dep

    plugin = HelloPlugin()
    plugin.setup(ctx)

    # Emit a step start; the plugin should log it
    ctx.emit("step/start", {"step": "research", "name": "lit_review"})

    events = log.read_all()
    assert any(e.kind == EventKind.STEP_START for e in events)
    assert any(e.payload.get("step") == "research" for e in events)


def test_hello_plugin_inject_missing_raises(tmp_path):
    from labagent_hello_plugin.plugin import HelloPlugin

    ctx = Context()
    # missing session_log inject should fail
    plugin = HelloPlugin()
    with pytest.raises(KeyError):
        plugin.setup(ctx)
