# Issue Triage Guide — MemoryX 2.0

> Applies to: `luckyl214/memoryx` GitHub Issues. Maintainers only for severity classification.

## Quick Triage Flow

```
New Issue → Classify Type → Classify Priority → Assign Area → needs-repro? → Acceptance Criteria
```

## Type Classification

| Type | Description | Example |
|------|-------------|---------|
| `type:bug` | Unexpected behavior, regression, crash | "`retrieve()` returns empty when DB has 500+ records" |
| `type:security` | Vulnerability, auth bypass, data leak | "candidate memory visible without `include_candidates=True`" |
| `type:docs` | Missing, incorrect, or outdated documentation | "README still references Mnemosyne-X" |
| `type:test` | Missing test coverage, flaky test | "No contract test for session scope" |
| `type:performance` | Slow queries, memory leaks, high latency | "10k memories → `list_memories_filtered` 15s" |
| `type:integration` | Hermes, REST, MCP, plugin boundary issues | "Hermes provider drops `include_lessons=False`" |
| `type:packaging` | PyPI, pip install, dependency, build issues | "Cannot install on Python 3.13" |

## Priority Classification

| Priority | Criteria | Response |
|----------|----------|----------|
| `P0` | Data loss, auth bypass, FK violations, runtime crash, release blocker | Immediate attention |
| `P1` | Wrong behavior in core path, regression from last release, security policy gap | Next batch |
| `P2` | Performance degradation, missing docs, missing observability | Scheduled batch |
| `P3` | Cosmetic, naming, non-functional improvement | Backlog |

## Area Labels

| Label | Scope |
|-------|-------|
| `area:retrieval` | `memoryx/retrieval/` — query, scoring, dedup, hydration, cache |
| `area:storage` | `memoryx/storage/` — repository, SQLite, migrations, backup |
| `area:context` | `memoryx/context/` — budget, assembly, annotation, compression |
| `area:hermes` | `memoryx/hermes_provider.py`, `memoryx/hermes_bridge.py`, MCP |
| `area:rest` | `memoryx/api/` — REST endpoints, auth, rate-limiting |
| `area:privacy` | PII filter, secret scan, trace safety, prompt injection |
| `area:release` | `scripts/`, ReleaseGate, repo_guard, archive hygiene |
| `area:docs` | `README.md`, `docs/`, CHANGELOG, comments |

## Reproduction Flag

Add `needs-repro` if:

- The issue describes unexpected behavior but provides no test case
- The scenario is complex enough to need a dedicated contract test
- The fix should be gated by a regression test

Remove `needs-repro` when a failing test is added.

## Acceptance Criteria

Every issue ready for fixing should have:

1. **Clear title** describing the problem (not "Fix stuff")
2. **Steps to reproduce** (or `needs-repro` label)
3. **Expected behavior** vs **actual behavior**
4. **Affected components** (area label)
5. **Severity** (priority label)

## Security Issues

Security issues follow a different path:

- Do NOT open public issues for security vulnerabilities
- Use GitHub Security Advisories (see `SECURITY.md`)
- Label as `type:security` only after the advisory is published or after a fix is publicly available
- Codex may assist in security review but never autonomously discloses

## Automation

Codex/GPT may assist in triage by suggesting labels and priorities.
All classifications are advisory — final decision by human maintainer.
