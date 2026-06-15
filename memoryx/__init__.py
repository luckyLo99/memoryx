from ._version import __version__

from .api import MemoryQueryAPI
from .storage.bank import MemoryBank
from .compression import SemanticCompressionEngine
from .config import MemoryXSettings
from .consolidation import ConsolidationEngine
from .storage.conversation_log import ConversationLogStore
from .context import ContextAssemblyEngine, ContextBundle
from .context_reasoning import ContextReasoningEngine
from .embeddings import (
    EmbeddingCache,
    EmbeddingManager,
    EmbeddingQueueWorker,
    EmbeddingRequest,
    EmbeddingResult,
    GenericEmbeddingClient,
    VectorStore,
    VectorProvider,
    VectorHit,
    NullVectorProvider,
)
from .episodic import EpisodicMemoryEngine
from .evaluation import MemoryEvaluationEngine
from .extraction import (
    ExtractionMemory,
    ExtractionRequest,
    ExtractionResult,
    ExtractionSource,
    GenericLLMExtractionClient,
    MemoryExtractionEngine,
)
from .runtime.events import EventPriority, MemoryEventType
from .hermes_adapter import HermesCompatibilityAdapter  # noqa: F401 — backward-compat alias
from .graph import EntityGraphEngine
from .hierarchy import HierarchicalMemoryManager, MemoryMigrationReport, MemoryTier
from .hooks import (
    CompatibilityAdapter,
    DeadLetterQueue,
    EventDispatcher,
    HealthMonitor,
    MemoryHookManager,
    QueueManager,
    RetryManager,
    SessionEventListener,
    SubscriberManager,
)
from .injection import InjectedPrompt, PromptInjectionEngine
from .integration import HermesIntegrationRuntime
from .knowledge_distillation import DistilledKnowledgeArtifact, KnowledgeDistillationEngine
from .mcp.server import MCPServer
from .meta_cognition import MetaCognitiveProfile, MetaCognitiveReflectionEngine
from .migration import MigrationEngine, MigrationReport
from .observability import MemoryObservabilityEngine
from .runtime.orchestrator import ModuleRegistry, ModuleStatus, SystemOrchestrator
from .palace import PalaceDrawer, PalaceEngine, PalaceNavigator, PalaceRoom, PalaceWing
from .evolution import (
    EvolutionDecision,
    EvolutionIntegration,
    EvolutionKind,
    EvolutionManager,
    EvolutionNode,
    EvolutionRepository,
    EvolutionTrajectory,
    IntegrationDecision,
    PreferenceSignal,
    PreferenceSignalDetector,
    ensure_evolution_table,
)
from .project_state import ProjectState, ProjectStateEngine
from .recall import ActiveRecallEngine
from .reflection.reflect import ReflectEngine
from .reflection import ReflectionEngine
from .reinforcement import ImportanceReinforcementEngine
from .governance import ResourceGovernanceDecision, ResourceGovernanceEngine, ResourceLimits, RuntimeResourceSnapshot
from .retrieval import (
    HybridRetrievalEngine,
    RetrievalIntent,
    RetrievalResult,
    ScoreBreakdown,
    ConfidenceLabel,
    compute_final_score,
    normalize_bm25,
    recency,
    decay_multiplier,
    access_boost,
    status_penalty,
    label_from_score,
    reciprocal_rank_fusion,
    make_ranked_candidates,
    RankedCandidate,
)
from .routing import MemoryRouter, RoutePlan, RoutingIntent
from .cognitive.persona import PersonaEngine
from .cognition import RuntimeCognitiveState, RuntimeCognitiveStateEngine
from .safety import MemorySafetyEngine
from .episodic.scene import Scene, SceneEngine
from .storage.seed import ConversationSeed
from .validation.self_editor import SelfEditor
from .self_healing import SelfHealingEngine, SelfHealingReport
from .storage import MemoryRecord, MemoryRepository
from .graph.symbolic import SymbolicIndex
from .temporal import TemporalMemoryEngine, TemporalState
from .tool_memory import ToolInteractionMemory, ToolInteractionRecord
from .validation import (
    ConflictResolver,
    DedupEngine,
    MemoryValidationEngine,
    QuarantineManager,
    QuarantineReport,
    ScoringEngine,
    SimilarityEngine,
    ValidationDecision,
    ValidationResult,
)
from .working_memory import WorkingMemoryEngine, WorkingMemoryState

__all__ = [
    "ActiveRecallEngine",
    "MemoryBank",
    "ConflictResolver",
    "ConsolidationEngine",
    "ContextAssemblyEngine",
    "ContextBundle",
    "ContextReasoningEngine",
    "ConversationLogStore",
    "DedupEngine",
    "DistilledKnowledgeArtifact",
    "EmbeddingCache",
    "EmbeddingManager",
    "EmbeddingQueueWorker",
    "EmbeddingRequest",
    "EmbeddingResult",
    "EntityGraphEngine",
    "EventPriority",
    "EpisodicMemoryEngine",
    "ExtractionMemory",
    "ExtractionRequest",
    "ExtractionResult",
    "ExtractionSource",
    "GenericEmbeddingClient",
    "GenericLLMExtractionClient",
    "CompatibilityAdapter",
    "DeadLetterQueue",
    "EventDispatcher",
    "HealthMonitor",
    "HermesIntegrationRuntime",
    "HermesCompatibilityAdapter",
    "HierarchicalMemoryManager",
    "MemoryHookManager",
    "QueueManager",
    "RetryManager",
    "SessionEventListener",
    "SubscriberManager",
    "HybridRetrievalEngine",
    "ImportanceReinforcementEngine",
    "InjectedPrompt",
    "KnowledgeDistillationEngine",
    "MemoryEvaluationEngine",
    "MemoryEventType",
    "MemoryExtractionEngine",
    "MemoryMigrationReport",
    "MemoryObservabilityEngine",
    "MemoryQueryAPI",
    "MCPServer",
    "MemoryRecord",
    "MemoryRepository",
    "MemoryRouter",
    "MemorySafetyEngine",
    "MemoryTier",
    "MemoryValidationEngine",
    "MemoryXSettings",
    "MetaCognitiveProfile",
    "MetaCognitiveReflectionEngine",
    "MigrationEngine",
    "MigrationReport",
    "ModuleRegistry",
    "ModuleStatus",
    "SystemOrchestrator",
    "PalaceRoom",
    "PalaceWing",
    "PalaceEngine",
    "PalaceNavigator",
    "PalaceDrawer",
    "PersonaEngine",
    "ProjectState",
    "ProjectStateEngine",
    "PromptInjectionEngine",
    "QuarantineManager",
    "QuarantineReport",
    "ReflectionEngine",
    "ReflectEngine",
    "ResourceGovernanceDecision",
    "ResourceGovernanceEngine",
    "ResourceLimits",
    "RetrievalIntent",
    "RetrievalResult",
    "RoutePlan",
    "RoutingIntent",
    "RuntimeResourceSnapshot",
    "RuntimeCognitiveState",
    "RuntimeCognitiveStateEngine",
    "ScoringEngine",
    "Scene",
    "SceneEngine",
    "SelfEditor",
    "SelfHealingEngine",
    "SelfHealingReport",
    "SemanticCompressionEngine",
    "SymbolicIndex",
    "ConversationSeed",
    "SimilarityEngine",
    "TemporalMemoryEngine",
    "TemporalState",
    "ToolInteractionMemory",
    "ToolInteractionRecord",
    "ValidationDecision",
    "ValidationResult",
    "VectorStore",
    "WorkingMemoryEngine",
    "WorkingMemoryState",
    # — evolutionary trajectory —
    "EvolutionDecision",
    "EvolutionIntegration",
    "EvolutionKind",
    "EvolutionManager",
    "EvolutionNode",
    "EvolutionRepository",
    "EvolutionTrajectory",
    "IntegrationDecision",
    "PreferenceSignal",
    "PreferenceSignalDetector",
    "ensure_evolution_table",
    # — retrieval scoring / fusion —
    "ScoreBreakdown",
    "ConfidenceLabel",
    "compute_final_score",
    "normalize_bm25",
    "recency",
    "decay_multiplier",
    "access_boost",
    "status_penalty",
    "label_from_score",
    "reciprocal_rank_fusion",
    "make_ranked_candidates",
    "RankedCandidate",
    # — vector abstraction —
    "VectorProvider",
    "VectorHit",
    "NullVectorProvider",
]
