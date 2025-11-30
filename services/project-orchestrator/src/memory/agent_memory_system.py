import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from .embedding_client import EmbeddingClient
from .agent_memory_store import AgentMemoryStore
from .knowledge_store import KnowledgeStore
from .working_memory import WorkingMemory
from .episode_embedder import EpisodeEmbedder
from .models import Episode, Strategy, WorkingMemorySession

logger = logging.getLogger(__name__)

class AgentMemorySystem:
    """Unified facade for all memory operations"""
    
    def __init__(
        self,
        connection_string: str = "postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory",
        embedding_service_url: str = "http://embedding-service.dsm.svc.cluster.local"
    ):
        self.connection_string = connection_string
        self.embedding_service_url = embedding_service_url
        
        # Initialize components
        self.embedding_client = EmbeddingClient(embedding_service_url)
        self.episode_embedder = EpisodeEmbedder(self.embedding_client)
        self.agent_memory_store = AgentMemoryStore(connection_string)
        self.knowledge_store = KnowledgeStore(connection_string)
        self.working_memory = WorkingMemory(connection_string)
        
        self._initialized = False
    
    async def initialize(self, min_connections: int = 2, max_connections: int = 10):
        """Initialize all memory system components"""
        try:
            await self.agent_memory_store.initialize(min_connections, max_connections)
            await self.knowledge_store.initialize(min_connections, max_connections)
            await self.working_memory.initialize(min_connections, max_connections)
            
            self._initialized = True
            logger.info("AgentMemorySystem initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AgentMemorySystem: {e}")
            raise
    
    async def close(self):
        """Close all memory system components"""
        try:
            await self.agent_memory_store.close()
            await self.knowledge_store.close()
            await self.working_memory.close()
            await self.episode_embedder.close()
            
            logger.info("AgentMemorySystem closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing AgentMemorySystem: {e}")
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all memory system components"""
        if not self._initialized:
            return {"initialized": False}
        
        health_status = {}
        
        try:
            health_status["embedding_client"] = await self.embedding_client.health_check()
            health_status["agent_memory_store"] = await self.agent_memory_store.health_check()
            health_status["knowledge_store"] = await self.knowledge_store.health_check()
            health_status["working_memory"] = await self.working_memory.health_check()
            
            health_status["overall"] = all(health_status.values())
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_status["error"] = str(e)
        
        return health_status
    
    # ==== Episode Memory Operations ====
    
    async def store_episode_with_embedding(self, episode: Episode) -> UUID:
        """Store episode and generate embedding in one operation"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        try:
            # Store episode first
            episode_id = await self.agent_memory_store.store_episode(episode)
            
            # Generate and store embedding
            embedding = await self.episode_embedder.embed_episode(episode)
            await self.agent_memory_store.update_episode_embedding(episode_id, embedding)
            
            logger.info(f"Stored episode {episode_id} with embedding")
            return episode_id
            
        except Exception as e:
            logger.error(f"Failed to store episode with embedding: {e}")
            raise
    
    async def get_episode(self, episode_id: UUID) -> Optional[Episode]:
        """Retrieve episode by ID"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        return await self.agent_memory_store.get_episode(episode_id)
    
    async def recall_similar_episodes(
        self, 
        context: Dict[str, Any], 
        project_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Episode]:
        """Recall episodes similar to given context"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        try:
            # Convert context to query embedding
            query_text = self.episode_embedder.create_query_from_context(context)
            query_embedding = await self.episode_embedder.embed_query(query_text)
            
            # Search for similar episodes
            similar_episodes = await self.agent_memory_store.search_similar_episodes(
                query_embedding, project_id, limit, similarity_threshold
            )
            
            logger.debug(f"Recalled {len(similar_episodes)} similar episodes for context")
            return similar_episodes
            
        except Exception as e:
            logger.error(f"Failed to recall similar episodes: {e}")
            raise
    
    async def get_recent_project_episodes(
        self, 
        project_id: str, 
        hours: int = 24, 
        limit: int = 20
    ) -> List[Episode]:
        """Get recent episodes for a project"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        return await self.agent_memory_store.get_recent_episodes(project_id, hours, limit)
    
    # ==== Knowledge and Strategy Operations ====
    
    async def store_strategy(self, strategy: Strategy) -> UUID:
        """Store a new strategy"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        return await self.knowledge_store.store_strategy(strategy)
    
    async def find_applicable_strategies(
        self, 
        context: Dict[str, Any],
        min_confidence: float = 0.5,
        limit: int = 5
    ) -> List[Strategy]:
        """Find strategies applicable to given context"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        return await self.knowledge_store.find_applicable_strategies(
            context, "strategy", min_confidence, limit
        )
    
    async def update_strategy_performance(
        self, 
        strategy_id: UUID, 
        success: bool,
        episode_id: Optional[UUID] = None
    ):
        """Update strategy performance based on outcome"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        if success and episode_id:
            await self.knowledge_store.update_strategy_performance(
                strategy_id, success, supporting_episode_id=episode_id
            )
        elif not success and episode_id:
            await self.knowledge_store.update_strategy_performance(
                strategy_id, success, contradicting_episode_id=episode_id
            )
        else:
            await self.knowledge_store.update_strategy_performance(strategy_id, success)
    
    # ==== Working Memory Operations ====
    
    async def get_or_create_working_session(
        self, 
        project_id: str,
        user_id: Optional[str] = None,
        current_goal: Optional[str] = None
    ) -> WorkingMemorySession:
        """Get active working memory session or create new one"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        # Try to get existing active session
        session = await self.working_memory.get_active_session(project_id, user_id)
        
        if session is None:
            # Create new session
            session_id = await self.working_memory.create_session(
                project_id, user_id, current_goal
            )
            session = await self.working_memory.get_session(session_id)
            logger.info(f"Created new working memory session {session_id} for project {project_id}")
        else:
            logger.debug(f"Using existing working memory session {session.session_id}")
        
        return session
    
    async def update_working_context(
        self, 
        session_id: UUID, 
        context: Dict[str, Any]
    ):
        """Update working memory context"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        await self.working_memory.update_context(session_id, context)
    
    async def append_to_working_context(
        self, 
        session_id: UUID, 
        key: str, 
        value: Any
    ):
        """Append data to working memory context"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        await self.working_memory.append_to_context(session_id, key, value)
    
    # ==== High-Level Memory Operations ====
    
    async def learn_from_episode(
        self, 
        episode: Episode, 
        outcome_quality: Optional[float] = None
    ) -> Dict[str, Any]:
        """Complete learning cycle: store episode, update strategies, return insights"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        try:
            # Store episode with embedding
            episode_id = await self.store_episode_with_embedding(episode)
            
            # Update outcome quality if provided
            if outcome_quality is not None:
                await self.agent_memory_store.update_episode_outcome(
                    episode_id, episode.outcome or {}, outcome_quality
                )
            
            # Find similar past episodes to identify patterns
            similar_episodes = await self.recall_similar_episodes(
                episode.perception, episode.project_id, limit=5, similarity_threshold=0.6
            )
            
            # Get applicable strategies that were used
            applicable_strategies = await self.find_applicable_strategies(
                episode.perception, min_confidence=0.3, limit=10
            )
            
            # Return learning insights
            insights = {
                "episode_id": episode_id,
                "similar_episodes_found": len(similar_episodes),
                "applicable_strategies": len(applicable_strategies),
                "patterns_detected": len(similar_episodes) >= 3,  # Threshold for pattern detection
                "outcome_quality": outcome_quality
            }
            
            logger.info(f"Completed learning cycle for episode {episode_id}: {insights}")
            return insights
            
        except Exception as e:
            logger.error(f"Failed to learn from episode: {e}")
            raise
    
    async def get_decision_context(
        self, 
        project_id: str, 
        current_situation: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get comprehensive context for decision making"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        try:
            # Get or create working memory session
            working_session = await self.get_or_create_working_session(
                project_id, user_id, "decision_support"
            )
            
            # Get recent episodes
            recent_episodes = await self.get_recent_project_episodes(
                project_id, hours=72, limit=10
            )
            
            # Get similar episodes
            similar_episodes = await self.recall_similar_episodes(
                current_situation, project_id, limit=5, similarity_threshold=0.6
            )
            
            # Get applicable strategies
            applicable_strategies = await self.find_applicable_strategies(
                current_situation, min_confidence=0.4, limit=8
            )
            
            # Build comprehensive context
            decision_context = {
                "current_situation": current_situation,
                "working_session_id": working_session.session_id,
                "working_context": working_session.active_context,
                "recent_episodes": [
                    {"id": ep.episode_id, "summary": ep.get_summary(), "timestamp": ep.timestamp}
                    for ep in recent_episodes
                ],
                "similar_situations": [
                    {
                        "id": ep.episode_id, 
                        "summary": ep.get_summary(), 
                        "similarity": ep.similarity,
                        "outcome_quality": ep.outcome_quality
                    }
                    for ep in similar_episodes
                ],
                "applicable_strategies": [
                    {
                        "id": strat.knowledge_id,
                        "description": strat.description,
                        "confidence": strat.confidence,
                        "success_rate": strat.success_rate,
                        "times_applied": strat.times_applied
                    }
                    for strat in applicable_strategies
                ],
                "insights": {
                    "has_recent_activity": len(recent_episodes) > 0,
                    "has_similar_precedents": len(similar_episodes) > 0,
                    "has_proven_strategies": len([s for s in applicable_strategies if s.success_rate and s.success_rate > 0.7]) > 0,
                    "experience_level": "high" if len(recent_episodes) > 5 else "medium" if len(recent_episodes) > 2 else "low"
                }
            }
            
            logger.info(f"Built decision context for project {project_id}: {len(recent_episodes)} recent, {len(similar_episodes)} similar, {len(applicable_strategies)} strategies")
            return decision_context
            
        except Exception as e:
            logger.error(f"Failed to get decision context: {e}")
            raise
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired working memory sessions"""
        if not self._initialized:
            raise RuntimeError("AgentMemorySystem not initialized")
        
        return await self.working_memory.cleanup_expired_sessions()
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        if not self._initialized:
            return {"initialized": False}
        
        try:
            stats = {
                "episodes": {
                    "total": await self.agent_memory_store.get_episode_count(),
                },
                "strategies": {
                    "total": await self.knowledge_store.get_strategy_count(),
                    "active": await self.knowledge_store.get_strategy_count(active_only=True),
                },
                "working_sessions": {
                    "active": await self.working_memory.get_session_count(active_only=True),
                    "total": await self.working_memory.get_session_count(active_only=False),
                }
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get system stats: {e}")
            return {"error": str(e)}