import asyncpg
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID
from .models import WorkingMemorySession

logger = logging.getLogger(__name__)

class WorkingMemory:
    """Database operations for agent working memory sessions"""
    
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
            logger.info("WorkingMemory initialized with connection pool")
        except Exception as e:
            logger.error(f"Failed to initialize WorkingMemory: {e}")
            raise
    
    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
            logger.info("WorkingMemory connection pool closed")
    
    async def create_session(
        self, 
        project_id: str,
        user_id: Optional[str] = None,
        current_goal: Optional[str] = None,
        active_context: Optional[Dict[str, Any]] = None,
        expires_in_hours: int = 1
    ) -> UUID:
        """Create a new working memory session"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
                
                session_id = await conn.fetchval("""
                    INSERT INTO agent_working_memory 
                    (project_id, user_id, current_goal, active_context, expires_at, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING session_id
                """,
                project_id,
                user_id,
                current_goal,
                json.dumps(active_context) if active_context else None,
                expires_at,
                True
                )
                
                logger.info(f"Created working memory session {session_id} for project {project_id}")
                return session_id
                
            except Exception as e:
                logger.error(f"Failed to create working memory session: {e}")
                raise
    
    async def get_session(self, session_id: UUID) -> Optional[WorkingMemorySession]:
        """Retrieve working memory session by ID"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT * FROM agent_working_memory WHERE session_id = $1",
                    session_id
                )
                
                if row:
                    return WorkingMemorySession.from_db_row(dict(row))
                return None
                
            except Exception as e:
                logger.error(f"Failed to get working memory session {session_id}: {e}")
                raise
    
    async def get_active_session(
        self, 
        project_id: str,
        user_id: Optional[str] = None
    ) -> Optional[WorkingMemorySession]:
        """Get active working memory session for project"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                if user_id:
                    row = await conn.fetchrow("""
                        SELECT * FROM agent_working_memory 
                        WHERE project_id = $1 AND user_id = $2
                        AND is_active = true AND expires_at > NOW()
                        ORDER BY last_updated DESC
                        LIMIT 1
                    """, project_id, user_id)
                else:
                    row = await conn.fetchrow("""
                        SELECT * FROM agent_working_memory 
                        WHERE project_id = $1 
                        AND is_active = true AND expires_at > NOW()
                        ORDER BY last_updated DESC
                        LIMIT 1
                    """, project_id)
                
                if row:
                    return WorkingMemorySession.from_db_row(dict(row))
                return None
                
            except Exception as e:
                logger.error(f"Failed to get active session for project {project_id}: {e}")
                raise
    
    async def update_context(
        self, 
        session_id: UUID, 
        active_context: Dict[str, Any]
    ):
        """Update active context in working memory session"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE agent_working_memory 
                    SET active_context = $1
                    WHERE session_id = $2
                """, 
                json.dumps(active_context), 
                session_id)
                
                logger.debug(f"Updated context for session {session_id}")
                
            except Exception as e:
                logger.error(f"Failed to update context for session {session_id}: {e}")
                raise
    
    async def update_temporary_data(
        self, 
        session_id: UUID, 
        temporary_data: Dict[str, Any]
    ):
        """Update temporary data in working memory session"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE agent_working_memory 
                    SET temporary_data = $1, updated_at = $2
                    WHERE session_id = $3
                """, 
                json.dumps(temporary_data), 
                datetime.utcnow(), 
                session_id)
                
                logger.debug(f"Updated temporary data for session {session_id}")
                
            except Exception as e:
                logger.error(f"Failed to update temporary data for session {session_id}: {e}")
                raise
    
    async def append_to_context(
        self, 
        session_id: UUID, 
        key: str, 
        value: Any
    ):
        """Append data to existing context"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                # Get current context
                current_context_json = await conn.fetchval(
                    "SELECT active_context FROM agent_working_memory WHERE session_id = $1",
                    session_id
                )
                
                if current_context_json is None:
                    raise ValueError(f"Session {session_id} not found")
                
                # Parse and update context
                current_context = json.loads(current_context_json) if isinstance(current_context_json, str) else current_context_json
                current_context[key] = value
                
                # Save updated context
                await conn.execute("""
                    UPDATE agent_working_memory 
                    SET active_context = $1, updated_at = $2
                    WHERE session_id = $3
                """, 
                json.dumps(current_context), 
                datetime.utcnow(), 
                session_id)
                
                logger.debug(f"Appended {key} to context for session {session_id}")
                
            except Exception as e:
                logger.error(f"Failed to append to context for session {session_id}: {e}")
                raise
    
    async def deactivate_session(self, session_id: UUID):
        """Deactivate working memory session"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE agent_working_memory 
                    SET is_active = false, updated_at = $1
                    WHERE session_id = $2
                """, datetime.utcnow(), session_id)
                
                logger.info(f"Deactivated working memory session {session_id}")
                
            except Exception as e:
                logger.error(f"Failed to deactivate session {session_id}: {e}")
                raise
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired working memory sessions"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                # Deactivate expired sessions
                result = await conn.execute("""
                    UPDATE agent_working_memory 
                    SET is_active = false, updated_at = $1
                    WHERE expires_at <= NOW() AND is_active = true
                """, datetime.utcnow())
                
                # Extract count from result (e.g., "UPDATE 5" -> 5)
                count = int(result.split()[-1]) if result.split() else 0
                
                if count > 0:
                    logger.info(f"Cleaned up {count} expired working memory sessions")
                
                return count
                
            except Exception as e:
                logger.error(f"Failed to cleanup expired sessions: {e}")
                raise
    
    async def get_project_sessions(
        self, 
        project_id: str,
        active_only: bool = True,
        limit: int = 10
    ) -> List[WorkingMemorySession]:
        """Get working memory sessions for a project"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                if active_only:
                    rows = await conn.fetch("""
                        SELECT * FROM agent_working_memory 
                        WHERE project_id = $1 AND is_active = true
                        ORDER BY updated_at DESC
                        LIMIT $2
                    """, project_id, limit)
                else:
                    rows = await conn.fetch("""
                        SELECT * FROM agent_working_memory 
                        WHERE project_id = $1
                        ORDER BY updated_at DESC
                        LIMIT $2
                    """, project_id, limit)
                
                return [WorkingMemorySession.from_db_row(dict(row)) for row in rows]
                
            except Exception as e:
                logger.error(f"Failed to get sessions for project {project_id}: {e}")
                raise
    
    async def get_session_count(self, project_id: Optional[str] = None, active_only: bool = True) -> int:
        """Get total session count"""
        if not self._pool:
            raise RuntimeError("WorkingMemory not initialized")
        
        async with self._pool.acquire() as conn:
            try:
                if project_id:
                    if active_only:
                        count = await conn.fetchval(
                            "SELECT COUNT(*) FROM agent_working_memory WHERE project_id = $1 AND is_active = true",
                            project_id
                        )
                    else:
                        count = await conn.fetchval(
                            "SELECT COUNT(*) FROM agent_working_memory WHERE project_id = $1",
                            project_id
                        )
                else:
                    if active_only:
                        count = await conn.fetchval("SELECT COUNT(*) FROM agent_working_memory WHERE is_active = true")
                    else:
                        count = await conn.fetchval("SELECT COUNT(*) FROM agent_working_memory")
                
                return count
                
            except Exception as e:
                logger.error(f"Failed to get session count: {e}")
                raise
    
    async def health_check(self) -> bool:
        """Check database connectivity and table access"""
        if not self._pool:
            return False
        
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1 FROM agent_working_memory LIMIT 1")
                return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False