"""Tests for labagent_llm_cache_plugin."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from labagent.plugin import Context


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_llm_cache_hits_on_repeat(tmp_path):
    from labagent_llm_cache_plugin.plugin import LLMCachePlugin
    cache_dir = tmp_path / "cache"
    p = LLMCachePlugin(cache_dir=cache_dir)

    # First call: cache miss → returns None
    miss_result = _run(p.llm_call({"system": "you are X", "user": "hello", "max_tokens": 100}))
    assert miss_result is None
    assert p.misses == 1
    assert p.hits == 0

    # Register the cache miss → make the original call return a real result
    p.record({"system": "you are X", "user": "hello", "max_tokens": 100},
             {"content": "hi back", "usage": {"total_tokens": 5}})

    # Second call: same prompt → cache hit
    hit_result = _run(p.llm_call({"system": "you are X", "user": "hello", "max_tokens": 100}))
    assert hit_result is not None
    assert hit_result["content"] == "hi back"
    assert hit_result.get("cached") is True
    assert p.hits == 1


def test_llm_cache_different_prompts_are_separate(tmp_path):
    from labagent_llm_cache_plugin.plugin import LLMCachePlugin
    p = LLMCachePlugin(cache_dir=tmp_path / "cache")
    p.record({"system": "x", "user": "q1", "max_tokens": 1}, {"content": "A", "usage": {}})
    p.record({"system": "x", "user": "q2", "max_tokens": 1}, {"content": "B", "usage": {}})

    r1 = _run(p.llm_call({"system": "x", "user": "q1", "max_tokens": 1}))
    r2 = _run(p.llm_call({"system": "x", "user": "q2", "max_tokens": 1}))
    assert r1["content"] == "A"
    assert r2["content"] == "B"


def test_llm_cache_persists_across_instances(tmp_path):
    from labagent_llm_cache_plugin.plugin import LLMCachePlugin
    cache_dir = tmp_path / "cache"
    p1 = LLMCachePlugin(cache_dir=cache_dir)
    p1.record({"system": "x", "user": "q", "max_tokens": 1}, {"content": "P", "usage": {}})

    p2 = LLMCachePlugin(cache_dir=cache_dir)
    r = _run(p2.llm_call({"system": "x", "user": "q", "max_tokens": 1}))
    assert r is not None
    assert r["content"] == "P"
