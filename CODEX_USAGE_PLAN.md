# Codex Usage Plan — MemoryX 2.0

> Last updated: 2026-05-31
> Program: [OpenAI Codex for Open Source](https://developers.openai.com/community/codex-for-oss)
> Repository: `luckyl214/memoryx`

## Purpose

This document describes how OpenAI Codex (and associated GPT models via API credits) will be used for **OSS maintainer automation** in the MemoryX project. Codex/GPT is **not integrated into MemoryX runtime** and does not serve as a default retrieval, memory, or context engine path.

## Approved Use Cases

### 1. Pull Request Review
- **What**: Codex reviews incoming PRs for code quality, contract regression, forbidden patterns (e.g. schema changes, FK violations, runtime path edits)
- **Scope**: Python source files, contract tests, CI workflows
- **Guard**: Review output is advisory only; merge requires human maintainer approval + ReleaseGate pass

### 2. Issue Triage
- **What**: Codex classifies new issues (bug / feature / security / question) and suggests labels
- **Scope**: GitHub Issues
- **Guard**: Classification is advisory only; security-sensitive issues are escalated to private advisory

### 3. Regression Test Generation
- **What**: Codex generates contract tests for new batch scopes based on batch instructions and audit findings
- **Scope**: `tests/test_*_contract.py` files
- **Guard**: Generated tests must pass the full test suite before commit; never skip or xfail

### 4. Release Validation
- **What**: Codex runs pre-release audit (repo_guard, ReleaseGate, diff analysis) and produces a structured readiness report
- **Scope**: `scripts/run_memoryx_release_gate.py`, `scripts/memoryx_repo_guard.py`
- **Guard**: Release decision requires human maintainer approval

### 5. Documentation / Changelog Alignment
- **What**: Codex validates that PR descriptions, CHANGELOG entries, and docs match the actual code changes
- **Scope**: `CHANGELOG.md`, `docs/`, `README.md`
- **Guard**: Content changes are advisory; human review required before merge

### 6. Security-Sensitive Review
- **What**: Codex auditor reviews `SECURITY_THREAT_MODEL.md`, dependency changes, and auth boundary modifications
- **Scope**: Security-critical files (`SECURITY.md`, `SECURITY_THREAT_MODEL.md`, `pyproject.toml`, `memoryx/api/`)
- **Guard**: Findings are advisory; must be reviewed by a human maintainer

## Hard Boundaries

| Boundary | Rule |
|----------|------|
| **No runtime integration** | Codex/GPT is never called from MemoryX runtime (retrieval, context assembly, memory ingestion, REST endpoints) |
| **No default model path** | MemoryX does not ship with a Codex/GPT provider as a default |
| **No API key storage** | API keys for Codex/OAI are stored in environment variables or Hermes config; never in the MemoryX repo |
| **Human-in-the-loop** | All maintainer automation output is advisory; final decisions require human maintainer approval |
| **No silent execution** | Codex-assisted workflows are always triggered explicitly (via Hermes agent or manual invocation), never as background automation |

## API Credits Usage

| Activity | Estimated Usage | Frequency |
|----------|----------------|-----------|
| PR review | Medium (code analysis) | Per PR |
| Issue triage | Low (classification) | Per issue |
| Test generation | Medium-High (code synthesis) | Per batch |
| Release validation | Low (audit report) | Per release |
| Docs/changelog | Low (text validation) | Per PR |

API credits are provided through the OpenAI Codex for Open Source program and are used exclusively for the approved use cases above.

## Review & Update Policy

- This plan is reviewed with each major release cycle.
- Codex Security review scope may include taint flow analysis, auth boundary review, and dependency risk assessment.
- Updates to this plan require human maintainer approval.
