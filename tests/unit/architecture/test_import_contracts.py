"""Architecture contract tests for MemoryX."""
from __future__ import annotations

import os

# G1: No new imports from memoryx.core (except allowed shims)
CORE_IMPORT_PATTERN = "from memoryx.core"
ALLOWED_CORE_IMPORTERS = frozenset({
    "memoryx/retrieval/__init__.py",
    "memoryx/mcp/_compat.py",
    "memoryx/core/__init__.py",
    "memoryx/core/hermes_adapter.py",
    "memoryx/core/hybrid_retriever.py",
    "memoryx/core/kernel.py",
    "memoryx/core/retriever.py",
    "memoryx/core/schema.py",
})


def _memoryx_py_files():
    for dp, _, fs in os.walk("memoryx"):
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(dp, f)


def test_g1_no_new_core_imports():
    """No file outside the allowed list imports from memoryx.core."""
    bad = []
    for fp in _memoryx_py_files():
        rel = fp.replace("\\", "/")
        if rel in ALLOWED_CORE_IMPORTERS:
            continue
        with open(fp, "r", encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if "from memoryx.core" in line and "# legacy" not in line:
                    bad.append(f"{rel}:{i}: {line.strip()}")
    assert not bad, "New core imports detected:\n" + "\n".join(bad[:10])


# G2: MCP data directory isolation
MCP_SERVER_FILES = {
    "memoryx/mcp/server.py",
    "memoryx/mcp/adapter.py",
    "memoryx/mcp/observed.py",
}


def test_g2_mcp_no_real_data_paths():
    """MCP files must not hardcode real user data paths."""
    suspicious = [".hermes/memoryx", "memoryx.db", "USER.md", "MEMORY.md"]
    for fp in MCP_SERVER_FILES:
        if not os.path.exists(fp):
            continue
        rel = fp.replace("\\", "/")
        with open(fp, "r", encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                for pat in suspicious:
                    if pat in line and "test" not in line.lower() and "example" not in line.lower():
                        assert False, f"{rel}:{i}: real path {pat} in: {line.strip()}"


# G3: Hermes write path uses MemoryCandidateService
def test_g3_hermes_write_uses_candidate_service():
    provider_path = "memoryx/hermes/provider.py"
    with open(provider_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "MemoryCandidateService" in content, f"{provider_path} must use MemoryCandidateService"
    assert "submit_candidate" in content or "promote_to_committed" in content or "_handle_add" in content, (
        f"{provider_path} must use candidate pipeline"
    )


# G4: Public API surface
EXPECTED_PUBLIC_EXPORTS = frozenset({
    "MemoryQueryAPI", "MemoryRepository", "MemoryRecord",
    "HermesIntegrationRuntime", "HermesCompatibilityAdapter",
    "MCPServer",
    "HybridRetrievalEngine", "RetrievalIntent", "RetrievalResult",
    "ScoreBreakdown", "ConfidenceLabel",
    "MemoryBank", "ReflectEngine", "PersonaEngine",
    "SceneEngine", "SelfEditor", "SymbolicIndex",
})


def test_g4_public_api_surface():
    import memoryx
    missing = [name for name in EXPECTED_PUBLIC_EXPORTS if not hasattr(memoryx, name)]
    assert not missing, f"Missing public API exports: {missing}"
