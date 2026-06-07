# AI-Assisted Development Governance

> Last updated: 2026-06-07
> Repository: `luckyl214/memoryx`

## Purpose

This document defines how AI-assisted development tools are used for MemoryX maintainer automation.
AI tools are never integrated into the MemoryX runtime and do not serve as a default retrieval,
memory, or context engine path.

## Approved Use Cases

### 1. Pull Request Review
- **Scope**: Python source files, contract tests, CI workflows
- **Guard**: Review output is advisory; merge requires human maintainer approval

### 2. Issue Triage
- **Scope**: GitHub Issues
- **Guard**: Classification is advisory; security issues escalated to private advisory

### 3. Regression Test Generation
- **Scope**: `tests/test_*_contract.py` files
- **Guard**: Generated tests must pass full test suite before commit

### 4. Release Validation
- **Scope**: Pre-release audit, diff analysis, readiness report
- **Guard**: Release decision requires human maintainer approval

### 5. Documentation Alignment
- **Scope**: `CHANGELOG.md`, `docs/`, `README.md`
- **Guard**: Content changes are advisory; human review required

### 6. Security Review
- **Scope**: `SECURITY.md`, `SECURITY_THREAT_MODEL.md`, `pyproject.toml`, auth boundaries
- **Guard**: Findings must be reviewed by a human maintainer

## Boundaries

| Boundary | Rule |
|----------|------|
| No runtime integration | AI tools are never called from MemoryX runtime |
| No default model path | MemoryX does not ship with any AI provider as default |
| No API key storage | Keys stored in environment variables only; never in repo |
| Human-in-the-loop | All outputs are advisory; human required for decisions |
| No silent execution | All AI-assisted workflows are explicitly triggered |

## API Credits Usage

| Activity | Estimated Usage | Frequency |
|----------|----------------|-----------|
| PR review | Medium (code analysis) | Per PR |
| Issue triage | Low (classification) | Per issue |
| Test generation | Medium (code generation) | Per batch |
| Release validation | High (full audit) | Per release |
