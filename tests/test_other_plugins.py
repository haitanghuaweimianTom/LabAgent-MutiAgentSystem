"""Tests for the other 5 plugin adapters (P3).

Each test instantiates a plugin, registers minimal host services, and checks
that the plugin's setup() either raises on missing inject (without services)
or registers the expected downstream services.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from labagent.plugin import Context, SessionLog


def _ctx_with_minimal_services(tmp_path, **extras) -> Context:
    """Build a context with the minimal service set most plugins need."""
    log = SessionLog(session_id="t", root=tmp_path)
    ctx = Context()
    ctx.register("session_log", log)
    for k, v in extras.items():
        ctx.register(k, v)
    return ctx


class TestMemoryPlugin:
    def test_requires_dependencies(self):
        from labagent_memory.plugin import MemoryPlugin
        ctx = Context()
        with pytest.raises(KeyError):
            MemoryPlugin().setup(ctx)

    def test_registers_memory_store(self, tmp_path):
        from labagent_memory.plugin import MemoryPlugin
        ctx = _ctx_with_minimal_services(tmp_path)
        MemoryPlugin(store_dir=tmp_path / "memory").setup(ctx)
        assert ctx.get("memory_store") is not None


class TestSkillsPlugin:
    def test_requires_dependencies(self):
        from labagent_skills.plugin import SkillsPlugin
        ctx = Context()
        with pytest.raises(KeyError):
            SkillsPlugin().setup(ctx)

    def test_registers_skill_library(self, tmp_path):
        from labagent_skills.plugin import SkillsPlugin
        ctx = _ctx_with_minimal_services(tmp_path)
        SkillsPlugin(store_dir=tmp_path / "skills").setup(ctx)
        assert ctx.get("skill_library") is not None


class TestHealerPlugin:
    def test_requires_dependencies(self):
        from labagent_healer.plugin import HealerPlugin
        ctx = Context()
        with pytest.raises(KeyError):
            HealerPlugin().setup(ctx)

    def test_registers_healer(self, tmp_path):
        from labagent_healer.plugin import HealerPlugin
        ctx = _ctx_with_minimal_services(tmp_path)
        HealerPlugin(state_dir=tmp_path / "healer").setup(ctx)
        assert ctx.get("healer") is not None


class TestQualityPlugin:
    def test_requires_dependencies(self):
        from labagent_quality.plugin import QualityPlugin
        ctx = Context()
        with pytest.raises(KeyError):
            QualityPlugin().setup(ctx)

    def test_registers_quality_gate(self, tmp_path):
        from labagent_quality.plugin import QualityPlugin
        ctx = _ctx_with_minimal_services(tmp_path)
        QualityPlugin(state_dir=tmp_path / "qg").setup(ctx)
        assert ctx.get("quality_gate") is not None


class TestDebatePlugin:
    def test_requires_dependencies(self):
        from labagent_debate.plugin import DebatePlugin
        ctx = Context()
        with pytest.raises(KeyError):
            DebatePlugin().setup(ctx)

    def test_registers_debate(self, tmp_path):
        from labagent_debate.plugin import DebatePlugin
        ctx = _ctx_with_minimal_services(
            tmp_path,
            llm_call=lambda *a, **kw: {"content": "{}"},
        )
        DebatePlugin().setup(ctx)
        assert ctx.get("debate") is not None
