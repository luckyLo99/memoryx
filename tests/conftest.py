"""Pytest configuration for MemoryX test suite."""
import os

# Use project-local temp directory to avoid Windows permission issues
_base = os.path.dirname(__file__)
os.environ.setdefault("PYTEST_TMPDIR", os.path.join(_base, "..", ".pytest_tmp"))
