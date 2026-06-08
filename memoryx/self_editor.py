"""DEPRECATED — moved to memoryx.validation.self_editor."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.self_editor is deprecated; use memoryx.validation.self_editor", DeprecationWarning, stacklevel=2)
from memoryx.validation.self_editor import SelfEditor, SelfEditRequest, SelfEditPreview, SelfEditResult
__all__ = ["SelfEditor", "SelfEditRequest", "SelfEditPreview", "SelfEditResult"]
