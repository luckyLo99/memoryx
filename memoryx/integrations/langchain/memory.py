"""
MemoryX LangChain Integration.

Provides integration with LangChain memory system.
"""
from __future__ import annotations

import asyncio
from typing import Any, List, Optional

from langchain.schema import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain.memory.chat_message_histories import BaseChatMessageHistory
from langchain.schema import BaseRetriever, Document
from langchain.callbacks.manager import CallbackManagerForRetrieverRun


def _messages_to_dict(messages: List[BaseMessage]) -> List[dict]:
    """Convert LangChain messages to serializable format."""
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            role = "human"
        elif isinstance(msg, AIMessage):
            role = "ai"
        elif isinstance(msg, SystemMessage):
            role = "system"
        else:
            role = "unknown"
        result.append({"role": role, "content": msg.content})
    return result


def _dict_to_messages(messages: List[dict]) -> List[BaseMessage]:
    """Convert serializable format back to LangChain messages."""
    result = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if role == "human":
            result.append(HumanMessage(content=content))
        elif role == "ai":
            result.append(AIMessage(content=content))
        elif role == "system":
            result.append(SystemMessage(content=content))
        else:
            # Default to AIMessage for unknown types
            result.append(AIMessage(content=content))
    return result


class MemoryXChatMessageHistory(BaseChatMessageHistory):
    """
    Chat message history backed by MemoryX.
    
    Uses MemoryX to persist and retrieve chat history.
    """
    
    def __init__(
        self,
        session_id: str,
        repository: Any,
        memory_type: str = "conversation",
        scope: str = "session",
    ):
        """
        Initialize MemoryX chat message history.
        
        Args:
            session_id: Unique identifier for the chat session
            repository: MemoryX repository instance
            memory_type: Type of memory to store
            scope: Scope of the memory (session or global)
        """
        self.session_id = session_id
        self.repository = repository
        self.memory_type = memory_type
        self.scope = scope
        self._messages: List[BaseMessage] = []
        self._loaded = False
    
    async def _aload_messages(self) -> None:
        """Asynchronously load messages from MemoryX."""
        if self._loaded:
            return
        
        try:
            # Search for memories related to this session
            memories = await self.repository.query_memories(
                memory_type=self.memory_type,
                scope=self.scope,
                limit=100,
            )
            
            # Filter and parse messages
            session_memories = []
            for mem in memories:
                mem_metadata = {}
                try:
                    import json
                    mem_metadata = json.loads(mem.get("metadata_json", "{}"))
                except Exception:
                    pass
                
                # Check if this memory is for our session
                if mem_metadata.get("session_id") == self.session_id:
                    session_memories.append(mem)
            
            # Sort by created_at
            session_memories.sort(key=lambda x: x.get("created_at", ""))
            
            # Parse messages
            messages_list = []
            for mem in session_memories:
                try:
                    import json
                    content = mem.get("content", "{}")
                    msg_data = json.loads(content)
                    if "messages" in msg_data:
                        messages_list.extend(msg_data["messages"])
                except Exception:
                    # If not JSON, treat as single message
                    content = mem.get("content", "")
                    if content:
                        messages_list.append({"role": "ai", "content": content})
            
            self._messages = _dict_to_messages(messages_list)
            self._loaded = True
        except Exception:
            # If loading fails, start with empty messages
            self._messages = []
            self._loaded = True
    
    def _ensure_loaded(self) -> None:
        """Ensure messages are loaded (blocking)."""
        if not self._loaded:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(self._aload_messages())
    
    @property
    def messages(self) -> List[BaseMessage]:
        """Get all messages in the history."""
        self._ensure_loaded()
        return list(self._messages)
    
    async def _asave_messages(self) -> None:
        """Asynchronously save messages to MemoryX."""
        try:
            import json
            from datetime import datetime
            
            # Serialize messages
            messages_dict = _messages_to_dict(self._messages)
            
            # Create metadata
            metadata = {
                "session_id": self.session_id,
                "message_count": len(self._messages),
                "last_updated": datetime.now().isoformat(),
            }
            
            # First, try to find and delete existing memory for this session
            memories = await self.repository.query_memories(
                memory_type=self.memory_type,
                scope=self.scope,
                limit=100,
            )
            
            for mem in memories:
                try:
                    mem_metadata = json.loads(mem.get("metadata_json", "{}"))
                    if mem_metadata.get("session_id") == self.session_id:
                        await self.repository.delete_memory(mem.get("id"))
                except Exception:
                    pass
            
            # Store new memory
            await self.repository.add_memory(
                content=json.dumps({"messages": messages_dict}),
                memory_type=self.memory_type,
                scope=self.scope,
                metadata_json=json.dumps(metadata),
            )
        except Exception:
            # If save fails, continue - don't crash the application
            pass
    
    def _save_messages(self) -> None:
        """Save messages to MemoryX (blocking)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(self._asave_messages())
    
    def add_message(self, message: BaseMessage) -> None:
        """Add a message to the history."""
        self._ensure_loaded()
        self._messages.append(message)
        # Save after adding
        self._save_messages()
    
    def add_messages(self, messages: List[BaseMessage]) -> None:
        """Add multiple messages to the history."""
        self._ensure_loaded()
        self._messages.extend(messages)
        # Save after adding
        self._save_messages()
    
    def clear(self) -> None:
        """Clear all messages from the history."""
        self._messages = []
        self._loaded = False
        # Try to delete stored memory
        try:
            import json
            import asyncio
            
            async def _clear():
                memories = await self.repository.query_memories(
                    memory_type=self.memory_type,
                    scope=self.scope,
                    limit=100,
                )
                
                for mem in memories:
                    try:
                        mem_metadata = json.loads(mem.get("metadata_json", "{}"))
                        if mem_metadata.get("session_id") == self.session_id:
                            await self.repository.delete_memory(mem.get("id"))
                    except Exception:
                        pass
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(_clear())
        except Exception:
            pass


class MemoryXRetriever(BaseRetriever):
    """
    LangChain retriever backed by MemoryX.
    
    Uses MemoryX's retrieval engine to find relevant memories.
    """
    
    def __init__(
        self,
        query_api: Any,
        search_kwargs: Optional[dict] = None,
    ):
        """
        Initialize MemoryX retriever.
        
        Args:
            query_api: MemoryX QueryAPI instance
            search_kwargs: Additional search parameters
        """
        self.query_api = query_api
        self.search_kwargs = search_kwargs or {}
    
    def _get_relevant_documents(
        self, query: str, *, run_manager: Optional[CallbackManagerForRetrieverRun] = None
    ) -> List[Document]:
        """
        Get relevant documents for a query (sync version).
        
        Args:
            query: Search query
            run_manager: Callback manager
            
        Returns:
            List of relevant documents
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._aget_relevant_documents(query, run_manager=run_manager))
    
    async def _aget_relevant_documents(
        self, query: str, *, run_manager: Optional[CallbackManagerForRetrieverRun] = None
    ) -> List[Document]:
        """
        Get relevant documents for a query (async version).
        
        Args:
            query: Search query
            run_manager: Callback manager
            
        Returns:
            List of relevant documents
        """
        try:
            # Use MemoryX's search API
            results = await self.query_api.search(
                query=query,
                **self.search_kwargs,
            )
            
            # Convert to LangChain Document format
            documents = []
            for result in results:
                content = result.get("content", "")
                metadata = {
                    "memory_id": result.get("id", ""),
                    "score": result.get("score", 0.0),
                    "created_at": result.get("created_at", ""),
                    "memory_type": result.get("memory_type", ""),
                    "importance_score": result.get("importance_score", 0.0),
                    "confidence_score": result.get("confidence_score", 0.0),
                }
                
                # Parse additional metadata
                try:
                    import json
                    metadata_json = result.get("metadata_json", "{}")
                    additional_meta = json.loads(metadata_json)
                    metadata.update(additional_meta)
                except Exception:
                    pass
                
                documents.append(Document(page_content=content, metadata=metadata))
            
            return documents
        except Exception:
            # If retrieval fails, return empty list
            return []
