# labagent Plugin Marketplace (stub)

> Internal listing of available plugins. A real marketplace would have
> install counts, ratings, search, etc. This file is the seed.

## Bundled plugins (ship with the host)

| Plugin | Description | Inject | Services it provides |
|--------|-------------|--------|---------------------|
| `labagent_hello_plugin` | Canonical example; logs step events | `session_log` | (none) |
| `labagent_evolve` | Self-evolution v2: lesson extraction + effectiveness tracking | `llm_call`, `session_log` | `evolution_store`, `reflection_agent` |
| `labagent_memory` | Persistent semantic memory across runs | `session_log` | `memory_store` |
| `labagent_skills` | Voyager-style verified code/writing/prompt skills | `session_log` | `skill_library` |
| `labagent_healer` | Auto error classification + circuit breaker | `session_log` | `healer` |
| `labagent_quality` | Iterative quality gate (auto-continue/revise/terminate) | `session_log` | `quality_gate` |
| `labagent_debate` | 6-persona multi-perspective evaluation | `llm_call`, `session_log` | `debate` |

## How to author a new plugin

See `docs/PLUGIN_GUIDE.md`. The minimum is a `class` with `name`, `inject`, and `setup(ctx)`.

## Submitting

(Not yet.) Future: `dsh plugin add <git-url>` style command, marketplace API.
