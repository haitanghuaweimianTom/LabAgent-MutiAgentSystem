# labagent Plugin SDK Guide

> Author your own plugin for the MathModel-MutiAgentSystem pipeline.
> Mirrors the DeepSeek Harness / Cordis plugin contract.

## 0. What is a plugin?

A plugin is a small Python class (or function) that hooks into the paper
generation pipeline. Plugins can:

- listen to lifecycle events (e.g. `step/start`, `session/end`)
- call host services (LLM, session log, file IO)
- register their own services for other plugins to consume
- survive unload via reversible effects (DSH invariant)

## 1. Quick start

```python
# my_plugin/plugin.py
from labagent.plugin import Context, EventKind, SessionLog

class MyPlugin:
    name = "my_plugin"
    inject = ["session_log"]  # declare host services you need

    def setup(self, ctx: Context) -> None:
        log = ctx.require("session_log")
        ctx.on("session/end", lambda p: self._on_session_end(p, log))

    def _on_session_end(self, payload, log):
        for e in log.read_all():
            print(e.kind, e.payload)
```

Ship as a pip package:

```toml
# pyproject.toml
[project]
name = "labagent-my-plugin"
version = "0.1.0"
requires-python = ">=3.10"

[project.entry-points."labagent.plugins"]
my_plugin = "my_plugin.plugin:MyPlugin"
```

Install: `pip install labagent-my-plugin` → it auto-loads on host startup.

## 2. Plugin contract

```python
class Plugin:
    name: str                    # unique identifier
    inject: list[str] = []       # host service names required (e.g. ["llm_call", "session_log"])

    def setup(self, ctx: Context) -> None:
        # Register hooks, declare services, set up effects.
        # Never blocks the pipeline; can be sync or async.
        ...
```

If your plugin is a plain function:

```python
def apply(ctx: Context) -> None:
    ctx.on("step/start", lambda p: ...)

plugin_name = "my_plugin"  # module-level
plugin_inject = ["session_log"]  # module-level (optional)
```

The host wraps this as a Plugin automatically.

## 3. Host services

The `Context` exposes a typed service registry. To use a service:

| Service | Purpose |
|---------|---------|
| `ctx.require("session_log")` | `SessionLog` — append-only event log (Model-visible means logged) |
| `ctx.require("llm_call")` | async callable `(system, user, max_tokens) -> dict` (MiniMax API) |
| `ctx.require("evolution_store")` | `EvolutionStore` — JSONL lessons store |
| `ctx.require("reflection_agent")` | `ReflectionAgent` — LLM-based lesson extractor |
| `ctx.require("memory_store")` | `MemoryStore` — Jaccard semantic memory |
| `ctx.require("skill_library")` | `SkillLibrary` — Voyager-style verified solutions |
| `ctx.require("healer")` | `SelfHealer` — auto error classification/fix |
| `ctx.require("quality_gate")` | `IterativeQualityGate` — auto-continue/revise/terminate |
| `ctx.require("debate")` | `EnhancedDebate` — 6-persona multi-perspective eval |

## 4. The 5-mode event bus

```python
# Fire-and-forget
ctx.emit("step/start", {"step": "research"})

# Sync: first listener with non-None return wins
ctx.bail("quality/decision", stage="research")

# Async: concurrent
await ctx.parallel("llm/pre-call", payload)

# Async: first non-None wins
result = await ctx.serial("tool/pre-execute", exec_data)

# Async: middleware chain
result = await ctx.waterfall("llm/stream", chunks, next=...)
```

## 5. Reversible effects (DSH invariant)

Anything you register must be reversible. `ctx.on(...)` returns a handle
that the host disposes on unload. For your own resources:

```python
def setup(self, ctx):
    f = open("my_resource.txt")
    ctx.effect(lambda: f.close())   # disposed on unload
```

## 6. Extension points (canonical event names)

| Event | When | Payload |
|-------|------|---------|
| `session/start` | session begin | `{run_id, template, problem}` |
| `session/end` | session done | `{stage_results, run_id}` |
| `step/start` | each pipeline step begins | `{step, name}` |
| `step/end` | each pipeline step ends | `{step, result}` |
| `llm/pre-call` | before LLM call (waterfall) | `{system, user, max_tokens}` |
| `llm/post-call` | after LLM call (waterfall) | `{content, usage}` |
| `tool/pre-execute` | before tool (waterfall) | `{name, args}` → return `{kind: "deny" or "allow"}` |
| `tool/post-execute` | after tool (waterfall) | `{name, result}` |
| `quality/evaluate` | quality decision (parallel) | `{stage, metrics}` |

## 7. Local development (no install)

```bash
mkdir -p plugins/
cat > plugins/my-plugin/plugin.yaml <<EOF
name: my-plugin
version: 0.1.0
entry: my_pkg.module:plugin
inject: [session_log]
EOF
```

The host's `PluginManager(plugin_dirs=["./plugins"])` scans this on startup.

## 8. Running

```python
from labagent.plugin import Context, PluginManager
from labagent.plugin.discovery import discover_entry_points, discover_directories

ctx = Context()
# Register host services first
ctx.register("llm_call", my_llm)
ctx.register("session_log", my_log)

mgr = PluginManager(ctx, plugin_dirs=["./plugins"])
mgr.discover()    # entry_points + directory
mgr.load_all()    # activate all

# ... use ctx ...

mgr.shutdown()    # dispose everything
```

## 9. Worked example: labagent_hello_plugin

```python
from labagent.plugin import Context, EventKind, SessionLog

class HelloPlugin:
    name = "hello"
    inject = ["session_log"]

    def setup(self, ctx: Context) -> None:
        log = ctx.require("session_log")
        ctx.on("step/start", lambda p: log.append(
            EventKind.STEP_START, p
        ))
```

That's the smallest useful plugin. See `src/labagent_hello_plugin/`.
