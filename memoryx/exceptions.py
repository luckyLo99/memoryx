"""MemoryX typed exception hierarchy.

Provides domain-specific exception types for each layer of the system.
Replaces bare ``except Exception:`` catch-alls with targeted error handling,
enabling better observability and debugging.

Usage::

    from memoryx.exceptions import StorageError

    try:
        repo.store_memory(record)
    except StorageError as e:
        logger.error("Storage failure", session_id=session_id, error=str(e))
        raise
"""

from __future__ import annotations


class MemoryXError(Exception):
    """Base exception for all MemoryX errors."""


# ── Storage ──

class StorageError(MemoryXError):
    """Database or storage layer failure."""


class ConnectionError(StorageError):
    """Database connection lost or uninitialized."""


class MigrationError(StorageError):
    """Schema migration failure."""


class RecordNotFoundError(StorageError):
    """Requested memory/entity/record does not exist."""


# ── Extraction ──

class ExtractionError(MemoryXError):
    """Memory extraction pipeline failure (LLM or rule-based)."""


class ExtractionClientError(ExtractionError):
    """LLM extraction client returned an error."""


class ExtractionValidationError(ExtractionError):
    """Extracted memory failed validation checks."""


# ── Safety ──

class SafetyError(MemoryXError):
    """Safety/security layer violation."""


class FirewallError(SafetyError):
    """LLM firewall blocked content."""


class PIIFilterError(SafetyError):
    """PII filter processing failure."""


class GoldenRuleViolation(SafetyError):
    """A golden rule was violated."""


# ── Retrieval ──

class RetrievalError(MemoryXError):
    """Retrieval pipeline failure."""


class EmbeddingError(RetrievalError):
    """Embedding generation or vector store failure."""


# ── API ──

class APIError(MemoryXError):
    """REST API layer error."""


class AuthenticationError(APIError):
    """API key authentication failure."""


class RateLimitError(APIError):
    """Rate limit exceeded."""


# ── Configuration ──

class ConfigurationError(MemoryXError):
    """Invalid or missing configuration."""


# ── Cognitive ──

class CognitiveError(MemoryXError):
    """Cognitive model error (forgetting curve, attention, etc.)."""


class WorkingMemoryError(CognitiveError):
    """Working memory engine failure."""


# ── Integration ──

class IntegrationError(MemoryXError):
    """External integration failure (Hermes, MCP, LangChain, etc.)."""


class HermesBridgeError(IntegrationError):
    """Hermes bridge communication failure."""


# ── Runtime ──

class RuntimeError_(MemoryXError):
    """Runtime execution error (command runner, context budget, etc.).

    Note: Named RuntimeError_ to avoid shadowing builtin RuntimeError.
    """


class CommandExecutionError(RuntimeError_):
    """Command execution in RuntimeCommandRunner failed."""