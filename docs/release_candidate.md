# Release Candidate

Phase 15 validates MemoryX release candidate readiness.

## Local verification

```bash
python scripts/verify_phase15_release_candidate.py
python scripts/build_release_candidate.py
```

## Build

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```

## Manifest

```bash
python -m memoryx.release.cli manifest
```

Generated files:

* `release_manifest.json`
* `dist_manifest.json`
