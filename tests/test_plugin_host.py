"""Tests for plugin/host core (P1: minimal skeleton)."""
import sys
from pathlib import Path

# 让 tests 能 import src/labagent
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from labagent.plugin.context import Context
from labagent.plugin.event_bus import EventBus
from labagent.plugin.disposer import DisposerHandle
from labagent.plugin.plugin import PluginSpec, Plugin
from labagent.plugin.manager import PluginManager
from labagent.plugin.discovery import discover_entry_points, discover_directories


class TestEventBus:
    def test_emit_calls_all_listeners(self):
        bus = EventBus()
        calls = []
        bus.on("foo", lambda p: calls.append(p))
        bus.on("foo", lambda p: calls.append(("b", p)))
        bus.emit("foo", "x")
        assert calls == ["x", ("b", "x")]

    def test_parallel_awaits(self):
        import asyncio
        bus = EventBus()
        async def test():
            results = []
            async def listener(p):
                results.append(p * 2)
            bus.on("foo", listener)
            await bus.parallel("foo", 3)
            return results
        results = asyncio.run(test())
        assert results == [6]

    def test_serial_returns_first_non_none(self):
        import asyncio
        bus = EventBus()
        async def test():
            bus.on("foo", lambda p: None)
            bus.on("foo", lambda p: p + 1)
            bus.on("foo", lambda p: p + 10)
            return await bus.serial("foo", 1)
        assert asyncio.run(test()) == 2

    def test_bail_sync(self):
        bus = EventBus()
        bus.on("foo", lambda p: None)
        bus.on("foo", lambda p: p * 2)
        bus.on("foo", lambda p: p * 3)
        assert bus.bail("foo", 5) == 10

    def test_waterfall_chains_with_next(self):
        import asyncio
        bus = EventBus()
        async def test():
            # listener_a wraps listener_b: a(next=...) -> b() -> result, a returns result+1
            async def listener_a(p, *, next):
                result = await next()  # a delegates to b
                return result + 1
            async def listener_b(p, *, next):
                return p * 2  # b is terminal: no next() call
            bus.on("chain", listener_a)
            bus.on("chain", listener_b)
            return await bus.waterfall("chain", 5)
        assert asyncio.run(test()) == 11  # (5 * 2) + 1

    def test_waterfall_veto_skips_next(self):
        import asyncio
        bus = EventBus()
        async def test():
            async def vetoer(p, *, next):
                return "vetoed"  # doesn't call next
            async def downstream(p, *, next):
                return "should-not-run"
            bus.on("veto", vetoer)
            bus.on("veto", downstream)
            return await bus.waterfall("veto", 1)
        assert asyncio.run(test()) == "vetoed"

    def test_on_returns_disposable(self):
        bus = EventBus()
        calls = []
        handle = bus.on("foo", lambda p: calls.append(p))
        bus.emit("foo", 1)
        handle.dispose()
        bus.emit("foo", 2)
        assert calls == [1]


class TestDisposerHandle:
    def test_dispose_calls_cleanup(self):
        cleanup = []
        handle = DisposerHandle(lambda: cleanup.append("ok"))
        handle.dispose()
        assert cleanup == ["ok"]

    def test_dispose_idempotent(self):
        count = []
        handle = DisposerHandle(lambda: count.append(1))
        handle.dispose()
        handle.dispose()
        assert count == [1]


class TestContext:
    def test_register_and_get(self):
        ctx = Context()
        ctx.register("logger", "fake-logger")
        assert ctx.get("logger") == "fake-logger"

    def test_register_with_attribute_access(self):
        ctx = Context()
        ctx.register("config", "v1")
        assert ctx.config == "v1"

    def test_emit_dispatches_to_listeners(self):
        ctx = Context()
        calls = []
        ctx.on("step/start", lambda p: calls.append(p))
        ctx.emit("step/start", "research")
        assert calls == ["research"]

    def test_effect_registers_disposer(self):
        ctx = Context()
        cleanup = []
        ctx.effect(lambda: cleanup.append("closed"))
        ctx.shutdown()
        assert cleanup == ["closed"]

    def test_shutdown_disposes_in_reverse_order(self):
        ctx = Context()
        order = []
        ctx.effect(lambda: order.append("first"))
        ctx.effect(lambda: order.append("second"))
        ctx.shutdown()
        assert order == ["second", "first"]


class TestPluginSpec:
    def test_minimal(self):
        spec = PluginSpec(name="hello", entry="hello.mod:plugin")
        assert spec.name == "hello"
        assert spec.inject == []


class TestPluginProtocol:
    def test_plugin_implements_protocol(self):
        class MyPlugin:
            name = "my"
            def setup(self, ctx):
                ctx.on("foo", lambda p: p)
        p = MyPlugin()
        assert isinstance(p, Plugin)


class TestPluginManager:
    def test_activate_plugin(self):
        class P:
            name = "p1"
            def setup(self, ctx):
                ctx.on("foo", lambda p: p + 1)
        ctx = Context()
        mgr = PluginManager(ctx)
        mgr.activate(P())
        assert ctx.bail("foo", 10) == 11

    def test_activate_respects_inject(self):
        class P:
            name = "p2"
            inject = ["missing"]
            def setup(self, ctx):
                pass
        ctx = Context()
        mgr = PluginManager(ctx)
        with pytest.raises(KeyError):
            mgr.activate(P())

    def test_unload_disposes_effects(self):
        class P:
            name = "p3"
            def setup(self, ctx):
                ctx.effect(lambda: None)  # disposers list
        ctx = Context()
        mgr = PluginManager(ctx)
        mgr.activate(P())
        # unload should not raise
        mgr.unload("p3")
        assert "p3" not in mgr.plugins

    def test_double_activate_replaces(self):
        class P:
            name = "p4"
            def setup(self, ctx):
                ctx.on("foo", lambda p: 1)
        class P2:
            name = "p4"
            def setup(self, ctx):
                ctx.on("foo", lambda p: 2)
        ctx = Context()
        mgr = PluginManager(ctx)
        mgr.activate(P())
        mgr.activate(P2())
        # P2 should win
        assert ctx.bail("foo", 0) == 2


class TestDiscovery:
    def test_discover_directories_empty(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        specs = list(discover_directories(plugins_dir))
        assert specs == []

    def test_discover_directories_finds_yaml(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        my_plugin = plugins_dir / "my-plugin"
        my_plugin.mkdir(parents=True, exist_ok=True)
        (my_plugin / "plugin.yaml").write_text(
            "name: my-plugin\nversion: 0.1.0\nentry: my_plugin.mod:plugin\n"
        )
        specs = list(discover_directories(plugins_dir))
        assert len(specs) == 1
        assert specs[0].name == "my-plugin"
        assert specs[0].entry == "my_plugin.mod:plugin"

    def test_discover_entry_points_returns_list(self):
        specs = list(discover_entry_points("nonexistent.group.that.does.not.exist"))
        assert isinstance(specs, list)
