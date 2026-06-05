# Supply Chain

Phase 15 adds release candidate supply-chain artifacts.

## Artifacts

* wheel
* sdist
* release manifest
* dist manifest
* SHA256 checksums
* optional SLSA provenance workflow

## Verification

```bash
python scripts/verify_phase15_release_candidate.py
python -m memoryx.release.cli verify-dist
```

## Provenance

The SLSA workflow is optional and manual. It is prepared so maintainers can attach provenance to release artifacts.
