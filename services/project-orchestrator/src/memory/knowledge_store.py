import asyncpg
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from .models import Strategy

logger = logging.getLogger(__name__)

class KnowledgeStore:
    """Database operations for agent knowledge and strategy storage"""
    
    def __init__(
        self,
        connection_string: str = "postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory"
    ):
        self.connection_string = connection_string
        self._pool = None
    
    async def initialize(self, min_connections: int = 2, max_connections: int = 10):
        """Initialize connection pool"""
        try:
            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=min_connections,
                max_size=max_connections
            )
            logger.info("KnowledgeStore initialized with connection pool")
        except Exception as e:
            logger.error(f"Failed to initialize KnowledgeStore: {e}")
            raise
    
    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
            logger.info("KnowledgeStore connection pool closed")
    
    async def store_strategy(self, strategy: Strategy) -> UUID:
        """Store a new strategy and return its ID"""
        if not self._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                knowledge_id = await conn.fetchval("""
                    INSERT INTO agent_knowledge 
                    (knowledge_type, content, description, confidence, 
                     supporting_episodes, contradicting_episodes, times_applied, 
                     success_count, failure_count, created_at,
                     last_validated, last_applied, created_by, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    RETURNING knowledge_id
                """,
                strategy.knowledge_type,
                json.dumps(strategy.content),
                strategy.description,
                strategy.confidence,
                strategy.supporting_episodes,
                strategy.contradicting_episodes,
                strategy.times_applied,
                strategy.success_count,
                strategy.failure_count,
                strategy.created_at,
                strategy.last_validated,
                strategy.last_applied,
                strategy.created_by,
                strategy.is_active
                )
                
                logger.info(f"Stored strategy {knowledge_id}: {strategy.description}")
                return knowledge_id
                
            except Exception as e:
                logger.error(f"Failed to store strategy: {e}")
                raise
    
    async def get_strategy(self, knowledge_id: UUID) -> Optional[Strategy]:
        """Retrieve strategy by ID"""
        if not self._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT * FROM agent_knowledge WHERE knowledge_id = $1",
                    knowledge_id
                )
                
                if row:
                    return Strategy.from_db_row(dict(row))
                return None
                
            except Exception as e:
                logger.error(f"Failed to get strategy {knowledge_id}: {e}")
                raise
    
    async def get_active_strategies(
        self, 
        knowledge_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Strategy]:
        """Get active strategies, optionally filtered by type"""
        if not self._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                if knowledge_type:
                    rows = await conn.fetch("""
                        SELECT * FROM agent_knowledge 
                        WHERE is_active = true AND knowledge_type = $1
                        ORDER BY confidence DESC, success_rate DESC NULLS LAST
                        LIMIT $2 OFFSET $3
                    """, knowledge_type, limit, offset)
                else:
                    rows = await conn.fetch("""
                        SELECT * FROM agent_knowledge 
                        WHERE is_active = true
                        ORDER BY confidence DESC, success_rate DESC NULLS LAST
                        LIMIT $1 OFFSET $2
                    """, limit, offset)
                
                return [Strategy.from_db_row(dict(row)) for row in rows]
                
            except Exception as e:
                logger.error(f"Failed to get active strategies: {e}")
                raise
    
    async def update_strategy_performance(
        self, 
        knowledge_id: UUID, 
        success: bool,
        supporting_episode_id: Optional[UUID] = None,
        contradicting_episode_id: Optional[UUID] = None
    ):
        """Update strategy performance metrics"""
        if not self._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                # Get current stats
                current = await conn.fetchrow("""
                    SELECT times_applied, success_count, failure_count, 
                           supporting_episodes, contradicting_episodes
                    FROM agent_knowledge 
                    WHERE knowledge_id = $1
                """, knowledge_id)
                
                if not current:
                    raise ValueError(f"Strategy {knowledge_id} not found")
                
                # Update counters
                new_times_applied = current['times_applied'] + 1
                new_success_count = current['success_count'] + (1 if success else 0)
                new_failure_count = current['failure_count'] + (0 if success else 1)
                new_success_rate = new_success_count / new_times_applied if new_times_applied > 0 else 0
                
                # Update episode lists
                supporting_episodes = list(current['supporting_episodes']) if current['supporting_episodes'] else []
                contradicting_episodes = list(current['contradicting_episodes']) if current['contradicting_episodes'] else []
                
                if success and supporting_episode_id:
                    if supporting_episode_id not in supporting_episodes:
                        supporting_episodes.append(supporting_episode_id)
                elif not success and contradicting_episode_id:
                    if contradicting_episode_id not in contradicting_episodes:
                        contradicting_episodes.append(contradicting_episode_id)
                
                # Update database
                await conn.execute("""
                    UPDATE agent_knowledge 
                    SET times_applied = $1, success_count = $2, failure_count = $3,
                        success_rate = $4, supporting_episodes = $5, 
                        contradicting_episodes = $6, last_applied = $7
                    WHERE knowledge_id = $8
                """, 
                new_times_applied, new_success_count, new_failure_count,
                new_success_rate, supporting_episodes, contradicting_episodes,
                datetime.utcnow(), knowledge_id)
                
                logger.info(f"Updated strategy {knowledge_id} performance: success_rate={new_success_rate:.3f}")
                
            except Exception as e:
                logger.error(f"Failed to update strategy performance: {e}")
                raise
    
    async def find_applicable_strategies(
        self, 
        context: Dict[str, Any],
        knowledge_type: str = "strategy",
        min_confidence: float = 0.3,
        limit: int = 10
    ) -> List[Strategy]:
        """Find strategies applicable to given context"""
        if not self._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                # For now, return strategies by confidence and success rate
                # TODO: Implement content-based matching logic
                rows = await conn.fetch("""
                    SELECT * FROM agent_knowledge 
                    WHERE knowledge_type = $1 AND is_active = true 
                    AND confidence >= $2
                    ORDER BY confidence DESC, success_rate DESC NULLS LAST
                    LIMIT $3
                """, knowledge_type, min_confidence, limit)
                
                strategies = [Strategy.from_db_row(dict(row)) for row in rows]
                
                # Filter by applicability (placeholder logic)
                applicable = []
                for strategy in strategies:
                    if strategy.applies_to(context):
                        applicable.append(strategy)
                
                logger.debug(f"Found {len(applicable)} applicable strategies for context")
                return applicable
                
            except Exception as e:
                logger.error(f"Failed to find applicable strategies: {e}")
                raise
    
    async def deactivate_strategy(self, knowledge_id: UUID, reason: str = "manual"):
        """Deactivate a strategy"""
        if not self._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE agent_knowledge 
                    SET is_active = false, last_validated = $1
                    WHERE knowledge_id = $2
                """, datetime.utcnow(), knowledge_id)
                
                logger.info(f"Deactivated strategy {knowledge_id}: {reason}")
                
            except Exception as e:
                logger.error(f"Failed to deactivate strategy {knowledge_id}: {e}")
                raise
    
    async def get_strategy_count(self, knowledge_type: Optional[str] = None, active_only: bool = True) -> int:
        """Get total strategy count"""
        if not self._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                if knowledge_type:
                    if active_only:
                        count = await conn.fetchval(
                            "SELECT COUNT(*) FROM agent_knowledge WHERE knowledge_type = $1 AND is_active = true",
                            knowledge_type
                        )
                    else:
                        count = await conn.fetchval(
                            "SELECT COUNT(*) FROM agent_knowledge WHERE knowledge_type = $1",
                            knowledge_type
                        )
                else:
                    if active_only:
                        count = await conn.fetchval("SELECT COUNT(*) FROM agent_knowledge WHERE is_active = true")
                    else:
                        count = await conn.fetchval("SELECT COUNT(*) FROM agent_knowledge")
                
                return count
                
            except Exception as e:
                logger.error(f"Failed to get strategy count: {e}")
                raise
    
    async def health_check(self) -> bool:
        """Check database connectivity and table access"""
        if not self._pool:
            return False
        
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1 FROM agent_knowledge LIMIT 1")
                return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False