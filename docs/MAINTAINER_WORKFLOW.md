# Maintainer Workflow — MemoryX 2.0

> For contributors and maintainers. See also: `CODEX_USAGE_PLAN.md`, `SECURITY_THREAT_MODEL.md`, `RELEASE_CHECKLIST.md`.

## Core Principle

**No blind agent coding.** Every change has a named batch with explicit scope, allow list, forbid list, test matrix, and pass criteria. Codex/GPT assists but does not autonomously commit, tag, or release.

## Workflow

```
Issue → Repro Test → Scoped Fix → Review → ReleaseGate → Changelog/Docs → Release
```

### 1. Issue Triage
- Classify: `type:bug/security/docs/test/performance/integration/packaging`, `priority:p0/p1/p2`
- Label: `area:hermes/retrieval/storage/privacy/release`
- Add `needs-repro` if no reproduction test exists
- See `docs/ISSUE_TRIAGE_GUIDE.md` for full guide

### 2. Minimal Reproduction Test
- Write a failing test in `tests/` that captures the exact bug or regression
- Test must fail on current HEAD before the fix is applied
- Follow contract test naming: `test_<module>_contract.py`

### 3. Scoped Fix
- Define batch scope: allowed files, forbidden files, test matrix
- Follow the numbered batch system (e.g. `24.9-D`)
- Prefer minimal patches over large refactors
- Never mix docs/hygiene changes with core logic fixes
- See `docs/PR_REVIEW_GUIDE.md` for review criteria

### 4. Code Review
- Review by a human maintainer (not automated merge)
- Codex may provide advisory review in parallel
- Verify: scope discipline, test coverage, no forbidden file changes, no unrelated refactor

### 5. Release Validation
- Run full test suite: `python -m pytest -q`
- Run repo guard: `python scripts/memoryx_repo_guard.py`
- Run release gate: `python scripts/run_memoryx_release_gate.py`
- All must PASS with FK 0 violations
- See `RELEASE_CHECKLIST.md` for complete checklist

### 6. Changelog & Docs
- Update `CHANGELOG.md` with the new version section
- Update any affected docs
- Verify version alignment in `pyproject.toml` and API endpoints

### 7. Release
- Create annotated tag
- Generate release archive with checksum
- Draft GitHub release notes
- Do NOT force push or move existing tags

## Codex/GPT Role

Codex/GPT is used as a **maintainer assistant** — not as a runtime engine:

| Activity | Codex Role | Human Role |
|----------|-----------|------------|
| PR review | Advisory analysis | Final approval |
| Issue triage | Label suggestion | Final classification |
| Test generation | Contract test draft | Review and integration |
| Release validation | Audit report | Go/no-go decision |
| Docs/changelog | Content validation | Final edit |

Codex/GPT is **never** called from MemoryX runtime (retrieval, context assembly, memory ingestion, REST endpoints).

## Evidence for Codex OSS Application

The following artifacts demonstrate OSS maintainer activity suitable for Codex OSS / Codex Security review:

- Numbered batch system with explicit scope gates
- Contract test discipline (800+ tests)
- ReleaseGate + repo_guard automation
- Security threat model (`SECURITY_THREAT_MODEL.md`)
- Codex usage plan (`CODEX_USAGE_PLAN.md`)
- Release checklist (`RELEASE_CHECKLIST.md`)
- PR/issue templates and maintainer guides
