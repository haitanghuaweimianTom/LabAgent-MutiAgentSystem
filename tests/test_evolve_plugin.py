"""Tests for labagent_evolve plugin (wraps self_evolution + reflection_agent)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
# Original modules live in scripts/ which isn't on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from labagent.plugin import Context, SessionLog, EventKind


def test_evolve_plugin_requires_dependencies():
    from labagent_evolve.plugin import EvolutionPlugin

    ctx = Context()
    plugin = EvolutionPlugin()
    with pytest.raises(KeyError):
        plugin.setup(ctx)


def test_evolve_plugin_registers_services(tmp_path):
    from labagent_evolve.plugin import EvolutionPlugin

    log = SessionLog(session_id="t", root=tmp_path)
    ctx = Context()
    ctx.register("session_log", log)
    # Pretend LLM callable is available
    ctx.register("llm_call", lambda *a, **kw: {"content": "{}"})

    plugin = EvolutionPlugin()
    plugin.setup(ctx)

    # Plugin should have registered an evolution_store service
    assert ctx.get("evolution_store") is not None
    # And a reflection_agent
    assert ctx.get("reflection_agent") is not None
