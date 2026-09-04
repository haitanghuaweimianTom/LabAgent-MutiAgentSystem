"""PluginManager - load, activate, unload plugins.

Activation is service-availability driven: a plugin declares `inject = [...]`
and the manager calls setup() only once all those services are registered.

Unload is reverse-order with all disposers invoked (DSH reversible effect invariant).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Optional

from .context import Context
from .discovery import discover_directories, discover_entry_points, load_plugin_instance
from .disposer import DisposerHandle
from .plugin import Plugin, PluginSpec

logger = logging.getLogger(__name__)


class PluginManager:
    """Manages the lifecycle of all plugins on a single Context.

    Typical use:
        ctx = Context()
        mgr = PluginManager(ctx, plugin_dirs=["./plugins"])
        mgr.discover()              # entry_points + directory scan
        mgr.load_all()              # instantiate, register, activate

    At shutdown:
        mgr.shutdown()              # unload in reverse order
    """

    def __init__(
        self,
        ctx: Context,
        *,
        plugin_dirs: Optional[Iterable[Path | str]] = None,
    ) -> None:
        self.ctx = ctx
        self.plugin_dirs: list[Path] = [Path(d) for d in (plugin_dirs or [])]
        self._specs: list[PluginSpec] = []
        self._plugins: dict[str, Plugin] = {}
        # Stack of disposers per plugin, in registration order
        self._plugin_disposers: dict[str, list[DisposerHandle]] = {}

    @property
    def specs(self) -> list[PluginSpec]:
        return list(self._specs)

    @property
    def plugins(self) -> dict[str, Plugin]:
        return dict(self._plugins)

    # --- Discovery ---

    def discover(self) -> list[PluginSpec]:
        """Discover all plugins: entry_points + configured directories."""
        seen: dict[str, PluginSpec] = {}

        for spec in discover_entry_points():
            seen.setdefault(spec.name, spec)

        for d in self.plugin_dirs:
            for spec in discover_directories(d):
                seen.setdefault(spec.name, spec)

        self._specs = list(seen.values())
        return self._specs

    # --- Loading ---

    def load_all(self) -> list[Plugin]:
        """Instantiate and activate all discovered plugins."""
        if not self._specs:
            self.discover()
        loaded: list[Plugin] = []
        for spec in self._specs:
            try:
                plugin = self.activate(spec)
                loaded.append(plugin)
            except Exception as e:
                logger.error(f"Failed to load plugin {spec.name!r}: {e}")
        return loaded

    def activate(self, spec_or_plugin) -> Plugin:
        """Load a single plugin from spec OR a pre-constructed plugin instance.

        Replaces any existing plugin with the same name (last-one-wins).
        """
        if isinstance(spec_or_plugin, PluginSpec):
            spec = spec_or_plugin
            instance = load_plugin_instance(spec)
        else:
            instance = spec_or_plugin
            spec = PluginSpec(name=instance.name, entry="<inline>")

        # Check inject dependencies
        for dep in getattr(instance, "inject", []) or []:
            if dep not in self.ctx._services:
                raise KeyError(
                    f"Plugin {spec.name!r} requires service {dep!r} "
                    f"which is not registered. Order matters: register deps first."
                )

        # If already loaded, unload first (last-one-wins)
        if spec.name in self._plugins:
            self.unload(spec.name)

        # Track disposers registered during setup so unload can rewind
        before = set(id(h) for h in self.ctx._disposers)
        try:
            instance.setup(self.ctx)
        except Exception:
            # Revert any disposers registered before the failure
            new_handles = [h for h in self.ctx._disposers if id(h) not in before]
            for h in reversed(new_handles):
                h.dispose()
            self.ctx._disposers = [h for h in self.ctx._disposers if id(h) in before]
            raise

        new_disposers = [h for h in self.ctx._disposers if id(h) not in before]
        self._plugin_disposers[spec.name] = new_disposers
        self._plugins[spec.name] = instance

        # Flush any deferred inject callbacks that this plugin's services unblocked
        self.ctx.resolve_pending_injects()

        logger.info(f"Loaded plugin {spec.name!r}")
        return instance

    def unload(self, name: str) -> None:
        """Unload a single plugin: dispose all its effects in reverse order."""
        if name not in self._plugins:
            return
        disposers = self._plugin_disposers.pop(name)
        for h in reversed(disposers):
            h.dispose()
        del self._plugins[name]
        logger.info(f"Unloaded plugin {name!r}")

    def shutdown(self) -> None:
        """Unload all plugins (reverse order) and shut down the context."""
        for name in list(reversed(self._plugins)):
            self.unload(name)
        self.ctx.shutdown()
