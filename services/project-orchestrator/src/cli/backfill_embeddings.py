#!/usr/bin/env python3
"""
CLI tool for manual embedding backfill operations.

Usage:
    python -m cli.backfill_embeddings [options]
    
Examples:
    # Backfill all missing embeddings
    python -m cli.backfill_embeddings
    
    # Backfill maximum 20 episodes
    python -m cli.backfill_embeddings --max-episodes 20
    
    # Use custom batch size
    python -m cli.backfill_embeddings --batch-size 5
    
    # Check status only (no processing)
    python -m cli.backfill_embeddings --status-only
"""

import argparse
import asyncio
import sys
import logging
from typing import Optional

# Configure logging for CLI
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def check_backfill_status():
    """Check how many episodes need embeddings."""
    from memory.agent_memory_system import AgentMemorySystem
    from services.embedding_backfill_service import EmbeddingBackfillService
    
    try:
        # Initialize memory system
        memory_system = AgentMemorySystem()
        await memory_system.initialize()
        
        # Create backfill service
        backfill_service = EmbeddingBackfillService(
            memory_system.agent_memory_store,
            memory_system.embedding_client,
            batch_size=1  # Small batch for status check
        )
        
        # Find episodes needing embeddings
        episodes = await backfill_service.find_episodes_needing_embeddings()
        
        print(f"\n📊 EMBEDDING BACKFILL STATUS")
        print(f"═══════════════════════════")
        print(f"Episodes needing embeddings: {len(episodes)}")
        
        if episodes:
            print(f"\nEpisodes without embeddings:")
            for i, episode in enumerate(episodes[:10]):  # Show first 10
                print(f"  {i+1}. {episode['episode_id']} (Project: {episode['project_id']})")
            
            if len(episodes) > 10:
                print(f"  ... and {len(episodes) - 10} more")
        else:
            print("✅ All episodes have embeddings!")
        
        return len(episodes)
        
    except Exception as e:
        logger.error(f"Failed to check backfill status: {e}")
        raise
    finally:
        if 'memory_system' in locals():
            await memory_system.close()

async def run_backfill(max_episodes: Optional[int] = None, batch_size: int = 10):
    """Run embedding backfill process."""
    from memory.agent_memory_system import AgentMemorySystem
    from services.embedding_backfill_service import EmbeddingBackfillService
    
    try:
        # Initialize memory system
        logger.info("Initializing agent memory system...")
        memory_system = AgentMemorySystem()
        await memory_system.initialize()
        
        # Create backfill service
        backfill_service = EmbeddingBackfillService(
            memory_system.agent_memory_store,
            memory_system.embedding_client,
            batch_size
        )
        
        print(f"\n🚀 STARTING EMBEDDING BACKFILL")
        print(f"═════════════════════════════")
        print(f"Max episodes: {max_episodes or 'All'}")
        print(f"Batch size: {batch_size}")
        print()
        
        # Run backfill
        results = await backfill_service.run_backfill(max_episodes)
        
        print(f"\n✅ BACKFILL COMPLETED")
        print(f"═══════════════════")
        print(f"Episodes processed: {results['processed']}")
        print(f"Successful: {results['success']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped: {results['skipped']}")
        
        if results['failed'] > 0:
            print(f"\n⚠️  {results['failed']} episodes failed to process")
            print("Check logs for details")
            
        return results
        
    except Exception as e:
        logger.error(f"Backfill process failed: {e}")
        raise
    finally:
        if 'memory_system' in locals():
            await memory_system.close()

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Manual embedding backfill tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check status only
    python -m cli.backfill_embeddings --status-only
    
    # Backfill all missing embeddings
    python -m cli.backfill_embeddings
    
    # Backfill maximum 20 episodes with batch size 5
    python -m cli.backfill_embeddings --max-episodes 20 --batch-size 5
        """
    )
    
    parser.add_argument(
        '--max-episodes',
        type=int,
        help='Maximum number of episodes to process (default: all)',
        default=None
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        help='Number of episodes to process in each batch (default: 10)',
        default=10
    )
    
    parser.add_argument(
        '--status-only',
        action='store_true',
        help='Only check status, do not process episodes'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate arguments
    if args.batch_size < 1:
        print("Error: batch-size must be at least 1")
        sys.exit(1)
    
    if args.max_episodes is not None and args.max_episodes < 1:
        print("Error: max-episodes must be at least 1")
        sys.exit(1)
    
    try:
        if args.status_only:
            # Status check only
            pending_count = asyncio.run(check_backfill_status())
            sys.exit(0 if pending_count == 0 else 1)
        else:
            # Run backfill
            results = asyncio.run(run_backfill(args.max_episodes, args.batch_size))
            
            # Exit with appropriate code
            if results['failed'] > 0:
                sys.exit(1)  # Some failures
            else:
                sys.exit(0)  # Success
                
    except KeyboardInterrupt:
        print("\n⏹️  Backfill interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Backfill failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()