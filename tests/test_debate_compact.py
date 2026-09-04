"""Tests for debate-compact plugin."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_compact_debate_uses_3_personas():
    from labagent_debate_compact.plugin import CompactDebatePlugin
    p = CompactDebatePlugin()
    assert len(p.personas) == 3
    assert p.name == "debate_compact"


def test_compact_debate_registers_compact_debate_service(tmp_path):
    from labagent.plugin import Context
    from labagent_debate_compact.plugin import CompactDebatePlugin
    ctx = Context()
    # CompactDebate needs an llm_call
    ctx.register("llm_call", lambda s, u, t: {"content": "stub"})
    CompactDebatePlugin().setup(ctx)
    assert ctx.get("debate") is not None
    assert ctx.get("debate").persona_count == 3


def test_compact_debate_requires_llm():
    from labagent.plugin import Context
    from labagent_debate_compact.plugin import CompactDebatePlugin
    ctx = Context()
    # No llm_call registered
    try:
        CompactDebatePlugin().setup(ctx)
        assert False, "should have raised"
    except KeyError:
        pass
