# PR Review Guide — MemoryX 2.0

> For reviewers and self-review. See also: `docs/MAINTAINER_WORKFLOW.md`, `RELEASE_CHECKLIST.md`.

## Review Checklist

### Scope Discipline
- [ ] Modified files match the batch's allowed file list
- [ ] No forbidden files touched (runtime, schema, migration, retrieval scoring, FTS, context budget, provider/bridge unless explicitly allowed)
- [ ] No unrelated refactors mixed into the batch
- [ ] No docs/hygiene changes mixed with core logic fixes (separate batches)

### Test Evidence
- [ ] Targeted contract tests pass
- [ ] Related tests pass
- [ ] Full test suite passes (`python -m pytest -q`)
- [ ] No skipped/xfailed tests used to clear failures
- [ ] New contract tests cover the batch's required assertions

### Security
- [ ] No API key / token / secret in diff
- [ ] No raw SQL concatenation (always parameterised)
- [ ] No `INSERT OR IGNORE` masking FK errors
- [ ] No `foreign_keys = OFF`
- [ ] No hardcoded paths (especially `/home/lucky/` or private paths)
- [ ] PII filter unchanged (or changes reviewed separately)
- [ ] Candidate / stale / superseded visibility unchanged (or changes explicitly gated)

### Gates
- [ ] `python scripts/memoryx_repo_guard.py` — PASS
- [ ] `python scripts/run_memoryx_release_gate.py` — OVERALL: PASS
- [ ] FK 0 violations

### Docs / Changelog
- [ ] `CHANGELOG.md` updated if this is a release batch
- [ ] `SECURITY.md` supported versions current
- [ ] `RELEASE_CHECKLIST.md` reviewed for release batches
- [ ] README / docs links point to correct repo

### Version
- [ ] `pyproject.toml` version matches intended release (if applicable)
- [ ] API live/health endpoints version aligned

## Codex/GPT in PR Review

Codex may provide advisory PR review but:

- **Review is advisory only** — human maintainer makes the final decision
- **Never autonomous merge** — all merges require human approval
- **Security-sensitive changes** must be reviewed by a human, not delegated to Codex

## Common Pitfalls

| Pitfall | Detection |
|---------|-----------|
| Scope creep | `git diff --name-only` has files not in allowed list |
| Skipped/xfailed to clear gates | `grep xfail` in test diff |
| Mixed refactor | Logic change + variable rename in same diff |
| Missing test | New code path without contract test |
| Dirty worktree | `git status --short` not empty before commit |
| Tag move / force push | Protected tags changed (detected by repo_guard) |
