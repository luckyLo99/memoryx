# Release Checklist — MemoryX 2.0

> Version: 2.0.x | Branch: `feature/24.0-runtime-replay`
> Use this checklist before every release (patch `v2.0.x` or feature `v2.1.x`).

## Pre-Release Gates

| Step | Command / Check | Required |
|------|----------------|----------|
| 1. Clean worktree | `git status --short` must be empty | ✅ |
| 2. Protected tags intact | `git tag -l 'v2.0.0*'` shows v2.0.0, v2.0.0-rc.1, v2.0.0-rc.2 | ✅ |
| 3. Targeted tests | `python -m pytest -q tests/<batch-test>.py` | ✅ |
| 4. Related tests | Batch-specific related test files | ✅ |
| 5. Full test suite | `python -m pytest -q` — all pass, no xfail beyond known | ✅ |
| 6. Repo guard | `python scripts/memoryx_repo_guard.py` — PASS | ✅ |
| 7. Release gate | `python scripts/run_memoryx_release_gate.py` — OVERALL: PASS | ✅ |
| 8. FK violations | ReleaseGate `foreign_key_check: pass` → 0 violations | ✅ |
| 9. Secret scan | `repo_guard` + `release-check.py` — no API key / token / secret in diff | ✅ |

## Metadata & Docs

| Step | Check | Required |
|------|-------|----------|
| 10. Version alignment | `pyproject.toml` version matches tag, `app_factory.py` live/health version matches | ✅ |
| 11. CHANGELOG | New version section exists with accurate date and summary | ✅ |
| 12. SECURITY.md | Supported versions table covers current release line | ✅ |
| 13. CITATION.cff | Version and date match release | ✅ |
| 14. README / docs links | Point to correct repo owner (`luckyl214/memoryx`) | ✅ |
| 15. Release notes | Drafted in GitHub Releases, no dirty-worktree evidence | ✅ |

## Archive & Distribution

| Step | Check | Required |
|------|-------|----------|
| 16. Archive hygiene | No private paths, `.env` files, or runtime data in release archive | ✅ |
| 17. Checksum verification | Archive checksum available and verified | ✅ |
| 18. Tag immutability | No tag move, no force push to release tags | ✅ |
| 19. Package metadata | `pyproject.toml` classifiers, keywords, license correct | ✅ |

## Safety

| Step | Check | Required |
|------|-------|----------|
| 20. No API key / secret | Grep for `sk-`, `OPENAI_API_KEY`, `DEEPSEEK`, tokens — zero hits | ✅ |
| 21. No runtime path leak | No hardcoded `/home/lucky/` or `/home/user/` paths | ✅ |
| 22. Dependencies | `pip-audit` or equivalent scan (CI scan planned in 24.9-E) | ⏳ |

## Sign-Off

- [ ] All gates PASS
- [ ] FK 0 violations
- [ ] CHANGELOG & docs aligned
- [ ] Security policy current
- [ ] Release notes ready
- [ ] Maintainer approval

**Do not release if any required gate fails.**
