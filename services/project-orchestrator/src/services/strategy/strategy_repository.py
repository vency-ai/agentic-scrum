import asyncpg
import logging
import json
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID
from memory.models import Strategy
from memory.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

class StrategyRepository:
    """
    Strategy Repository - Manages CRUD operations for strategies
    
    Responsible for:
    - Creating and storing new strategies
    - Retrieving strategies by various criteria
    - Updating strategy performance metrics
    - Managing strategy lifecycle (activation/deactivation)
    - Versioning and archival of outdated strategies
    """
    
    def __init__(self, knowledge_store: KnowledgeStore):
        self.knowledge_store = knowledge_store
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def create_strategy(
        self,
        pattern_data: Dict[str, Any],
        confidence: float,
        description: str,
        created_by: str = "strategy_generator"
    ) -> UUID:
        """Create a new strategy from extracted pattern data"""
        try:
            strategy = Strategy(
                knowledge_type="strategy",
                content=pattern_data,
                description=description,
                confidence=confidence,
                supporting_episodes=pattern_data.get('supporting_episodes', []),
                contradicting_episodes=[],
                times_applied=0,
                success_count=0,
                failure_count=0,
                created_at=datetime.utcnow(),
                last_validated=None,
                last_applied=None,
                created_by=created_by,
                is_active=True
            )
            
            strategy_id = await self.knowledge_store.store_strategy(strategy)
            self.logger.info(f"Created new strategy {strategy_id}: {description}")
            return strategy_id
            
        except Exception as e:
            self.logger.error(f"Failed to create strategy: {e}")
            raise
    
    async def get_strategy(self, strategy_id: UUID) -> Optional[Strategy]:
        """Retrieve a strategy by ID"""
        return await self.knowledge_store.get_strategy(strategy_id)
    
    async def get_active_strategies(
        self,
        min_confidence: float = 0.3,
        limit: int = 100
    ) -> List[Strategy]:
        """Get all active strategies above confidence threshold"""
        return await self.knowledge_store.get_active_strategies(
            knowledge_type="strategy",
            limit=limit
        )
    
    async def find_applicable_strategies(
        self,
        context: Dict[str, Any],
        min_confidence: float = 0.3,
        limit: int = 10
    ) -> List[Strategy]:
        """Find strategies applicable to the given decision context"""
        return await self.knowledge_store.find_applicable_strategies(
            context=context,
            knowledge_type="strategy",
            min_confidence=min_confidence,
            limit=limit
        )
    
    async def update_strategy_performance(
        self,
        strategy_id: UUID,
        success: bool,
        episode_id: Optional[UUID] = None
    ):
        """Update strategy performance based on application outcome"""
        if success:
            await self.knowledge_store.update_strategy_performance(
                knowledge_id=strategy_id,
                success=True,
                supporting_episode_id=episode_id
            )
        else:
            await self.knowledge_store.update_strategy_performance(
                knowledge_id=strategy_id,
                success=False,
                contradicting_episode_id=episode_id
            )
    
    async def log_strategy_performance(
        self,
        strategy_id: UUID,
        episode_id: UUID,
        project_id: str,
        predicted_outcome: Dict[str, Any],
        actual_outcome: Dict[str, Any],
        outcome_quality: float,
        strategy_confidence: float,
        context_similarity: Optional[float] = None
    ):
        """Log detailed strategy performance for learning optimizer"""
        if not self.knowledge_store._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        try:
            # Calculate performance delta
            performance_delta = None
            if 'expected_quality' in predicted_outcome and outcome_quality is not None:
                performance_delta = outcome_quality - predicted_outcome['expected_quality']
            
            async with self.knowledge_store._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO strategy_performance_log 
                    (strategy_id, episode_id, project_id, predicted_outcome, actual_outcome,
                     outcome_quality, strategy_confidence, context_similarity, performance_delta)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                strategy_id, episode_id, project_id,
                json.dumps(predicted_outcome), json.dumps(actual_outcome),
                outcome_quality, strategy_confidence, context_similarity, performance_delta)
                
                self.logger.debug(f"Logged performance for strategy {strategy_id} on episode {episode_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to log strategy performance: {e}")
            raise
    
    async def get_strategy_performance_history(
        self,
        strategy_id: UUID,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent performance history for a strategy"""
        if not self.knowledge_store._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        try:
            async with self.knowledge_store._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM strategy_performance_log
                    WHERE strategy_id = $1 
                    AND application_timestamp >= NOW() - INTERVAL '%d days'
                    ORDER BY application_timestamp DESC
                    LIMIT $2
                """ % days, strategy_id, limit)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Failed to get strategy performance history: {e}")
            raise
    
    async def get_underperforming_strategies(
        self,
        min_applications: int = 5,
        max_success_rate: float = 0.3,
        days: int = 30
    ) -> List[Tuple[UUID, float]]:
        """Identify strategies that are underperforming and may need deactivation"""
        if not self.knowledge_store._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        try:
            async with self.knowledge_store._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT s.knowledge_id, s.success_rate, COUNT(spl.log_id) as recent_applications
                    FROM agent_knowledge s
                    LEFT JOIN strategy_performance_log spl ON s.knowledge_id = spl.strategy_id
                        AND spl.application_timestamp >= NOW() - INTERVAL '%d days'
                    WHERE s.knowledge_type = 'strategy' 
                    AND s.is_active = true
                    AND s.times_applied >= $1
                    AND s.success_rate <= $2
                    GROUP BY s.knowledge_id, s.success_rate
                    HAVING COUNT(spl.log_id) >= $1
                    ORDER BY s.success_rate ASC
                """ % days, min_applications, max_success_rate, min_applications)
                
                return [(row['knowledge_id'], row['success_rate']) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Failed to get underperforming strategies: {e}")
            raise
    
    async def deactivate_strategy(self, strategy_id: UUID, reason: str = "underperforming"):
        """Deactivate a strategy that is no longer performing well"""
        await self.knowledge_store.deactivate_strategy(strategy_id, reason)
        self.logger.info(f"Deactivated strategy {strategy_id}: {reason}")
    
    async def get_strategy_analytics(self) -> Dict[str, Any]:
        """Get overall strategy repository analytics"""
        try:
            total_strategies = await self.knowledge_store.get_strategy_count(
                knowledge_type="strategy", active_only=False
            )
            active_strategies = await self.knowledge_store.get_strategy_count(
                knowledge_type="strategy", active_only=True
            )
            
            if not self.knowledge_store._pool:
                raise RuntimeError("KnowledgeStore not initialized")
            
            async with self.knowledge_store._pool.acquire() as conn:
                # Get performance metrics
                perf_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_applications,
                        AVG(outcome_quality) as avg_outcome_quality,
                        AVG(strategy_confidence) as avg_strategy_confidence,
                        COUNT(CASE WHEN outcome_quality >= 0.7 THEN 1 END) as high_quality_outcomes
                    FROM strategy_performance_log
                    WHERE application_timestamp >= NOW() - INTERVAL '30 days'
                """)
                
                # Get top performing strategies
                top_performers = await conn.fetch("""
                    SELECT knowledge_id, description, confidence, success_rate, times_applied
                    FROM agent_knowledge
                    WHERE knowledge_type = 'strategy' AND is_active = true AND times_applied >= 3
                    ORDER BY success_rate DESC, confidence DESC
                    LIMIT 5
                """)
            
            return {
                "total_strategies": total_strategies,
                "active_strategies": active_strategies,
                "inactive_strategies": total_strategies - active_strategies,
                "performance_stats": dict(perf_stats) if perf_stats else {},
                "top_performers": [dict(row) for row in top_performers]
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get strategy analytics: {e}")
            raise
    
    async def cleanup_old_performance_logs(self, days_to_keep: int = 90):
        """Clean up old performance logs to manage storage"""
        if not self.knowledge_store._pool:
            raise RuntimeError("KnowledgeStore not initialized")
        
        try:
            async with self.knowledge_store._pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM strategy_performance_log
                    WHERE application_timestamp < NOW() - INTERVAL '%d days'
                """ % days_to_keep)
                
                deleted_count = int(result.split()[-1])
                self.logger.info(f"Cleaned up {deleted_count} old performance log entries")
                return deleted_count
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup old performance logs: {e}")
            raise