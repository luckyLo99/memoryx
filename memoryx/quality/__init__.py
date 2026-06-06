"""Quality evaluation stubs for MemoryX e2e testing."""


class QualityEvaluator:
    """Stub for e2e quality evaluation."""

    def evaluate(self, *args, **kwargs) -> dict:
        return {}


def load_golden_cases(path: str) -> list[dict]:
    return []


def write_quality_reports(results: list[dict], output_dir: str) -> None:
    pass