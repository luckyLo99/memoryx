# PR Transition Plan — MemoryX 2.0

> Baseline: `5603874` on `feature/24.0-runtime-replay`
> 9 commits, 35 files, 827 tests, 0 FK violations
> Target: `memoryx-2-kernel` → `main`

## Strategy

Split 9 commits into **4 reviewable PRs**. Each PR has:
- A linked GitHub Issue with acceptance criteria
- A self-contained scope (no cross-PR dependency on review order)
- Evidence: test count, gate results, no forbidden file changes

## PR Sequence

| Order | PR Title | Commits | Files | Tests | Issue |
|-------|----------|---------|-------|-------|-------|
| 1 | Context budget quota + deterministic compression | 2 | 4 | 827 | #1 |
| 2 | Repository batch hydration + per-request retrieval cache | 2 | 4 | 827 | #2 |
| 3 | Retrieval trace semantics + debug surface | 1 | 3 | 827 | #3 |
| 4 | Codex OSS readiness: identity, security, docs, CI | 4 | 24 | 827 | #4 |

## Notes

- PRs 1–3 are runtime changes (retrieval/context) with contract tests.
- PR 4 is metadata/docs/CI only — no runtime changes.
- All 4 PRs pass the full 827-test suite independently.
- No schema/migration changes in any PR.
- No `pull_request_target`, no secrets, no release/tag/push in any workflow.

## Target Branch

All PRs target `memoryx-2-kernel` first. After review and merge, `memoryx-2-kernel` is merged to `main` in a separate release preparation step.

## Blocked Actions

- Do NOT push/tag/release until 24.10 final gate.
- Do NOT open actual GitHub PRs until planning is approved.
