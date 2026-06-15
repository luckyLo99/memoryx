"""DEPRECATED — moved to memoryx.episodic.scene."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.scene is deprecated; use memoryx.episodic.scene", DeprecationWarning, stacklevel=2)
from memoryx.episodic.scene import Scene, SceneEngine  # noqa: E402
__all__ = ["Scene", "SceneEngine"]
