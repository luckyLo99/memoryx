# Security Threat Model — MemoryX 2.0

> Last updated: 2026-05-31
> Scope: MemoryX 2.0.x stable (`feature/24.0-runtime-replay`)

## Assets

| Asset | Location | Sensitivity |
|-------|----------|-------------|
| Long-term memories (FACT, PREFERENCE, PROJECT, LESSON, etc.) | SQLite `memories` table | High — persistent user/agent knowledge |
| Session summaries & working context | SQLite `session_summaries`, `memory_versions` | Medium — session-scoped |
| Vector embeddings | LanceDB vector index | Medium — similarity-search index |
| API keys & secrets | Environment variables, `.env` | Critical — never stored in DB or repo |
| Release artifacts & checksums | GitHub Releases, `dist/` | Medium — supply-chain integrity |
| REST API endpoints | FastAPI routes (`/v1/memories`, `/ready`, `/health`) | Medium — authentication-gated |
| Hermes provider integration | `hermes_provider.py`, hooks | High — passes memory to LLM context |

## Attack Surfaces

### 1. REST API (FastAPI)
- **Entry points**: `/v1/memories`, `/ready`, `/health`, `/metrics`, search, export
- **Auth**: API key via `verify_api_key` dependency (constant-time comparison with `secrets.compare_digest`)
- **Threats**: auth bypass, mass read/exfiltration, unauthenticated write of poisoned memories

### 2. Hermes Provider / MCP Integration
- **Entry points**: `hermes_provider.py` memory tool (`add`, `read`, `replace`, `remove`, `usage`, `export`)
- **Threats**: prompt injection persistence via `add` action, context poisoning via `read` returning crafted memories, tool-call injection

### 3. Memory Ingestion (Candidate Pipeline)
- **Entry points**: `store_memory`, `create_candidate`, `verify_candidate`, `commit_candidate`
- **Threats**: PII/secret ingestion without filtering, E0 model-inference memories bypassing evidence gates, candidate visibility bypass in retrieval

### 4. Retrieval & Context Assembly
- **Entry points**: `HybridRetrievalEngine.retrieve()`, `ContextAssemblyEngine.assemble()`
- **Threats**: retrieval-to-context injection (crafted vectors/keywords returning poisoned memories), session isolation bypass, candidate/rejected memories leaking into context

### 5. Storage & Migration
- **Entry points**: SQLite WAL, FTS5 index, LanceDB, migration scripts
- **Threats**: SQLite pragma abuse (foreign_keys disabled), INSERT OR IGNORE masking FK errors, unsafe migration scripts

### 6. Release Pipeline
- **Entry points**: `scripts/memoryx_patch_flow.sh`, `scripts/run_memoryx_release_gate.py`, GitHub Actions
- **Threats**: unsigned release artifacts, checksum tampering, dirty worktree commits bypassing ReleaseGate

## Threats & Mitigations

| Threat | Severity | Existing Mitigation | Status |
|--------|----------|-------------------|--------|
| Prompt injection persistence | High | Candidate gate (E0 → E2+ required for commit), evidence-level gating | ✅ Mitigated |
| PII / secret ingestion | Medium | `pii_filter.py` detects emails, phones, credit cards, API keys on write | ✅ Mitigated |
| Auth bypass | High | `secrets.compare_digest` for API key comparison | ✅ Mitigated |
| Retrieval-to-context injection | Medium | Candidate visibility filter, session scope hardening, include_lessons semantics | ✅ Mitigated |
| Candidate / stale memory leaking into context | Medium | `_is_visible_memory_for_retrieval` excludes candidate/rejected/stale/superseded | ✅ Mitigated |
| Session isolation bypass | Medium | `session_only` flag, `_is_session_scoped_memory`, `_session_matches` | ✅ Mitigated |
| FK violations / schema drift | High | `PRAGMA foreign_keys=ON`, ReleaseGate FK check, repo_guard | ✅ Mitigated |
| Dirty release artifacts | High | ReleaseGate (`run_memoryx_release_gate.py`), `repo_guard`, commit hygiene rules | ✅ Mitigated |
| Dependency / supply-chain risk | Medium | `pip-audit` integration point (CI scan pending — 24.9-D) | ⚠️ Pending |
| Memory poisoning via bulk ingestion | Low | Batch hydration with parameterised queries, no raw SQL concatenation | ✅ Mitigated |
| Cross-session contamination | Low | Session ID scoping in retrieval, `session_only` semantics | ✅ Mitigated |

## Known Gaps

| Gap | Severity | Plan |
|-----|----------|------|
| No automated CI security scan | P2 | Target 24.9-D: CodeQL / Bandit / pip-audit |
| No runtime taint tracking for model-inferred content | P3 | Design review — may exceed scope of available resources |
| REST rate-limiting per key | P3 | Basic rate-limit exists; not per-key granular |
| LanceDB access control | P3 | File-system permission only; no internal ACL |

## Review & Update Policy

- This document is reviewed with each major release batch.
- Security review scope: taint flow, auth boundary, poisoning vectors, dependency risk, release artifact integrity.
- Report vulnerabilities via GitHub Security Advisories (see `SECURITY.md`).
