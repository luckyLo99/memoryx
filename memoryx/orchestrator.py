"""DEPRECATED — moved to memoryx.runtime.orchestrator."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.orchestrator is deprecated; use memoryx.runtime.orchestrator", DeprecationWarning, stacklevel=2)
from memoryx.runtime.orchestrator import ModuleEntry, ModuleRegistry, ModuleStatus, SystemOrchestrator  # noqa: E402
__all__ = ["ModuleEntry", "ModuleRegistry", "ModuleStatus", "SystemOrchestrator"]
