"""labagent.plugin - DSH/Cordis-style plugin host.

Public API for plugins to interact with the host.
"""

from .context import Context
from .disposer import DisposerHandle
from .event_bus import EventBus
from .plugin import Plugin, PluginSpec
from .manager import PluginManager
from .discovery import (
    discover_entry_points,
    discover_directories,
    load_plugin_instance,
)
from .session_log import (
    SessionLog,
    SessionEvent,
    EventKind,
    derive_session_id,
    CURRENT_VERSION,
)
from .bundle import (
    Profile,
    Bundle,
    load_profile,
    load_bundle,
    discover_bundles,
    collect_bundle_plugins,
)

__all__ = [
    "Context",
    "DisposerHandle",
    "EventBus",
    "Plugin",
    "PluginSpec",
    "PluginManager",
    "discover_entry_points",
    "discover_directories",
    "load_plugin_instance",
    "SessionLog",
    "SessionEvent",
    "EventKind",
    "derive_session_id",
    "CURRENT_VERSION",
    "Profile",
    "Bundle",
    "load_profile",
    "load_bundle",
    "discover_bundles",
    "collect_bundle_plugins",
]
