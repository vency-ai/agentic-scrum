#!/usr/bin/env python3
"""
Strategy Evolution CLI Runner

This script runs the daily strategy evolution process as a Kubernetes CronJob.
It extracts patterns from successful episodes, generates new strategies, and optimizes existing ones.
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any

# Add src to Python path for imports
sys.path.insert(0, '/app/src')

from memory.agent_memory_store import AgentMemoryStore
from memory.knowledge_store import KnowledgeStore
from memory.embedding_client import EmbeddingClient
from services.strategy_evolver import StrategyEvolver
from config.feature_flags import FeatureFlags

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

class StrategyEvolutionRunner:
    """CLI runner for strategy evolution process"""
    
    def __init__(self):
        self.memory_store = None
        self.knowledge_store = None
        self.embedding_client = None
        self.strategy_evolver = None
        
    async def initialize_components(self):
        """Initialize required components for strategy evolution"""
        try:
            # Get database connection configuration
            db_connection_string = os.getenv(
                'AGENT_MEMORY_DB_CONNECTION_STRING',
                'postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory'
            )
            min_connections = int(os.getenv('AGENT_MEMORY_DB_MIN_CONNECTIONS', '2'))
            max_connections = int(os.getenv('AGENT_MEMORY_DB_MAX_CONNECTIONS', '10'))
            
            logger.info(f"Initializing database connections: {db_connection_string}")
            
            # Initialize memory store
            self.memory_store = AgentMemoryStore(connection_string=db_connection_string)
            await self.memory_store.initialize(min_connections, max_connections)
            logger.info("Agent memory store initialized")
            
            # Initialize knowledge store
            self.knowledge_store = KnowledgeStore(connection_string=db_connection_string)
            await self.knowledge_store.initialize(min_connections, max_connections)
            logger.info("Knowledge store initialized")
            
            # Initialize embedding client
            embedding_service_url = os.getenv(
                'EMBEDDING_SERVICE_URL',
                'http://embedding-service.dsm.svc.cluster.local'
            )
            self.embedding_client = EmbeddingClient(service_url=embedding_service_url)
            logger.info(f"Embedding client initialized: {embedding_service_url}")
            
            # Initialize feature flags
            feature_flags = FeatureFlags()
            # Feature flags are configured via config file or environment variables
            # No need to override here as FeatureFlags class handles environment variables automatically
            
            # Initialize strategy evolver
            self.strategy_evolver = StrategyEvolver(
                memory_store=self.memory_store,
                knowledge_store=self.knowledge_store,
                feature_flags=feature_flags
            )
            
            # Configure evolution parameters from environment
            min_episodes = int(os.getenv('MIN_EPISODES_FOR_EVOLUTION', '10'))
            pattern_days = int(os.getenv('PATTERN_EXTRACTION_DAYS', '30'))
            max_strategies = int(os.getenv('MAX_STRATEGIES_PER_EVOLUTION', '20'))
            
            self.strategy_evolver.min_episodes_for_evolution = min_episodes
            self.strategy_evolver.pattern_extraction_days = pattern_days
            self.strategy_evolver.max_strategies_per_evolution = max_strategies
            
            logger.info(f"Strategy evolver configured: min_episodes={min_episodes}, "
                       f"pattern_days={pattern_days}, max_strategies={max_strategies}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}", exc_info=True)
            return False
    
    async def run_evolution(self) -> Dict[str, Any]:
        """Run the daily strategy evolution process"""
        logger.info("Starting daily strategy evolution process")
        start_time = datetime.utcnow()
        
        try:
            # Run the evolution
            evolution_results = await self.strategy_evolver.run_daily_evolution()
            
            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()
            evolution_results['cli_execution_duration_seconds'] = duration
            
            # Log results
            status = evolution_results.get('status', 'unknown')
            logger.info(f"Strategy evolution completed with status: {status}")
            
            if status == 'completed':
                summary = evolution_results.get('summary', {})
                logger.info(
                    f"Evolution summary: {summary.get('patterns_extracted', 0)} patterns extracted, "
                    f"{summary.get('strategies_generated', 0)} strategies generated, "
                    f"{summary.get('strategies_optimized', 0)} strategies optimized, "
                    f"{summary.get('strategies_deactivated', 0)} strategies deactivated"
                )
            elif status == 'failed':
                logger.error(f"Evolution failed: {evolution_results.get('failure_reason', 'unknown')}")
            elif status == 'disabled':
                logger.info("Strategy evolution is disabled by feature flag")
            
            return evolution_results
            
        except Exception as e:
            logger.error(f"Strategy evolution failed with exception: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'cli_execution_duration_seconds': (datetime.utcnow() - start_time).total_seconds()
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on strategy evolution components"""
        logger.info("Performing strategy evolution health check")
        
        try:
            health_status = await self.strategy_evolver.health_check()
            
            if health_status.get('overall_status') == 'healthy':
                logger.info("Strategy evolution system health check passed")
            else:
                logger.warning(f"Strategy evolution system health check failed: {health_status}")
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {
                'overall_status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if self.memory_store:
                await self.memory_store.close()
                logger.info("Memory store closed")
            
            if self.knowledge_store:
                await self.knowledge_store.close()
                logger.info("Knowledge store closed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

async def main():
    """Main entry point for strategy evolution CLI"""
    logger.info("Strategy Evolution CLI starting up")
    
    runner = StrategyEvolutionRunner()
    exit_code = 0
    
    try:
        # Initialize components
        logger.info("Initializing strategy evolution components...")
        if not await runner.initialize_components():
            logger.error("Failed to initialize strategy evolution components")
            return 1
        
        # Perform health check first
        logger.info("Performing health check...")
        health_status = await runner.health_check()
        if health_status.get('overall_status') not in ['healthy', 'operational']:
            logger.error(f"Health check failed: {health_status}")
            return 1
        
        # Run strategy evolution
        logger.info("Running strategy evolution process...")
        results = await runner.run_evolution()
        
        # Log final results as JSON for easy parsing
        logger.info(f"Strategy evolution results: {json.dumps(results, indent=2, default=str)}")
        
        # Determine exit code based on results
        status = results.get('status', 'unknown')
        if status == 'completed':
            exit_code = 0
        elif status == 'disabled':
            exit_code = 0  # Not an error, just disabled
        elif status in ['failed', 'error']:
            exit_code = 1
        else:
            exit_code = 2  # Unknown status
        
        logger.info(f"Strategy evolution CLI completed with exit code: {exit_code}")
        
    except Exception as e:
        logger.error(f"Strategy evolution CLI failed with unhandled exception: {e}", exc_info=True)
        exit_code = 1
        
    finally:
        # Always cleanup
        await runner.cleanup()
    
    return exit_code

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)