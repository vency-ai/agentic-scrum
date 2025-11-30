"""
Embedding Backfill Service

Identifies and processes episodes that are missing embeddings, generating
vector representations for complete similarity search capabilities.
"""

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from memory.agent_memory_store import AgentMemoryStore
from memory.embedding_client import EmbeddingClient
from monitoring.agent_memory_metrics import (
    AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS,
    AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL,
    EMBEDDING_BACKFILL_EPISODES_PROCESSED_TOTAL,
    EMBEDDING_BACKFILL_RUN_DURATION_SECONDS,
    EMBEDDING_BACKFILL_EPISODES_PENDING,
    EMBEDDING_BACKFILL_LAST_RUN_TIMESTAMP,
    EMBEDDING_BACKFILL_BATCH_SIZE
)

logger = logging.getLogger(__name__)

class EmbeddingBackfillService:
    """Service to backfill missing embeddings for stored episodes."""
    
    def __init__(self, memory_store: AgentMemoryStore, embedding_client: EmbeddingClient, batch_size: int = 10):
        """
        Initialize backfill service.
        
        Args:
            memory_store: Agent memory store for database operations
            embedding_client: Client for generating embeddings
            batch_size: Number of episodes to process in each batch
        """
        self.memory_store = memory_store
        self.embedding_client = embedding_client
        self.batch_size = batch_size
        
        # Set batch size metric
        EMBEDDING_BACKFILL_BATCH_SIZE.set(batch_size)
        
    async def find_episodes_needing_embeddings(self) -> List[Dict[str, Any]]:
        """Find all episodes that don't have embeddings."""
        query = """
        SELECT episode_id, project_id, perception, reasoning, action
        FROM agent_episodes
        WHERE embedding IS NULL
        ORDER BY timestamp ASC
        """
        
        start_time = time.time()
        try:
            async with self.memory_store._pool.acquire() as conn:
                rows = await conn.fetch(query)
                episodes = [dict(row) for row in rows]
                
            duration = time.time() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation="backfill_find").observe(duration)
            
            # Update pending episodes metric
            EMBEDDING_BACKFILL_EPISODES_PENDING.set(len(episodes))
            
            logger.info(f"Found {len(episodes)} episodes needing embeddings")
            return episodes
            
        except Exception as e:
            duration = time.time() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation="backfill_find").observe(duration)
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation="backfill_find").inc()
            logger.error(f"Failed to find episodes needing embeddings: {e}")
            raise
    
    async def generate_episode_embedding(self, episode: Dict[str, Any]) -> Optional[List[float]]:
        """Generate embedding for a single episode."""
        try:
            # Create episode text for embedding
            episode_text = self._create_episode_text(episode)
            
            # Generate embedding
            embedding = await self.embedding_client.generate_embedding(episode_text)
            
            if embedding:
                logger.debug(f"Generated embedding for episode {episode['episode_id']}")
                return embedding
            else:
                logger.warning(f"Failed to generate embedding for episode {episode['episode_id']}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating embedding for episode {episode['episode_id']}: {e}")
            return None
    
    def _create_episode_text(self, episode: Dict[str, Any]) -> str:
        """Create text representation of episode for embedding."""
        parts = []
        
        # Add project context
        parts.append(f"Project: {episode['project_id']}")
        
        # Add perception data
        if episode['perception']:
            perception = episode['perception']
            if isinstance(perception, dict):
                if 'backlog_tasks' in perception:
                    parts.append(f"Backlog tasks: {perception['backlog_tasks']}")
                if 'team_size' in perception:
                    parts.append(f"Team size: {perception['team_size']}")
                if 'active_sprints' in perception:
                    parts.append(f"Active sprints: {perception['active_sprints']}")
        
        # Add reasoning
        if episode['reasoning']:
            reasoning = episode['reasoning']
            if isinstance(reasoning, dict) and 'decision_rationale' in reasoning:
                parts.append(f"Decision rationale: {reasoning['decision_rationale']}")
        
        # Add action taken
        if episode['action']:
            action = episode['action']
            if isinstance(action, dict):
                if 'decision_type' in action:
                    parts.append(f"Decision type: {action['decision_type']}")
                if 'tasks_assigned' in action:
                    parts.append(f"Tasks assigned: {action['tasks_assigned']}")
        
        return " | ".join(parts)
    
    async def update_episode_embedding(self, episode_id: str, embedding: List[float]) -> bool:
        """Update episode with generated embedding."""
        query = """
        UPDATE agent_episodes 
        SET embedding = $1::vector(1024)
        WHERE episode_id = $2
        """
        
        start_time = time.time()
        try:
            # Convert embedding to vector format
            vector_str = '[' + ','.join(map(str, embedding)) + ']'
            
            async with self.memory_store._pool.acquire() as conn:
                await conn.execute(query, vector_str, episode_id)
                
            duration = time.time() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation="backfill_update").observe(duration)
            
            logger.debug(f"Updated embedding for episode {episode_id}")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS.labels(operation="backfill_update").observe(duration)
            AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL.labels(operation="backfill_update").inc()
            logger.error(f"Failed to update embedding for episode {episode_id}: {e}")
            return False
    
    async def process_batch(self, episodes: List[Dict[str, Any]]) -> Dict[str, int]:
        """Process a batch of episodes for embedding generation."""
        results = {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        for episode in episodes:
            results['processed'] += 1
            
            try:
                # Generate embedding
                embedding = await self.generate_episode_embedding(episode)
                
                if embedding:
                    # Update episode with embedding
                    success = await self.update_episode_embedding(episode['episode_id'], embedding)
                    
                    if success:
                        results['success'] += 1
                        EMBEDDING_BACKFILL_EPISODES_PROCESSED_TOTAL.labels(result="success").inc()
                        logger.info(f"Successfully backfilled embedding for episode {episode['episode_id']}")
                    else:
                        results['failed'] += 1
                        EMBEDDING_BACKFILL_EPISODES_PROCESSED_TOTAL.labels(result="failed").inc()
                        logger.warning(f"Failed to update embedding for episode {episode['episode_id']}")
                else:
                    results['failed'] += 1
                    EMBEDDING_BACKFILL_EPISODES_PROCESSED_TOTAL.labels(result="failed").inc()
                    logger.warning(f"Failed to generate embedding for episode {episode['episode_id']}")
                    
            except Exception as e:
                results['failed'] += 1
                EMBEDDING_BACKFILL_EPISODES_PROCESSED_TOTAL.labels(result="failed").inc()
                logger.error(f"Error processing episode {episode['episode_id']}: {e}")
        
        return results
    
    async def run_backfill(self, max_episodes: Optional[int] = None) -> Dict[str, int]:
        """
        Run complete backfill process.
        
        Args:
            max_episodes: Maximum number of episodes to process (None for all)
            
        Returns:
            Dictionary with processing statistics
        """
        logger.info("Starting embedding backfill process")
        start_time = time.time()
        
        total_results = {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        # Track duration with Prometheus
        with EMBEDDING_BACKFILL_RUN_DURATION_SECONDS.time():
            try:
                # Find episodes needing embeddings
                episodes = await self.find_episodes_needing_embeddings()
                
                if not episodes:
                    logger.info("No episodes need embedding backfill")
                    # Update last run timestamp even for empty runs
                    EMBEDDING_BACKFILL_LAST_RUN_TIMESTAMP.set(time.time())
                    return total_results
                
                # Apply max episodes limit if specified
                if max_episodes and len(episodes) > max_episodes:
                    episodes = episodes[:max_episodes]
                    logger.info(f"Limited processing to {max_episodes} episodes")
                
                # Process in batches
                for i in range(0, len(episodes), self.batch_size):
                    batch = episodes[i:i + self.batch_size]
                    batch_num = (i // self.batch_size) + 1
                    total_batches = (len(episodes) + self.batch_size - 1) // self.batch_size
                    
                    logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} episodes)")
                    
                    batch_results = await self.process_batch(batch)
                    
                    # Update totals
                    for key in total_results:
                        total_results[key] += batch_results[key]
                    
                    # Log batch results
                    logger.info(f"Batch {batch_num} complete: {batch_results}")
                    
                    # Small delay between batches to avoid overwhelming services
                    if i + self.batch_size < len(episodes):
                        await asyncio.sleep(0.5)
                
                duration = time.time() - start_time
                logger.info(f"Backfill process completed in {duration:.2f}s: {total_results}")
                
                # Update last successful run timestamp
                EMBEDDING_BACKFILL_LAST_RUN_TIMESTAMP.set(time.time())
                
            except Exception as e:
                logger.error(f"Backfill process failed: {e}")
                raise
        
        return total_results

# CLI interface for manual backfill execution
async def run_manual_backfill(max_episodes: Optional[int] = None, batch_size: int = 10):
    """Run manual backfill from command line."""
    from memory.agent_memory_system import AgentMemorySystem
    
    logger.info("Initializing agent memory system for backfill")
    
    try:
        # Initialize memory system
        memory_system = AgentMemorySystem()
        await memory_system.initialize()
        
        # Create backfill service
        backfill_service = EmbeddingBackfillService(
            memory_system.agent_memory_store,
            memory_system.embedding_client,
            batch_size
        )
        
        # Run backfill
        results = await backfill_service.run_backfill(max_episodes)
        
        print(f"Backfill completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Manual backfill failed: {e}")
        raise
    finally:
        if 'memory_system' in locals():
            await memory_system.close()

if __name__ == "__main__":
    import sys
    
    # Simple CLI parsing
    max_episodes = None
    batch_size = 10
    
    if len(sys.argv) > 1:
        try:
            max_episodes = int(sys.argv[1])
        except ValueError:
            print("Usage: python embedding_backfill_service.py [max_episodes] [batch_size]")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        try:
            batch_size = int(sys.argv[2])
        except ValueError:
            print("Usage: python embedding_backfill_service.py [max_episodes] [batch_size]")
            sys.exit(1)
    
    # Run backfill
    asyncio.run(run_manual_backfill(max_episodes, batch_size))