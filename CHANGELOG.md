# Changelog

All notable changes to MemoryX are documented in this file.

## [3.2.0] - 2026-06-12

### Major: Evolutionary Trajectory

- **Evolutionary Trajectory System** (`memoryx/evolution/`)
  - New data model: `EvolutionTrajectory`, `EvolutionNode`, `EvolutionKind`, `PreferenceSignal`
  - `EvolutionManager` with `observe()` + per-slot `get_trajectory()`
  - SQLite migration `012_evolution_trajectory.sql`
  - Auto-decay on superseded nodes (Ebbinghaus) — no hard deletion
  - Preference shifts (e.g. "favorite singer 张杰 → 房东的猫) no longer trigger
    flagged as contradiction

### Major: Query Understanding

- **Bilingual query intent classifier (`memoryx/retrieval/query_understanding.py`)
  - 10 intents: coding, debugging, deployment, planning, project, workflow,
    preference, emotional, troubleshooting, fact
  - Bilingual keyword catalog (Chinese + English, zero external deps
  - Silent fallback to generic retrieval when intent is unknown
  - Zero network / zero LLM call — pure keyword matching for latency safety

### Major: CJK Search + Fuzzy Matching

- **CJK bigram tokenizer** — contiguous 中文/日本語/한국어 text is tokenized
  into individual chars + 2-char bigrams so "记忆系统" is searchable
  without whitespace. Mixed-language segments like "部署docker" are
  split automatically.
- **Fuzzy / pinyin search** — Levenshtein edit distance + synonym alias
  table (`config` ↔ `configuration`; `错误` ↔ `bug`; optional
  `pypinyin` when available).
- No breaking changes to the default `search_full_text` API.

### Performance: Parallel Retrieval

- Vector DB and SQLite FTS5 now run in parallel via `asyncio.gather`
- `_enrich_evolution_meta` reimplemented with an O(n) index — reduces
  evolution-metadata attachment — previously O(results × nodes)
- `_entity_overlap` bug fix — was storing generators, now stores tokens.

### Integration

- LangChain: `memoryx/integrations/langchain/memory.py` —
  `MemoryXChatMessageHistory` + `MemoryXRetriever`
- ConflictResolver: preference-shift detection
  (e.g. 张杰 → 房东的猫) no longer triggers conflict; real contradictions
  are still detected.
- REST route `memoryx/api/routes/evolution.py`
  (optional;懒加载,默认不破坏现有路由)

### Benchmarks & docs

- `tests/benchmarks/test_longmemeval.py` +
- `tests/benchmarks/test_evolution.py`
- `docs/evolution/01_concept.md`, `02_data_model.md`, `03_api.md`
- `docs/pipeline/01_extraction.md ~ `05_forgetting.md`
- `docs/benchmarks.md`
- README updated with QueryUnderstanding + CJK + fuzzy in features/architecture docs

### Updated `.gitignore`

- Added `.trae/` and ad-hoc `test_*.py` / `run_*.ps1` exclusions

---

## [3.1.0] - 2026-06-08

### Major: Configuration Wizard
- Added interactive 5-step `configure_memoryx.sh` for full setup
- Steps: env check, module config, .env generation, deps install, launch

### Major: Memory Source Policy
- Added MEMORYX_UNIQUE_MEMORY_SOURCE flag
- Sole Source mode: MemoryX takes over all memory functions
- Coexistence mode (default): augments existing memory systems
- Wizard asks user for their preferred strategy

### Hermes Coexistence (Verified)
- MemoryX at abstraction layer, Hermes at platform layer: no conflict
- Only memory tool intercepted via HermesCompatibilityAdapter
- Guard decisions apply only to memory operations

### Documentation
- Updated README.md, CHANGELOG.md, VERSION to 3.1.0

## [3.0.1] - 2026-06-07

### Security and Release Completion
- Hardened context isolation so retrieved memory, tool output, artifacts, and runtime context are rendered as untrusted data blocks.
- Added adversarial tests proving malicious retrieved memories do not become executable instructions.
- Improved semantic compression with deterministic clustering, conservative archive decisions, and source-memory provenance.
- Added compression audit coverage for source IDs, checksums, rollback metadata, and archive decisions.
- Published this patch release from the current hardening commit because the existing `v3.0.0` tag predates the final safety hardening changes.

## [3.0.0] - 2026-06-07

### Phase 7 — Cognitive Capability Upgrade (7 sub-phases)

**7A: Ebbinghaus Forgetting Curve**
- Added `memoryx/cognitive/ebbinghaus.py` — Ebbinghaus exponential decay function with configurable retention and decay rate
- Integrated into `retrieval/scorer.py` as `ebbinghaus_decay_multiplier`
- Added spaced repetition scheduling in `consolidation/engine.py`

**7B: Baddeley Working Memory Model**
- Added `memoryx/cognitive/working_memory.py` — phonological loop, visuospatial sketchpad, episodic buffer, central executive
- 17 unit tests covering capacity limits, decay, interference patterns

**7C: Dual-Process Retrieval (System 1 / System 2)**
- Added `memoryx/cognitive/dual_process.py` — fast intuitive vs slow deliberate retrieval paths
- 15 unit tests covering confidence thresholds, conflict resolution

**7D: Memory Consolidation and Replay**
- Added `memoryx/consolidation/replay.py` — background memory replay with importance-weighted prioritization
- Integration with ConsolidationScheduler for idle-time processing
- 11 unit tests for replay queue and consolidation logic

**7E: Predictive Coding and Active Inference**
- Added `memoryx/cognitive/predictive_coding.py` — prediction error minimization, belief updating, free energy principle
- 10 unit tests covering prediction generation and error-driven learning

**7F: Cognitive Load Optimization**
- Added `memoryx/cognitive/cognitive_load.py` — intrinsic/extraneous/germane load tracking, adaptive context budget adjustment
- 12 shared tests with procedural memory module

**7G: Procedural Memory**
- Added `memoryx/cognitive/procedural_memory.py` — skill pattern learning, execution frequency tracking, automaticity detection
- Pattern recognition for repeated operations

### Phase A-F — Architecture Restructuring Baseline (v2.2.0→v3.0.0)

**Phase A: Legacy Import Elimination**
- Redirected all `memoryx.core.*` imports through compatibility shims
- No new code depends on `memoryx/core/` modules
- Added deprecation warnings for all legacy import paths

**Phase B: Unified Write Path**
- MemoryCandidateService established as the single authoritative write entry point
- HermesProvider, MCP tools, and API writes all routed through unified repository
- Eliminated dual-track writes between provider_index.json and SQLite

**Phase C: Unified Retrieval and Scoring**
- HybridRetrievalEngine is the single authoritative retrieval engine
- Merged duplicate scoring logic from core/scoring.py into retrieval/scorer.py
- Consistent scoring pipeline across memory search, MCP search, and Hermes context injection

**Phase D: Hermes Integration Normalization**
- Clear boundaries: HermesMemoryBridge ↔ MemoryXHermesProvider ↔ MCP server
- Authoritative native memory() patch with SHA256 verification and rollback
- Hermes E2E lifecycle test covering add→retrieve→forget, conflict detection, context injection

**Phase E: Module Relocation and Root Cleanup**
- pii_filter.py → safety/pii_filter.py (backward-compatible import retained)
- temporal_scorer.py → temporal/scorer.py
- symbolic.py → graph/symbolic.py
- conversation_log.py → storage/conversation_log.py
- events.py / event_bus.py → runtime/events.py / runtime/event_bus.py
- hermes_bridge.py / hermes_provider.py → hermes/bridge.py / hermes/provider.py

**Phase F: Test and Quality Gates**
- Architecture contract tests: forbid new memoryx.core imports, enforce MCP data isolation, verify Hermes path integrity
- All legacy tests updated to use current module paths
- 993 tests passing, 0 failing (up from 849 baseline)

### ConsolidationScheduler Hardening
- Added `health()` method returning full status dictionary
- `metrics` property tracking passes, replays, decays, reinforcements
- Retry logic with exponential backoff (configurable max_retries)
- Timeout-safe stop() using asyncio.wait_for
- Non-fatal per-operation error handling

### Competitive Benchmarks
- Added `tests/benchmarks/test_competitive_benchmark.py` — MemoryX vs Mem0/Letta/Zep
- Covers short-term recall, conflict detection, session isolation, Ebbinghaus decay, context retrieval
- External benchmarks (Mem0/Letta/Zep) are placeholder until API keys are configured

### Documentation
- 7 bilingual (Chinese/English) cognitive module docs in docs/cognitive/
- Competitive analysis: docs/competitive_analysis.md
- Updated all module-level docstrings

## [2.1.1] - 2026-06-03

### Phase 1 — Memory Kernel
- Memory Kernel with evidence_events / claims / claim_versions / fts_memories schema.
- MemoryKernel class: create_evidence / create_claim / revoke_claim / supersede_claim with version history.
- Retriever class: FTS5 keyword search with configurable options.
- 22 new tests for kernel and retriever (849 total, all passing).
- Version bump: 2.1.0 → 2.1.1.

## [2.1.0] - 2026-06-03

### Phase 0 — Foundation
- Unified version to single source of truth (VERSION / _version.py / pyproject.toml).
- Added `memoryx doctor` self-check command (lite/standard/dev profiles).
- Added three installation profiles: lite, standard, dev with separate env examples.
- Added `check_release_truth` release consistency script.
- Updated README installation and configuration sections.
- All 827 tests passing.

## [2.0.0] - 2026-05-29

### Stable release
- Published MemoryX 2.0.0 stable.
- Added release archive and checksum verification.
- Completed production acceptance for Hermes integration.
- Kept v2.0.0-rc.1 and v2.0.0-rc.2 as prerelease history.
