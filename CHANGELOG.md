# Changelog

All notable changes to mini-harness will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-02

### Added

#### DeepSeek API Integration
- **llm_client.py**: DeepSeek API adapter with OpenAI SDK, .env-based credential loading, streaming support via `on_chunk` callback
- **expert_functions.py**: Four production-ready expert functions (code_reviewer, security_expert, test_writer, doc_writer) with streaming progress callbacks
- **demo_v2.py**: Rewritten as real multi-agent demo with `--stream`, `--quick`, `--task`, `--api-check` flags
- Stream-to-console progress display with thread-safe ProgressDisplay class
- Windows UTF-8 encoding fix for CJK character display

#### Developer Experience
- `py demo_v2.py --api-check` to verify DeepSeek connectivity
- `py demo_v2.py --quick` for fast demo with smaller task
- `py demo_v2.py --stream` for real-time expert output streaming

### Security

- **[CRITICAL]** `SessionStore.get_messages`: Parameterized LIMIT clause (SQL injection fix)
- **[HIGH]** `AgentHarness._run_single_agent`: Tool argument validation against registered schema before dispatch (LLM prompt injection defense)
- **[HIGH]** `Orchestrator._llm_decompose`: SubTask whitelist validation (ID format, domain names, priority values) after JSON deserialization
- **[MEDIUM]** `PermissionGate.check_agent_call`: Default policy changed from ALLOW to DENY
- **[MEDIUM]** `AgentHarness._redact_metadata`: Automatic redaction of sensitive metadata keys (args, api_key, token, secret, password)
- **[MEDIUM]** `Tracer._print`: Sensitive pattern redaction before stdout output
- **[MEDIUM]** `.gitignore`: Added `.env`, `.env.*`, `*.key`, `*.pem` patterns
- **[LOW]** `Recovery.save/save_branch`: Deep copy (`copy.deepcopy`) replaced shallow copy for checkpoint snapshots
- **[LOW]** `Compressor.compress_branch`: Explicit `hasattr` check replaced silent `getattr` fallback

### Fixed

- `AgentHarness.run_multi`: Synthesizer llm_fn signature mismatch (1-arg vs 2-arg) fixed with lambda wrapper
- `tool_registry.py`: Docstring example changed from `eval()` to `ast.literal_eval`
- `ci.yml`: Removed `|| true` from mypy step; removed non-existent `types-tiktoken` package
- `orchestrator.py`: Added type annotation for `all_expert_domains`
- `harness.py`: Added type annotation for `_redact_metadata` return value
- 21 f-string-without-placeholders (F541) lints fixed across `synthesizer.py` and `harness.py`

### Changed

- `requirements.txt`: Added `openai>=1.0.0` and `python-dotenv>=1.0.0` for production LLM integration
- `ci.yml`: mypy step no longer silenced; type errors now block CI

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

[1.1.0]: https://github.com/2913636/mini-harness/releases/tag/v1.1.0
[1.0.0]: https://github.com/2913636/mini-harness/releases/tag/v1.0.0
