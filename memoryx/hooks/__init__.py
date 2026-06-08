from memoryx.hooks.memory_hook_manager import MemoryHookManager
from memoryx.hooks.session_listener import SessionEventListener
from memoryx.hooks.dispatcher import EventDispatcher
from memoryx.hooks.subscriber_manager import SubscriberManager
from memoryx.hooks.retry_manager import RetryManager
from memoryx.hooks.health_monitor import HealthMonitor
from memoryx.hooks.compatibility_adapter import CompatibilityAdapter
from memoryx.hooks.dead_letter_queue import DeadLetterQueue
from memoryx.hooks.queue_manager import QueueManager
from memoryx.hooks.hermes_adapter import HermesCompatibilityAdapter
from memoryx.runtime.events import MemoryEventType

__all__ = [
    "MemoryHookManager",
    "SessionEventListener",
    "EventDispatcher",
    "SubscriberManager",
    "RetryManager",
    "HealthMonitor",
    "CompatibilityAdapter",
    "DeadLetterQueue",
    "QueueManager",
    "HermesCompatibilityAdapter",
]

# Standard Hermes hook event types
HOOK_EVENTS = [
    MemoryEventType.ON_USER_MESSAGE,
    MemoryEventType.ON_ASSISTANT_RESPONSE,
    MemoryEventType.ON_TOOL_CALL,
    MemoryEventType.ON_TOOL_RESULT,
    MemoryEventType.ON_SESSION_END,
]