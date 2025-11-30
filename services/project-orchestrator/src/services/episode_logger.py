"""
Episode Logger Service

Provides asynchronous episode logging with embedding integration and fallback mechanisms.
Uses the existing AgentMemoryStore from CR_Agent_04_01 for database operations.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from uuid import UUID

from memory.models import Episode
from memory.agent_memory_store import AgentMemoryStore
from memory.embedding_client import EmbeddingClient
from validators.episode_validator import EpisodeValidator
from monitoring.agent_memory_metrics import (
    AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS,
    AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL
)

logger = logging.getLogger(__name__)

class EpisodeLogger:
    """
    Asynchronous episode logging service with embedding integration.
    
    Features:
    - Async logging to prevent blocking orchestration responses
    - Integration with existing AgentMemoryStore connection pool
    - Embedding fallback using EmbeddingClient circuit breaker
    - Episode quality validation before storage
    - Comprehensive Prometheus metrics
    """
    
    def __init__(
        self, 
        memory_store: AgentMemoryStore,
        embedding_client: EmbeddingClient,
        validator: Optional[EpisodeValidator] = None,
        enable_validation: bool = True,
        embedding_timeout: float = 5.0
    ):
        """
        Initialize the episode logger.
        
        Args:
            memory_store: AgentMemoryStore instance for database operations
            embedding_client: EmbeddingClient for vector generation
            validator: Episode validator (creates default if None)
            enable_validation: Whether to validate episodes before storage
            embedding_timeout: Timeout for embedding generation
        """
        self.memory_store = memory_store
        self.embedding_client = embedding_client
        self.validator = validator or EpisodeValidator()
        self.enable_validation = enable_validation
        self.embedding_timeout = embedding_timeout
        
        # Metrics tracking
        self._episodes_logged = 0
        self._episodes_failed = 0
        self._embeddings_generated = 0
        self._embeddings_failed = 0
        
        logger.info(f"EpisodeLogger initialized (validation: {enable_validation})")
    
    async def log_episode_async(self, episode: Episode) -> Optional[UUID]:
        """
        Log an episode asynchronously without blocking caller.
        
        Args:
            episode: Episode to log
            
        Returns:
            Task that will complete with episode_id or None if failed
        """
        # Fire-and-forget async logging
        task = asyncio.create_task(self._log_episode_internal(episode))
        logger.debug(f"Started async episode logging for project {episode.project_id}")
        return task
    
    async def log_episode_sync(self, episode: Episode) -> Optional[UUID]:
        """
        Log an episode synchronously (for testing/special cases).
        
        Args:
            episode: Episode to log
            
        Returns:
            Episode ID if successful, None if failed
        """
        return await self._log_episode_internal(episode)
    
    async def _log_episode_internal(self, episode: Episode) -> Optional[UUID]:
        """Internal episode logging implementation."""
        start_time = time.monotonic()
        operation_label = "episode_storage"
        
        try:
            # Step 1: Validate episode quality if enabled
            if self.enable_validation:
                is_valid, quality_score, issues = self.validator.validate_episode(episode)
                logger.debug(
                    f"Episode validation for {episode.project_id}: "
                    f"valid={is_valid}, score={quality_score:.3f}"
                )
                
                if not is_valid:
                    logger.warning(
                        f"Episode rejected due to quality (score: {quality_score:.3f}): {issues}"
                    )
                    self._episodes_failed += 1
                    return None
            
            # Step 2: Generate embedding with fallback
            embedding_vector = await self._generate_embedding_with_fallback(episode)
            
            # Step 3: Store episode using AgentMemoryStore
            episode_id = await self.memory_store.store_episode(episode)
            
            # Step 4: Update embedding if generated successfully
            if embedding_vector and episode_id:
                try:
                    await self.memory_store.update_episode_embedding(episode_id, embedding_vector)
                    self._embeddings_generated += 1
                    logger.debug(f"Episode {episode_id} stored with embedding")
                except Exception as e:
                    logger.error(f"Failed to update embedding for episode {episode_id}: {e}")
                    # Episode is still stored, just without embedding
            
            self._episodes_logged += 1
            logger.info(
                f"Episode logged successfully for project {episode.project_id}: {episode_id}"
            )
            
            return episode_id
            
        except Exception as e:
            self._episodes_failed += 1
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation=operation_label).inc()
            logger.error(f"Failed to log episode for project {episode.project_id}: {e}")
            return None
            
        finally:
            # Record latency metric
            latency = time.monotonic() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation=operation_label).observe(latency)
    
    async def _generate_embedding_with_fallback(self, episode: Episode) -> Optional[List[float]]:
        """
        Generate embedding for episode with graceful fallback.
        
        Args:
            episode: Episode to generate embedding for
            
        Returns:
            Embedding vector or None if generation failed
        """
        try:
            # Create text representation of episode for embedding
            episode_text = self._create_episode_text(episode)
            
            # Use EmbeddingClient with built-in circuit breaker and timeout
            embedding_vector = await asyncio.wait_for(
                self.embedding_client.generate_embedding(episode_text),
                timeout=self.embedding_timeout
            )
            
            logger.debug(f"Generated embedding for episode (length: {len(embedding_vector)})")
            return embedding_vector
            
        except asyncio.TimeoutError:
            logger.warning(f"Embedding generation timed out after {self.embedding_timeout}s")
            self._embeddings_failed += 1
            return None
            
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            self._embeddings_failed += 1
            return None
    
    def _create_episode_text(self, episode: Episode) -> str:
        """
        Create text representation of episode for embedding generation.
        
        Args:
            episode: Episode to convert to text
            
        Returns:
            Text representation suitable for embedding
        """
        parts = [
            f"Project: {episode.project_id}",
            f"Decision Source: {episode.decision_source}",
            f"Control Mode: {episode.control_mode}"
        ]
        
        # Add perception context
        if episode.perception:
            perception_text = self._dict_to_text(episode.perception, "Context")
            parts.append(perception_text)
        
        # Add reasoning details
        if episode.reasoning:
            reasoning_text = self._dict_to_text(episode.reasoning, "Analysis")
            parts.append(reasoning_text)
        
        # Add action details
        if episode.action:
            action_text = self._dict_to_text(episode.action, "Actions")
            parts.append(action_text)
        
        # Add outcome if available
        if episode.outcome:
            outcome_text = self._dict_to_text(episode.outcome, "Results")
            parts.append(outcome_text)
        
        return " | ".join(parts)
    
    def _dict_to_text(self, data: Dict[str, Any], prefix: str) -> str:
        """Convert dictionary data to readable text."""
        if not data:
            return f"{prefix}: none"
        
        items = []
        for key, value in data.items():
            if isinstance(value, dict):
                items.append(f"{key}: {len(value)} items")
            elif isinstance(value, list):
                items.append(f"{key}: {len(value)} entries")
            elif isinstance(value, bool):
                items.append(f"{key}: {'yes' if value else 'no'}")
            else:
                items.append(f"{key}: {str(value)[:50]}")  # Truncate long values
        
        return f"{prefix}: {', '.join(items)}"
    
    async def update_episode_outcome(
        self, 
        episode_id: UUID, 
        outcome: Dict[str, Any], 
        quality: Optional[float] = None
    ) -> bool:
        """
        Update an existing episode with outcome data.
        
        Args:
            episode_id: ID of episode to update
            outcome: Outcome data to add
            quality: Quality score for the outcome
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            await self.memory_store.update_episode_outcome(episode_id, outcome, quality)
            logger.info(f"Updated outcome for episode {episode_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update outcome for episode {episode_id}: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get logging statistics.
        
        Returns:
            Dictionary with logging statistics
        """
        total_attempts = self._episodes_logged + self._episodes_failed
        success_rate = (self._episodes_logged / total_attempts) if total_attempts > 0 else 0.0
        embedding_rate = (self._embeddings_generated / total_attempts) if total_attempts > 0 else 0.0
        
        return {
            'episodes_logged': self._episodes_logged,
            'episodes_failed': self._episodes_failed,
            'total_attempts': total_attempts,
            'success_rate': success_rate,
            'embeddings_generated': self._embeddings_generated,
            'embeddings_failed': self._embeddings_failed,
            'embedding_success_rate': embedding_rate,
            'validation_enabled': self.enable_validation
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of episode logger components.
        
        Returns:
            Health status dictionary
        """
        health = {
            'episode_logger': 'ok',
            'memory_store': 'unknown',
            'embedding_client': 'unknown',
            'validator': 'ok' if self.validator else 'disabled'
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
        
        # Overall status
        component_statuses = [v for k, v in health.items() if k != 'validator']
        health['overall'] = 'ok' if all(status == 'ok' for status in component_statuses) else 'degraded'
        
        return health

# Convenience function for dependency injection
def create_episode_logger(
    memory_store: AgentMemoryStore,
    embedding_client: EmbeddingClient,
    enable_validation: bool = True
) -> EpisodeLogger:
    """Create episode logger with default configuration."""
    return EpisodeLogger(
        memory_store=memory_store,
        embedding_client=embedding_client,
        enable_validation=enable_validation
    )