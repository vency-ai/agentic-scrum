import asyncpg
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from .models import Episode
import time # New import
from monitoring.agent_memory_metrics import (
    AGENT_MEMORY_DB_POOL_SIZE,
    AGENT_MEMORY_DB_POOL_CHECKED_IN,
    AGENT_MEMORY_DB_POOL_CHECKED_OUT,
    AGENT_MEMORY_DB_POOL_OVERFLOW,
    AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS, # New import
    AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL # New import
) # New import

logger = logging.getLogger(__name__)

class AgentMemoryStore:
    """Database operations for agent episodic memory"""
    
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
            self._max_connections = max_connections # Store max_connections
            logger.info("AgentMemoryStore initialized with connection pool")
            # Set initial pool metrics
            AGENT_MEMORY_DB_POOL_SIZE.set(max_connections)
            AGENT_MEMORY_DB_POOL_CHECKED_IN.set(min_connections)
            AGENT_MEMORY_DB_POOL_CHECKED_OUT.set(0)
            AGENT_MEMORY_DB_POOL_OVERFLOW.set(0)
        except Exception as e:
            logger.error(f"Failed to initialize AgentMemoryStore: {e}")
            raise
    
    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
            logger.info("AgentMemoryStore connection pool closed")
    
    async def store_episode(self, episode: Episode) -> UUID:
        """Store a new episode and return its ID"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                episode_id = await conn.fetchval("""
                    INSERT INTO agent_episodes 
                    (project_id, timestamp, perception, reasoning, action, 
                     outcome, outcome_quality, outcome_recorded_at, agent_version, 
                     control_mode, decision_source, sprint_id, chronicle_note_id, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    RETURNING episode_id
                """,
                episode.project_id,
                episode.timestamp,
                json.dumps(episode.perception),
                json.dumps(episode.reasoning),
                json.dumps(episode.action),
                json.dumps(episode.outcome) if episode.outcome else None,
                episode.outcome_quality,
                episode.outcome_recorded_at,
                episode.agent_version,
                episode.control_mode,
                episode.decision_source,
                episode.sprint_id,
                episode.chronicle_note_id,
                None  # embedding will be set separately
                )
                
                logger.info(f"Stored episode {episode_id} for project {episode.project_id}")
                return episode_id
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='store_episode').inc()
            logger.error(f"Failed to store episode: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='store_episode').observe(time.monotonic() - start_time)
    
    async def get_episode(self, episode_id: UUID) -> Optional[Episode]:
        """Retrieve episode by ID"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM agent_episodes WHERE episode_id = $1",
                    episode_id
                )
                
                if row:
                    return Episode.from_db_row(dict(row))
                return None
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='get_episode').inc()
            logger.error(f"Failed to get episode {episode_id}: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='get_episode').observe(time.monotonic() - start_time)
    
    async def get_project_episodes(
        self, 
        project_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Episode]:
        """Get episodes for a project, ordered by timestamp desc"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM agent_episodes 
                    WHERE project_id = $1 
                    ORDER BY timestamp DESC 
                    LIMIT $2 OFFSET $3
                """, project_id, limit, offset)
                
                return [Episode.from_db_row(dict(row)) for row in rows]
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='get_project_episodes').inc()
            logger.error(f"Failed to get episodes for project {project_id}: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='get_project_episodes').observe(time.monotonic() - start_time)
    
    async def update_episode_embedding(self, episode_id: UUID, embedding: List[float]):
        """Update episode with embedding vector"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                # Convert embedding to vector format
                vector_str = '[' + ','.join(map(str, embedding)) + ']'
                
                await conn.execute("""
                    UPDATE agent_episodes 
                    SET embedding = $1::vector(1024)
                    WHERE episode_id = $2
                """, vector_str, episode_id)
                
                logger.debug(f"Updated embedding for episode {episode_id}")
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='update_episode_embedding').inc()
            logger.error(f"Failed to update embedding for episode {episode_id}: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='update_episode_embedding').observe(time.monotonic() - start_time)
    
    async def update_episode_outcome(
        self, 
        episode_id: UUID, 
        outcome: Dict[str, Any], 
        quality: Optional[float] = None
    ):
        """Update episode outcome and quality"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    UPDATE agent_episodes 
                    SET outcome = $1, outcome_quality = $2, outcome_recorded_at = $3
                    WHERE episode_id = $4
                """, 
                json.dumps(outcome), 
                quality, 
                datetime.utcnow(), 
                episode_id)
                
                logger.info(f"Updated outcome for episode {episode_id}")
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='update_episode_outcome').inc()
            logger.error(f"Failed to update outcome for episode {episode_id}: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='update_episode_outcome').observe(time.monotonic() - start_time)
    
    async def search_similar_episodes(
        self,
        query_embedding: List[float],
        project_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Episode]:
        """Search for similar episodes using vector similarity"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                # Convert query embedding to vector format
                query_vector = '[' + ','.join(map(str, query_embedding)) + ']'
                
                # Build query based on whether project_id is provided
                if project_id:
                    sql = """
                        SELECT *, 1 - (embedding <=> $1::vector(1024)) as similarity
                        FROM agent_episodes 
                        WHERE project_id = $2 AND embedding IS NOT NULL
                        AND 1 - (embedding <=> $1::vector(1024)) >= $3
                        ORDER BY embedding <=> $1::vector(1024)
                        LIMIT $4
                    """
                    rows = await conn.fetch(sql, query_vector, project_id, similarity_threshold, limit)
                else:
                    sql = """
                        SELECT *, 1 - (embedding <=> $1::vector(1024)) as similarity
                        FROM agent_episodes 
                        WHERE embedding IS NOT NULL
                        AND 1 - (embedding <=> $1::vector(1024)) >= $2
                        ORDER BY embedding <=> $1::vector(1024)
                        LIMIT $3
                    """
                    rows = await conn.fetch(sql, query_vector, similarity_threshold, limit)
                
                episodes = []
                for row in rows:
                    episode_dict = dict(row)
                    episode_dict['similarity'] = row['similarity']
                    episodes.append(Episode.from_db_row(episode_dict))
                
                logger.debug(f"Found {len(episodes)} similar episodes")
                return episodes
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='search_similar_episodes').inc()
            logger.error(f"Failed to search similar episodes: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='search_similar_episodes').observe(time.monotonic() - start_time)
    
    async def get_recent_episodes(
        self, 
        project_id: str, 
        hours: int = 24, 
        limit: int = 50
    ) -> List[Episode]:
        """Get recent episodes within specified hours"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM agent_episodes 
                    WHERE project_id = $1 
                    AND timestamp >= NOW() - INTERVAL '%d hours'
                    ORDER BY timestamp DESC 
                    LIMIT $2
                """ % hours, project_id, limit)
                
                return [Episode.from_db_row(dict(row)) for row in rows]
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='get_recent_episodes').inc()
            logger.error(f"Failed to get recent episodes: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='get_recent_episodes').observe(time.monotonic() - start_time)
    
    async def get_episode_count(self, project_id: Optional[str] = None) -> int:
        """Get total episode count, optionally filtered by project"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                if project_id:
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM agent_episodes WHERE project_id = $1",
                        project_id
                    )
                else:
                    count = await conn.fetchval("SELECT COUNT(*) FROM agent_episodes")
                
                return count
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='get_episode_count').inc()
            logger.error(f"Failed to get episode count: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='get_episode_count').observe(time.monotonic() - start_time)
    
    async def delete_episode(self, episode_id: UUID) -> bool:
        """Delete episode by ID"""
        if not self._pool:
            raise RuntimeError("AgentMemoryStore not initialized")
        
        start_time = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM agent_episodes WHERE episode_id = $1",
                    episode_id
                )
                
                deleted = result.split()[-1] == "1"  # "DELETE 1" means one row deleted
                if deleted:
                    logger.info(f"Deleted episode {episode_id}")
                
                return deleted
                
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation='delete_episode').inc()
            logger.error(f"Failed to delete episode {episode_id}: {e}")
            raise
        finally:
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation='delete_episode').observe(time.monotonic() - start_time)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database connectivity and table access, and update pool metrics"""
        if not self._pool:
            return {"status": "not_initialized"}
        
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1 FROM agent_episodes LIMIT 1")
                
                # Update pool metrics using asyncpg.Pool public methods
                current_pool_size = self._pool.get_size()
                idle_connections = self._pool.get_idle_size()
                
                checked_out_connections = current_pool_size - idle_connections
                # asyncpg pool does not expose an explicit 'overflow' count directly.
                # We can infer it if current_pool_size exceeds the configured max_connections.
                overflow_connections = current_pool_size - self._max_connections if current_pool_size > self._max_connections else 0

                AGENT_MEMORY_DB_POOL_SIZE.set(self._max_connections) # Max configured pool size
                AGENT_MEMORY_DB_POOL_CHECKED_IN.set(idle_connections)
                AGENT_MEMORY_DB_POOL_CHECKED_OUT.set(checked_out_connections)
                AGENT_MEMORY_DB_POOL_OVERFLOW.set(overflow_connections)

                return {
                    "status": "ok",
                    "pool_status": {
                        "pool_size": self._max_connections,
                        "checked_in_connections": idle_connections,
                        "checked_out_connections": checked_out_connections,
                        "overflow_connections": overflow_connections,
                        "total_connections": current_pool_size
                    }
                }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "error", "error_message": str(e)}