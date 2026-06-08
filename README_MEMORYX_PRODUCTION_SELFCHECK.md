# MemoryX Production Self-Check Suite

This is a non-invasive audit suite for MemoryX. It does not overwrite or patch runtime code.

## Install

Copy these files into the MemoryX repository root:

```bash
cp -r tools tests /path/to/memoryx/
cd /path/to/memoryx
```

## Fast self-check

```bash
python tools/memoryx_system_selfcheck.py --root .
```

## Full self-check

```bash
python tools/memoryx_system_selfcheck.py \
  --root . \
  --run-pytest \
  --run-pip-check \
  --run-ruff \
  --run-bandit \
  --timeout 300
```

## Pytest contract mode

```bash
pytest -q tests/system/test_memoryx_system_contracts.py
```

## Reports

The script writes:

- `system_selfcheck_report.json`
- `system_selfcheck_report.md`

The JSON report includes an `summary.agent_instruction` field designed for an autonomous repair agent.
