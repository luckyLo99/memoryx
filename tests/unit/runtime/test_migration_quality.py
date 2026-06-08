from __future__ import annotations

from pathlib import Path


def test_migration_010_fixes_placeholder_index():
    """Verify migration 010 no longer has the placeholder index name."""
    path = Path("memoryx/storage/sql/migrations/010_cognitive_timeline_lessons.sql")
    text = path.read_text(encoding="utf-8")
    # The placeholder index name must not be present
    assert "idx_taYOUR_API_KEY_HERE" not in text, "Placeholder index name found, should have been fixed"
    # The correct index name must exist
    assert "idx_task_durations_entity_time" in text
    # Key lesson tables must exist
    assert "lesson_memories" in text
    assert "lesson_evidence" in text
