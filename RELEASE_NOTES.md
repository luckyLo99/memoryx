# MemoryX v3.0.1 Release Notes

Release date: 2026-06-07

## Security and Release Completion

MemoryX v3.0.1 publishes the final context-isolation and compression hardening
from the current release branch. The earlier `v3.0.0` tag existed before these
last safety changes and did not have a GitHub Release entry, so this patch
release is the canonical GitHub release for the completed v3 line.

### Highlights

- Strong untrusted-context rendering for retrieved memory, tool output, artifacts, and runtime context.
- Adversarial tests that verify malicious memories stay data-only and cannot become instructions.
- Deterministic semantic compression clustering with conservative archive gates.
- Compression provenance that records source memory IDs, checksums, rollback metadata, and archive decisions.
- GitHub Actions green for release gate, privacy guard, and security scans on the hardening commit.

## What's New

MemoryX v3.0.0 is a major release that introduces comprehensive cognitive science models, completes the architecture restructuring, and adds  reliability features.

### Cognitive Architecture (Phase 7)

| Module | Model | Scientific Basis |
|--------|-------|-----------------|
| Ebbinghaus Forgetting Curve | Exponential decay + spaced repetition | Ebbinghaus (1885) |
| Baddeley Working Memory | Phonological loop, sketchpad, buffer | Baddeley (1992) |
| Dual-Process Retrieval | System 1 (fast) / System 2 (slow) | Kahneman (2011) |
| Predictive Coding | Active inference, free-energy principle | Friston (2010) |
| Cognitive Load Optimization | Intrinsic/extraneous/germane load | Sweller (1988) |
| Procedural Memory | Skill learning, automaticity | Squire (1986) |

### Architecture Restructuring (Phase A-F)

- Legacy `memoryx/core/*` eliminated — all paths unified to current architecture
- Single authoritative write path via MemoryCandidateService
- Unified HybridRetrievalEngine as the sole retrieval engine
- Hermes integration normalized with SHA256-verified patch and rollback
- Root directory cleanup — all modules properly namespaced
- Architecture contract tests enforce quality gates

### Stability Improvements

- ConsolidationScheduler with health checks, metrics, and exponential-backoff retry
- Competitive benchmark suite (MemoryX vs Mem0/Letta/Zep)
- Hermes E2E lifecycle test (add -> retrieve -> forget -> conflict detection -> context injection)

## Test Statistics

- **993 tests passing, 0 failing** (baseline was 849)
- 100% commit-stage pass rate
- Hermes lifecycle simulation: 3 integration tests
- Cognitive module unit tests: 77+ tests across 6 modules
- Architecture contract tests: import isolation, data directory isolation

## Upgrade Notes

- v3.0.0 is backward-compatible with v2.1.1 data stores (no migration needed)
- Legacy `memoryx.core.*` imports still work but emit deprecation warnings
- All existing Hermes integration scripts remain compatible
- `pytest.ini` markers updated — register "benchmark" and "slow" markers

## Contributors

MemoryX is developed by luckyl214 with design inspiration from the open-source projects and academic papers listed in CREDITS.md.
