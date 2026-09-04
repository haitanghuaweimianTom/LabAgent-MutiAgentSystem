"""Tests for pipeline-profile plugin."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from labagent.plugin import Context


def test_pipeline_plugin_loads_step_list_from_profile(tmp_path):
    from labagent_pipeline_plugin.plugin import PipelinePlugin
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "name: research-only\n"
        "steps:\n"
        "  - research\n"
        "  - code\n"
    )
    p = PipelinePlugin(profile_path=profile_path)
    assert p.steps == ["research", "code"]


def test_pipeline_plugin_runs_only_listed_steps(tmp_path):
    """Plugin should emit step/start for each step in profile, no more."""
    from labagent_pipeline_plugin.plugin import PipelinePlugin
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "name: quick\n"
        "steps:\n"
        "  - research\n"
        "  - code\n"
    )
    ctx = Context()
    started = []
    ctx.on("step/start", lambda p: started.append(p.get("step")))
    # Inject a step-runner stub: each step just emits a result
    runners = {
        "research": lambda p, c: asyncio.sleep(0, result={"papers": []}),
        "code":     lambda p, c: asyncio.sleep(0, result={"exec_success": True}),
    }
    p = PipelinePlugin(profile_path=profile_path, step_runners=runners)
    p.setup(ctx)
    asyncio.run(p.run("test problem"))
    assert started == ["research", "code"]


def test_pipeline_plugin_emits_session_lifecycle(tmp_path):
    from labagent_pipeline_plugin.plugin import PipelinePlugin
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: empty\nsteps: []\n")
    ctx = Context()
    events = []
    ctx.on("session/start", lambda p: events.append("start"))
    ctx.on("session/end", lambda p: events.append("end"))
    p = PipelinePlugin(profile_path=profile_path)
    p.setup(ctx)
    asyncio.run(p.run("test"))
    assert events == ["start", "end"]


def test_pipeline_plugin_skips_unlisted_steps(tmp_path):
    """A step in the global pipeline not listed in profile is NOT emitted."""
    from labagent_pipeline_plugin.plugin import PipelinePlugin
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "name: tiny\n"
        "steps:\n"
        "  - research\n"  # only research
    )
    ctx = Context()
    started = []
    ctx.on("step/start", lambda p: started.append(p.get("step")))
    p = PipelinePlugin(profile_path=profile_path)
    p.setup(ctx)
    asyncio.run(p.run("test"))
    # debate is not in profile → should not be emitted
    assert "debate" not in started
    assert "research" in started
