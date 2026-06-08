# Phase 14 E2E Runtime

Phase 14 turns the earlier MCP and retrieval observability limitations into executable e2e tests.

## Local e2e

This path requires no optional MCP SDK:

```bash
python scripts/verify_phase14_e2e.py
python scripts/run_phase14_e2e.py --db ./memoryx_phase14_e2e.db --artifacts ./phase14_artifacts
```

## Artifacts

The e2e run generates:

* `e2e_diagnostics.zip`
* `e2e_retrieval_debug.json`
* `e2e_profile.json`
* `e2e_profile.md`
* `e2e_quality_report.json`
* `e2e_quality_report.md`
* `e2e_audit_export.json`
* `e2e_metrics.json`

## Pytest

```bash
pytest -q tests/e2e/test_retrieval_observability_e2e.py tests/e2e/test_mcp_observability_e2e.py
pytest -rs tests/e2e/test_mcp_observability_e2e.py
```
