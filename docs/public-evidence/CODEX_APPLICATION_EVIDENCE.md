# Codex Application Evidence — MemoryX 2.0

> Repository: `luckyl214/memoryx`
> Program: [OpenAI Codex for Open Source](https://developers.openai.com/community/codex-for-oss)

## Application Signals

OpenAI Codex for Open Source covers: PR review, maintainer automation, release workflows, API credits, ChatGPT Pro with Codex, and case-by-case Codex Security. The following artifacts demonstrate active OSS maintenance suitable for application.

### 1. Active Maintenance — 857 commits, numbered batch system

- 24.4 → 24.9 batches completed on `feature/24.0-runtime-replay`
- Each batch has explicit scope, allow/forbid lists, test matrix, and pass criteria
- 32 commits in current feature branch, ready for PR transition

### 2. PR Review Readiness — 4 independent PRs

- PR1: Context budget + compression (2 commits, 4 files, 30 contract tests)
- PR2: Batch hydration + cache (2 commits, 4 files, 47 contract tests)
- PR3: Trace semantics (1 commit, 3 files, 17 contract tests)
- PR4: Codex readiness (4 commits, 24 files, metadata/docs only)

### 3. Test Discipline — 827 tests, 0 FK violations

- Contract test naming: `test_<module>_contract.py`
- Full suite runs as ReleaseGate on every PR/push
- `repo_guard.py` checks tag integrity, secret patterns, runtime path leaks
- `run_memoryx_release_gate.py` runs 8 gate checks before release

### 4. Release Workflows — ReleaseGate + RELEASE_CHECKLIST

- `memoryx-release-gate.yml`: PR + push gate (runs full test suite + ReleaseGate)
- `release.yml`: tag push trigger for versioned releases
- `RELEASE_CHECKLIST.md`: 22-step release gate
- `scripts/memoryx_patch_flow.sh`: patch flow with archive hygiene

### 5. Security Posture — threat model + CI scans

- `SECURITY.md`: vulnerability reporting, supported versions (2.0.x)
- `SECURITY_THREAT_MODEL.md`: 6 assets, 6 attack surfaces, 11 threats
- `.github/workflows/security.yml`: CodeQL Python + pip-audit (report-only)
- CodeQL advanced setup with `security-events: write` permissions
- No API keys, tokens, or secrets in repository

### 6. Maintainer Automation — Codex usage plan

- `CODEX_USAGE_PLAN.md`: 6 approved use cases (PR review, issue triage, test gen, release validation, docs, security review)
- `docs/MAINTAINER_WORKFLOW.md`: issue → repro → fix → review → ReleaseGate → docs → release
- `docs/ISSUE_TRIAGE_GUIDE.md`: 7 types, 3 priorities, 8 areas
- `docs/PR_REVIEW_GUIDE.md`: scope, test, security, docs/pitfalls checklists
- Codex/GPT explicitly restricted to maintainer assistant role; never runtime default

### 7. Repository Health — CODEOWNERS, templates, contributing

- `.github/CODEOWNERS`
- `.github/pull_request_template.md` with secret scan checklist
- `.github/ISSUE_TEMPLATE/` (bug report + feature request)
- `CONTRIBUTING.md`
- `dependabot.yml`

## Usage Plan for API Credits

If awarded, API credits will be used for:

| Activity | Tool | Frequency |
|----------|------|-----------|
| PR review | Codex / GPT | Per PR |
| Issue triage | Codex / GPT | Per issue |
| Regression test generation | Codex / GPT | Per batch |
| Release validation | Hermes agent + manual | Per release |
| Security scan review | CodeQL + manual | Per PR/push/weekly |

No credits will be used for MemoryX runtime (retrieval, context assembly, memory ingestion, REST endpoints).

## Evidence Summary

| Signal | Artifact | Status |
|--------|----------|--------|
| Active maintenance | 857 commits, numbered batches 24.4–24.9 | ✅ |
| Contract test discipline | 827 tests, 0 FK violations | ✅ |
| Release workflows | ReleaseGate + RELEASE_CHECKLIST + patch flow | ✅ |
| Security posture | SECURITY.md + threat model + CodeQL + pip-audit | ✅ |
| Maintainer automation | CODEX_USAGE_PLAN + workflow docs | ✅ |
| Repository health | CODEOWNERS, templates, CONTRIBUTING, dependabot | ✅ |
| No secrets | Zero API key/token/secret in repo | ✅ |
