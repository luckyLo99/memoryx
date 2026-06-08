# Issue Drafts — MemoryX 2.0 PR Transition

> Status: Draft — not yet opened on GitHub.

---

## Issue #1: Context budget quota + deterministic compression

- **Type**: `type:feature`
- **Priority**: `P1`
- **Labels**: `area:context`, `area:retrieval`
- **Scope**: `memoryx/context/engine.py`, `memoryx/context/models.py`, `memoryx/hermes_bridge.py`, `tests/test_context_budget_contract.py`

### Description
Introduce `ContextBudgetPolicy` with per-layer quotas (policy/guard, project, session, long_term) and hard reserves for working/warnings/policy context. Add evidence-backed compression priority: high-evidence (E4) items are retained over low-evidence (E1) during truncation, with `final_score` as tiebreaker within the same evidence tier. Adds `budget_report` and `truncation_reason` observability.

### Acceptance Criteria
- [ ] 827 tests pass (full suite)
- [ ] ReleaseGate PASS, FK 0
- [ ] `ContextBudgetPolicy.from_max_token_budget()` backwards-compatible
- [ ] Hard reserve: working/warnings/policy never squeezed
- [ ] `_compress_priority_key` called in compression/truncation path
- [ ] E4 > E1, same evidence uses `final_score`, unknown evidence last
- [ ] Section order unchanged (policy > working > project > session > long_term)
- [ ] No `SemanticCompressionEngine` import
- [ ] Candidate/stale/superseded not injected

### Evidence
- 30 contract tests in `test_context_budget_contract.py`
- 827 full-suite pass (9 contract files)

---

## Issue #2: Repository batch hydration + per-request retrieval cache

- **Type**: `type:feature`
- **Priority**: `P1`
- **Labels**: `area:retrieval`, `area:storage`, `area:performance`
- **Scope**: `memoryx/storage/repository.py`, `memoryx/retrieval/engine.py`, `memoryx/retrieval/models.py`, `tests/test_retrieval_batch_hydration_contract.py`, `tests/test_retrieval_cache_contract.py`

### Description
Add `repository.batch_get_memories()` with parameterised `IN` query and chunking (batch_size=500) to replace O(N) per-ID hydration. Add per-request `hydration_cache` dict in `retrieve()` to avoid same-request re-hydration. Main path fills cache; fallback checks cache before batch hydration. Add trace counters: `batch_hydration_count`, `cache_hit_count`, `cache_miss_count`.

### Acceptance Criteria
- [ ] 827 tests pass (full suite)
- [ ] ReleaseGate PASS, FK 0
- [ ] `batch_get_memories` uses parameterised `IN` (no raw SQL)
- [ ] Chunking applies for IDs > batch_size
- [ ] Per-request cache — no global/repository cache, no `lru_cache`
- [ ] `cache_hit_count` / `cache_miss_count` observable
- [ ] `get_memory_count` = requested hydration IDs (24.6 semantic)
- [ ] Eligibility / scoring / ordering / dedup unchanged
- [ ] Candidate/stale/superseded still invisible

### Evidence
- 47 contract tests (25 batch + 22 cache)
- 827 full-suite pass

---

## Issue #3: Retrieval trace semantics + debug surface

- **Type**: `type:feature`
- **Priority**: `P2`
- **Labels**: `area:retrieval`, `area:rest`, `area:observability`
- **Scope**: `memoryx/api/app_factory.py`, `memoryx/hermes_provider.py`, `tests/test_retrieval_trace_semantics_contract.py`

### Description
Add `batch_hydration_enabled` and `per_request_cache_enabled` to `/ready retrieval_capabilities`. Add `retrieval_observability` summary to `usage` action. Add 17 trace semantics contract tests covering: explain=False/True, no raw content/metadata/DB path/secret in trace, capability flags present, query-level trace excluded from `/ready`.

### Acceptance Criteria
- [ ] 827 tests pass (full suite)
- [ ] ReleaseGate PASS, FK 0
- [ ] `/ready` has `batch_hydration_enabled`, `per_request_cache_enabled`
- [ ] `/ready` excludes query-level trace (no `query_plan_used`, `fallback_steps`)
- [ ] `usage` includes `retrieval_observability` summary
- [ ] Trace never contains raw content, metadata_json, DB path, or secrets

### Evidence
- 17 trace semantics contract tests
- 827 full-suite pass

---

## Issue #4: Codex OSS readiness: identity, security, docs, CI

- **Type**: `type:docs`, `type:security`, `type:integration`
- **Priority**: `P1`
- **Labels**: `area:docs`, `area:release`, `area:security`
- **Scope**: 24 files (README, pyproject, SECURITY, CITATION, CHANGELOG, docs/*, .github/*)

### Description
Align project identity from `lucky99/Mnemosyne-X/1.1.0` to `luckyl214/MemoryX/2.0.0`. Add `SECURITY_THREAT_MODEL.md`, `CODEX_USAGE_PLAN.md`, `RELEASE_CHECKLIST.md`, maintainer workflow docs, issue triage guide, and PR review guide. Add CodeQL Python + pip-audit CI security workflow (report-only). This is a metadata/docs/CI-only PR — no runtime changes.

### Acceptance Criteria
- [ ] 827 tests pass (full suite) — unchanged
- [ ] ReleaseGate PASS, FK 0
- [ ] P1 identity issues cleared: luckyl214/2.0.0/MemoryX, no placeholder email
- [ ] SECURITY.md covers 2.0.x
- [ ] SECURITY_THREAT_MODEL.md covers 6 assets, 6 surfaces, 11 threats
- [ ] CODEX_USAGE_PLAN.md explicitly restricts Codex to maintainer automation
- [ ] RELEASE_CHECKLIST.md covers 22 release gates
- [ ] security.yml: CodeQL + pip-audit, `continue-on-error: true`, no `pull_request_target`
- [ ] No API key, token, or secret in any file

### Evidence
- No test changes (metadata/docs only)
- 827 existing tests pass unchanged
- CodeQL + pip-audit workflow ready for CI execution
