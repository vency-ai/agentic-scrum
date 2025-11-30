"""
Episode Retriever Service

Provides episode retrieval capabilities with similarity search, caching,
and timeout protection for decision engine integration.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta

from memory.models import Episode
from memory.agent_memory_store import AgentMemoryStore
from memory.embedding_client import EmbeddingClient
from monitoring.agent_memory_metrics import (
    AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS,
    AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL
)

logger = logging.getLogger(__name__)

class EpisodeCache:
    """Simple in-memory cache for retrieved episodes."""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        """
        Initialize episode cache.
        
        Args:
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for cached entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[List[Episode], datetime]] = {}
        
    def get(self, cache_key: str) -> Optional[List[Episode]]:
        """Get episodes from cache if valid."""
        if cache_key in self._cache:
            episodes, cached_at = self._cache[cache_key]
            if datetime.utcnow() - cached_at < timedelta(seconds=self.ttl_seconds):
                logger.debug(f"Cache hit for key: {cache_key[:50]}...")
                return episodes
            else:
                # Expired entry
                del self._cache[cache_key]
                logger.debug(f"Cache expired for key: {cache_key[:50]}...")
        
        return None
    
    def put(self, cache_key: str, episodes: List[Episode]) -> None:
        """Put episodes in cache."""
        # Simple LRU: remove oldest if at capacity
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        
        self._cache[cache_key] = (episodes, datetime.utcnow())
        logger.debug(f"Cached {len(episodes)} episodes for key: {cache_key[:50]}...")
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("Episode cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = datetime.utcnow()
        valid_entries = 0
        expired_entries = 0
        
        for _, (_, cached_at) in self._cache.items():
            if now - cached_at < timedelta(seconds=self.ttl_seconds):
                valid_entries += 1
            else:
                expired_entries += 1
        
        return {
            'total_entries': len(self._cache),
            'valid_entries': valid_entries,
            'expired_entries': expired_entries,
            'max_size': self.max_size,
            'ttl_seconds': self.ttl_seconds
        }

class EpisodeRetriever:
    """
    Retrieves relevant episodes for decision making with caching and timeout protection.
    
    Features:
    - Similarity-based episode retrieval using vector embeddings
    - In-memory caching for performance optimization
    - Timeout protection to prevent blocking decision engine
    - Flexible filtering by project, time range, quality scores
    - Comprehensive metrics collection
    """
    
    def __init__(
        self,
        memory_store: AgentMemoryStore,
        embedding_client: EmbeddingClient,
        cache_size: int = 100,
        cache_ttl: int = 300,
        default_timeout: float = 3.0,
        min_similarity: float = 0.7
    ):
        """
        Initialize the episode retriever.
        
        Args:
            memory_store: AgentMemoryStore for database operations
            embedding_client: EmbeddingClient for query embeddings
            cache_size: Maximum number of cached queries
            cache_ttl: Cache time-to-live in seconds
            default_timeout: Default timeout for retrieval operations
            min_similarity: Minimum similarity threshold for relevant episodes
        """
        self.memory_store = memory_store
        self.embedding_client = embedding_client
        self.cache = EpisodeCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self.default_timeout = default_timeout
        self.min_similarity = min_similarity
        
        # Metrics tracking
        self._queries_executed = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._timeouts = 0
        self._errors = 0
        
        logger.info(
            f"EpisodeRetriever initialized (cache_size: {cache_size}, "
            f"timeout: {default_timeout}s, min_similarity: {min_similarity})"
        )
    
    async def find_similar_episodes(
        self,
        query_context: Dict[str, Any],
        project_id: Optional[str] = None,
        limit: int = 10,
        timeout: Optional[float] = None,
        min_quality: Optional[float] = None
    ) -> List[Episode]:
        """
        Find episodes similar to the given query context.
        
        Args:
            query_context: Context data to find similar episodes for
            project_id: Filter by specific project (None for all projects)
            limit: Maximum number of episodes to return
            timeout: Operation timeout in seconds
            min_quality: Minimum episode quality score filter
            
        Returns:
            List of similar episodes ordered by similarity
        """
        start_time = time.monotonic()
        operation_label = "episode_retrieval"
        timeout = timeout or self.default_timeout
        
        try:
            # Create cache key
            cache_key = self._create_cache_key(query_context, project_id, limit, min_quality)
            
            # Check cache first
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                self._cache_hits += 1
                logger.debug(f"Retrieved {len(cached_result)} episodes from cache")
                return cached_result
            
            self._cache_misses += 1
            
            # Perform retrieval with timeout
            episodes = await asyncio.wait_for(
                self._retrieve_similar_episodes(query_context, project_id, limit, min_quality),
                timeout=timeout
            )
            
            # Cache the result
            self.cache.put(cache_key, episodes)
            
            self._queries_executed += 1
            logger.info(f"Retrieved {len(episodes)} similar episodes for project {project_id}")
            
            return episodes
            
        except asyncio.TimeoutError:
            self._timeouts += 1
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation=operation_label).inc()
            logger.warning(f"Episode retrieval timed out after {timeout}s")
            return []  # Return empty list on timeout
            
        except Exception as e:
            self._errors += 1
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation=operation_label).inc()
            logger.error(f"Failed to retrieve similar episodes: {e}")
            return []  # Return empty list on error
            
        finally:
            # Record latency metric
            latency = time.monotonic() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation=operation_label).observe(latency)
    
    async def _retrieve_similar_episodes(
        self,
        query_context: Dict[str, Any],
        project_id: Optional[str],
        limit: int,
        min_quality: Optional[float]
    ) -> List[Episode]:
        """Internal method to retrieve similar episodes."""
        
        # Step 1: Generate embedding for query context
        query_text = self._context_to_text(query_context)
        query_embedding = await self.embedding_client.generate_embedding(query_text)
        
        if not query_embedding:
            logger.warning("Failed to generate query embedding, falling back to recent episodes")
            return await self._get_recent_episodes(project_id, limit, min_quality)
        
        # Step 2: Search for similar episodes using vector similarity
        episodes = await self.memory_store.find_similar_episodes(
            query_embedding=query_embedding,
            project_id=project_id,
            limit=limit * 2,  # Get more candidates for filtering
            min_similarity=self.min_similarity
        )
        
        # Step 3: Apply quality filter if specified
        if min_quality is not None:
            episodes = [ep for ep in episodes if self._get_episode_quality(ep) >= min_quality]
        
        # Step 4: Return top results
        return episodes[:limit]
    
    async def _get_recent_episodes(
        self,
        project_id: Optional[str],
        limit: int,
        min_quality: Optional[float]
    ) -> List[Episode]:
        """Fallback method to get recent episodes when embedding fails."""
        
        episodes = await self.memory_store.get_recent_episodes(
            project_id=project_id,
            limit=limit * 2 if min_quality is not None else limit
        )
        
        # Apply quality filter if specified
        if min_quality is not None:
            episodes = [ep for ep in episodes if self._get_episode_quality(ep) >= min_quality]
            episodes = episodes[:limit]
        
        return episodes
    
    def _context_to_text(self, context: Dict[str, Any]) -> str:
        """Convert context dictionary to text for embedding generation."""
        parts = []
        
        # Add key context elements
        if 'project_data' in context:
            parts.append(f"Project: {context['project_data']}")
        
        if 'team_availability' in context:
            parts.append(f"Team: {context['team_availability']}")
        
        if 'backlog_summary' in context:
            parts.append(f"Backlog: {context['backlog_summary']}")
        
        if 'current_sprint_status' in context:
            parts.append(f"Sprint Status: {context['current_sprint_status']}")
        
        # Add any other relevant fields
        for key, value in context.items():
            if key not in ['project_data', 'team_availability', 'backlog_summary', 'current_sprint_status']:
                if isinstance(value, (str, int, float, bool)):
                    parts.append(f"{key}: {value}")
                elif isinstance(value, dict):
                    parts.append(f"{key}: {len(value)} items")
                elif isinstance(value, list):
                    parts.append(f"{key}: {len(value)} entries")
        
        return " | ".join(parts)
    
    def _create_cache_key(
        self,
        query_context: Dict[str, Any],
        project_id: Optional[str],
        limit: int,
        min_quality: Optional[float]
    ) -> str:
        """Create cache key from query parameters."""
        import hashlib
        import json
        
        # Create deterministic string representation
        cache_data = {
            'context': query_context,
            'project_id': project_id,
            'limit': limit,
            'min_quality': min_quality,
            'min_similarity': self.min_similarity
        }
        
        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_string.encode()).hexdigest()
    
    def _get_episode_quality(self, episode: Episode) -> float:
        """Get quality score for an episode."""
        if episode.outcome_quality is not None:
            return episode.outcome_quality
        
        # Fallback quality estimation based on data completeness
        quality = 0.0
        
        if episode.perception:
            quality += 0.25
        if episode.reasoning:
            quality += 0.25
        if episode.action:
            quality += 0.25
        if episode.outcome:
            quality += 0.25
        
        return quality
    
    async def get_episodes_by_project(
        self,
        project_id: str,
        limit: int = 50,
        min_quality: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Episode]:
        """
        Get episodes for a specific project with optional filtering.
        
        Args:
            project_id: Project to get episodes for
            limit: Maximum number of episodes to return
            min_quality: Minimum quality score filter
            start_date: Filter episodes after this date
            end_date: Filter episodes before this date
            
        Returns:
            List of episodes matching criteria
        """
        start_time = time.monotonic()
        operation_label = "project_episodes"
        
        try:
            episodes = await self.memory_store.get_episodes_by_project(
                project_id=project_id,
                limit=limit,
                start_date=start_date,
                end_date=end_date
            )
            
            # Apply quality filter if specified
            if min_quality is not None:
                episodes = [ep for ep in episodes if self._get_episode_quality(ep) >= min_quality]
            
            logger.info(f"Retrieved {len(episodes)} episodes for project {project_id}")
            return episodes
            
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation=operation_label).inc()
            logger.error(f"Failed to get episodes for project {project_id}: {e}")
            return []
            
        finally:
            latency = time.monotonic() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation=operation_label).observe(latency)
    
    async def get_episode_by_id(self, episode_id: UUID) -> Optional[Episode]:
        """
        Get a specific episode by ID.
        
        Args:
            episode_id: ID of episode to retrieve
            
        Returns:
            Episode if found, None otherwise
        """
        start_time = time.monotonic()
        operation_label = "episode_by_id"
        
        try:
            episode = await self.memory_store.get_episode_by_id(episode_id)
            
            if episode:
                logger.debug(f"Retrieved episode {episode_id}")
            else:
                logger.warning(f"Episode {episode_id} not found")
            
            return episode
            
        except Exception as e:
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation=operation_label).inc()
            logger.error(f"Failed to get episode {episode_id}: {e}")
            return None
            
        finally:
            latency = time.monotonic() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation=operation_label).observe(latency)
    
    def clear_cache(self) -> None:
        """Clear the episode cache."""
        self.cache.clear()
        logger.info("Episode retriever cache cleared")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get retriever statistics.
        
        Returns:
            Dictionary with retrieval statistics
        """
        cache_stats = self.cache.get_stats()
        
        total_queries = self._cache_hits + self._cache_misses
        cache_hit_rate = (self._cache_hits / total_queries) if total_queries > 0 else 0.0
        
        return {
            'queries_executed': self._queries_executed,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_rate': cache_hit_rate,
            'timeouts': self._timeouts,
            'errors': self._errors,
            'cache_stats': cache_stats,
            'config': {
                'default_timeout': self.default_timeout,
                'min_similarity': self.min_similarity
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of episode retriever components.
        
        Returns:
            Health status dictionary
        """
        health = {
            'episode_retriever': 'ok',
            'memory_store': 'unknown',
            'embedding_client': 'unknown',
            'cache': 'ok'
        }
        
        try:
            # Check memory store
            memory_health = await self.memory_store.health_check()
            health['memory_store'] = memory_health.get('status', 'error')
        except Exception as e:
            health['memory_store'] = f'error: {e}'
        
        try:
            # Check embedding client
            embedding_health = await self.embedding_client.health_check()
            health['embedding_client'] = 'ok' if embedding_health else 'error'
        except Exception as e:
            health['embedding_client'] = f'error: {e}'
        
        # Check cache stats
        cache_stats = self.cache.get_stats()
        if cache_stats['expired_entries'] > cache_stats['valid_entries']:
            health['cache'] = 'degraded'
        
        # Overall status
        component_statuses = [v for k, v in health.items() if k != 'cache']
        health['overall'] = 'ok' if all(status == 'ok' for status in component_statuses) else 'degraded'
        
        return health

# Convenience function for dependency injection
def create_episode_retriever(
    memory_store: AgentMemoryStore,
    embedding_client: EmbeddingClient,
    cache_size: int = 100,
    default_timeout: float = 3.0
) -> EpisodeRetriever:
    """Create episode retriever with default configuration."""
    return EpisodeRetriever(
        memory_store=memory_store,
        embedding_client=embedding_client,
        cache_size=cache_size,
        default_timeout=default_timeout
    )