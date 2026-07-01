# Changelog

All notable changes to mini-harness will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-01

### Added

#### v2: Multi-Agent Orchestration System
- **ExpertRegistry**: Expert agent registration, domain-based matching, capability catalog generation
- **Orchestrator**: Task decomposition, expert matching, DAG-based dispatch, gap detection, LLM fallback
- **ResultSynthesizer**: Multi-expert result merging, priority-weighted ordering, deduplication, source annotation

#### v2: Component Upgrades
- **SessionStore**: Tree message support (parent_id, expert_id, branch_id), per-branch and per-expert query methods
- **PermissionGate**: Agent-to-Agent call permissions via AgentRule
- **Compressor**: Per-branch compression via `compress_branch()`
- **Tracer**: Multi-agent causal chain (expert_id, parent_step_id), expert performance statistics
- **Recovery**: Branch-level checkpoint (save_branch, restore_branch, clear_branch)
- **ToolRegistry**: Expert-to-tool bridge via `register_expert_as_tool()`

#### v1: Initial Release (Six-Component Agent Runtime)
- **ToolRegistry**: Tool registration with JSON Schema, category-based filtering, LLM-format export
- **PermissionGate**: Three-tier check (exact/wildcard/category), ALLOW/DENY/ASK policies
- **SessionStore**: SQLite-backed session persistence, message CRUD, state management
- **Compressor**: Three strategies (truncate/summarize/hybrid), tiktoken integration
- **Tracer**: Structured step tracking with span context manager, SQLite + console output
- **Recovery**: Checkpoint-based state recovery for interrupted agent runs

### Changed
- AgentHarness now auto-detects multi-agent mode when experts are registered
- Message dataclass extended with parent_id, expert_id, branch_id fields (backward compatible)
- TraceStep dataclass extended with expert_id, parent_step_id fields (backward compatible)

### Fixed
- N/A (initial release)

[1.0.0]: https://github.com/2913636/mini-harness/releases/tag/v1.0.0
