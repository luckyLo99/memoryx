"""Tests for ConflictResolver - antonym false positive fix"""
from __future__ import annotations

from datetime import datetime

import pytest

from memoryx.extraction import ExtractionMemory
from memoryx.validation.conflict_resolver import ConflictResolver


def create_memory(content: str, reasoning: str = "") -> ExtractionMemory:
    """Create test memory"""
    return ExtractionMemory(
        content=content,
        reasoning=reasoning,
        timestamp=datetime.now(),
        metadata={}
    )


def test_antonym_false_positive_dislike():
    """Test that "dislike" is not falsely matched as "like" when checking antonyms"""
    resolver = ConflictResolver()
    
    # Both memories have "dislike" - should NOT detect conflict
    memory1 = create_memory("I dislike pizza")
    memory2 = create_memory("I dislike vegetables")
    
    result = resolver.resolve(memory1, [memory2])
    assert result is None, "Should not detect conflict between two 'dislike' statements"


def test_antonym_true_positive_like_vs_dislike():
    """Test that "like" vs "dislike" correctly detects conflict"""
    resolver = ConflictResolver()
    
    memory1 = create_memory("I like pizza")
    memory2 = create_memory("I dislike pizza")
    
    result = resolver.resolve(memory1, [memory2])
    assert result is not None, "Should detect conflict between 'like' and 'dislike'"
    assert "conflict" in result.reason.lower()


def test_word_boundary_likely_not_like():
    """Test that "likely" is not matched as "like" (word boundary test)"""
    resolver = ConflictResolver()
    
    memory1 = create_memory("It's likely to rain")
    memory2 = create_memory("I dislike rain")
    
    result = resolver.resolve(memory1, [memory2])
    assert result is None, "Should not match 'likely' as 'like'"


def test_word_boundary_hate_vs_love():
    """Test that "hate" vs "love" correctly detects conflict"""
    resolver = ConflictResolver()
    
    memory1 = create_memory("I hate Mondays")
    memory2 = create_memory("I love Mondays")
    
    result = resolver.resolve(memory1, [memory2])
    assert result is not None, "Should detect conflict between 'hate' and 'love'"


def test_negation_marker_not_like():
    """Test that "not like" vs "like" correctly detects conflict"""
    resolver = ConflictResolver()
    
    memory1 = create_memory("I like coffee")
    memory2 = create_memory("I do not like coffee")
    
    result = resolver.resolve(memory1, [memory2])
    assert result is not None, "Should detect conflict between 'like' and 'not like'"


def test_multiple_antonym_pairs():
    """Test that various antonym pairs work correctly"""
    resolver = ConflictResolver()
    
    test_cases = [
        # (text1, text2, should_conflict)
        ("I agree", "I disagree", True),
        ("I prefer tea", "I avoid tea", True),
        ("This is good", "This is bad", True),
        ("I'm happy", "I'm sad", True),
        ("I enjoy this", "I dislike this", True),
        ("I'm satisfied", "I'm disappointed", True),
        # Same sentiment - no conflict
        ("I agree", "I also agree", False),
        ("I prefer tea", "I like tea", False),
        ("This is good", "This is great", False),
    ]
    
    for text1, text2, should_conflict in test_cases:
        mem1 = create_memory(text1)
        mem2 = create_memory(text2)
        result = resolver.resolve(mem1, [mem2])
        actual_conflict = result is not None
        assert actual_conflict == should_conflict, \
            f"Failed for '{text1}' vs '{text2}': expected conflict={should_conflict}, got={actual_conflict}"


def test_positive_negative_markers_with_word_boundaries():
    """Test that positive/negative marker detection uses word boundaries"""
    resolver = ConflictResolver()
    
    # "notable" should not be matched as "not"
    memory1 = create_memory("This is notable")
    memory2 = create_memory("This is good")
    
    result = resolver.resolve(memory1, [memory2])
    assert result is None, "Should not match 'notable' as containing 'not'"


def test_compound_words_not_matched():
    """Test that compound words are not split into markers"""
    resolver = ConflictResolver()
    
    test_cases = [
        ("dislike", "dislike", False),  # Same word - no conflict
        ("hateful", "lovely", False),   # Compound forms - no direct conflict
        ("liking", "disliking", True),  # Gerund forms - should conflict
    ]
    
    for text1, text2, should_conflict in test_cases:
        mem1 = create_memory(text1)
        mem2 = create_memory(text2)
        result = resolver.resolve(mem1, [mem2])
        actual_conflict = result is not None
        assert actual_conflict == should_conflict, \
            f"Failed for '{text1}' vs '{text2}': expected conflict={should_conflict}, got={actual_conflict}"
