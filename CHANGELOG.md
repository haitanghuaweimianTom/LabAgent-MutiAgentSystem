# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [8.2.0] - 2025-07-21

### Fixed
- Removed API keys from repository
- Fixed debug endpoint exposing API key prefix
- Unified version numbers across all files
- Unified port configuration to 8001
- Fixed bare exception catches in task_persistence.py
- Fixed uninitialized `last_error` variable in `_call_claude_coder_http`
- Removed CORS wildcard configuration
- Fixed hardcoded paths in MCP configuration
- Merged duplicate .env files
- Removed unused anthropic/openai SDK dependencies
- Removed unused axios dependency from frontend
- Cleaned up build artifacts from git
- Applied rate limiting to task submission endpoint
- Fixed Docker port mapping consistency
- Unified brand name to LabAgent

### Added
- CI/CD pipeline with GitHub Actions
- Jest testing framework for frontend
- CONTRIBUTING.md
- CHANGELOG.md

## [8.1.0] - 2025-07-15

### Added
- Multi-KB task injection support
- Task-level knowledge base auto-cleanup
- Knowledge base file download

## [8.0.0] - 2025-07-10

### Added
- Agent memory self-evolution
- Token budget management
- Blackboard context trimming

## [7.3.0] - 2025-06-20

### Added
- LangGraph + ReAct + Harness data-driven transformation
- CC Switch dynamic sync
- Frontend notification dropdown

## [7.0.0] - 2025-06-01

### Added
- AI Scientist full automated pipeline
- Requirement decomposition
- Innovation discovery
- Discussion voting
- Knowledge base organization

## [6.0.0] - 2025-05-15

### Added
- Multi-agent real-time collaborative discussion
- User participation
- Automatic iteration

## [5.0.0] - 2025-04-20

### Added
- LangGraph + ReAct integration
- Paper templates registry
- Camera-ready pipeline

## [3.0.0] - 2025-03-15

### Added
- Multi-agent memory system
- Agent model router
- Cross-validator

## [2.0.0] - 2025-02-10

### Added
- Unified workflow engine
- Knowledge base integration
- MCP support

## [1.0.0] - 2025-01-15

### Added
- Initial release
- Basic paper generation workflow
- Frontend UI
