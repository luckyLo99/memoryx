from __future__ import annotations

from pathlib import Path


class DiagnosticsBundle:
    """Collect and package diagnostics for a MemoryX instance.

    This is a stub — P0/P1 placeholder for full implementation.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def build(self, output_path: str | Path, include_profile: bool = True) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "DiagnosticsBundle stub — no diagnostics collected yet.\n"
            f"db_path={self.db_path}\n"
            f"include_profile={include_profile}\n"
        )
        return output


class ProfileRunner:
    """Run a profile of retrieval performance.

    This is a stub — P0/P1 placeholder for full implementation.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def run(self, records: int = 20, queries: int = 3, **kwargs: object) -> None:
        pass


class RetrievalDebugger:
    """Debug a specific retrieval query.

    This is a stub — P0/P1 placeholder for full implementation.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def debug_query(self, query: str, limit: int = 10) -> dict:
        return {"query": query, "limit": limit, "results": []}