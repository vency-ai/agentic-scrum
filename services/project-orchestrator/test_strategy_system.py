#!/usr/bin/env python3
"""
Test Strategy Evolution System

This script tests the Strategy Evolution Layer components to ensure they work correctly.
"""

import asyncio
import sys
import os
sys.path.insert(0, 'services/project-orchestrator/src')

from datetime import datetime
from uuid import uuid4
from memory.agent_memory_store import AgentMemoryStore
from memory.knowledge_store import KnowledgeStore
from memory.models import Episode, Strategy
from services.strategy.strategy_repository import StrategyRepository
from config.feature_flags import FeatureFlags

async def test_strategy_system():
    """Test the strategy evolution system"""
    print("🧪 Testing Strategy Evolution System...")
    
    # Database connection
    db_connection = "postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory"
    
    try:
        # Initialize components
        print("\n1. Initializing components...")
        memory_store = AgentMemoryStore(db_connection)
        await memory_store.initialize(min_connections=1, max_connections=2)
        print("   ✅ Memory store initialized")
        
        knowledge_store = KnowledgeStore(db_connection)
        await knowledge_store.initialize(min_connections=1, max_connections=2)
        print("   ✅ Knowledge store initialized")
        
        strategy_repository = StrategyRepository(knowledge_store)
        print("   ✅ Strategy repository initialized")
        
        # Test strategy creation
        print("\n2. Testing strategy creation...")
        test_pattern_data = {
            'strategy_type': 'context_based',
            'context_signature': 'small_team_high_velocity',
            'applicability_conditions': {
                'team_size': {'min': 2, 'max': 5},
                'velocity_trend': ['stable', 'increasing']
            },
            'decision_rules': [
                {
                    'rule_type': 'task_adjustments',
                    'adjustment_guidelines': {'increase_by': 1}
                }
            ],
            'confidence_factors': {
                'pattern_frequency_score': 0.8,
                'outcome_quality_score': 0.85,
                'consistency_score': 0.7,
                'evidence_strength_score': 0.6
            },
            'performance_expectations': {
                'expected_outcome_quality': 0.85,
                'success_probability': 0.8,
                'risk_level': 'low'
            }
        }
        
        strategy_id = await strategy_repository.create_strategy(
            pattern_data=test_pattern_data,
            confidence=0.75,
            description="Test strategy for small teams with high velocity",
            created_by="test_system"
        )
        
        print(f"   ✅ Strategy created with ID: {strategy_id}")
        
        # Test strategy retrieval
        print("\n3. Testing strategy retrieval...")
        retrieved_strategy = await strategy_repository.get_strategy(strategy_id)
        if retrieved_strategy:
            print(f"   ✅ Strategy retrieved: {retrieved_strategy.description}")
            print(f"   📊 Confidence: {retrieved_strategy.confidence:.2f}")
        else:
            print("   ❌ Failed to retrieve strategy")
            return False
        
        # Test active strategies listing
        print("\n4. Testing active strategies listing...")
        active_strategies = await strategy_repository.get_active_strategies(limit=10)
        print(f"   ✅ Found {len(active_strategies)} active strategies")
        
        # Test strategy performance logging (simulate)
        print("\n5. Testing strategy performance logging...")
        
        # Create a test episode first
        test_episode = Episode(
            episode_id=uuid4(),
            project_id="TEST-001",
            timestamp=datetime.utcnow(),
            perception={"test": "data"},
            reasoning={"analysis": "test reasoning"},
            action={"task_count": 5},
            outcome={"success": True},
            outcome_quality=0.9,
            agent_version="2.0.0",
            control_mode="strategy_enhanced",
            decision_source="strategy"
        )
        
        episode_id = await memory_store.store_episode(test_episode)
        print(f"   ✅ Test episode created: {episode_id}")
        
        # Log strategy performance
        await strategy_repository.log_strategy_performance(
            strategy_id=strategy_id,
            episode_id=episode_id,
            project_id="TEST-001",
            predicted_outcome={"expected_quality": 0.8, "expected_success": True},
            actual_outcome={"actual_quality": 0.9, "actual_success": True},
            outcome_quality=0.9,
            strategy_confidence=0.75,
            context_similarity=0.8
        )
        print("   ✅ Strategy performance logged")
        
        # Test performance history retrieval
        print("\n6. Testing performance history...")
        performance_history = await strategy_repository.get_strategy_performance_history(
            strategy_id=strategy_id,
            days=30,
            limit=10
        )
        print(f"   ✅ Performance history retrieved: {len(performance_history)} entries")
        
        # Test analytics
        print("\n7. Testing strategy analytics...")
        analytics = await strategy_repository.get_strategy_analytics()
        print(f"   ✅ Analytics retrieved:")
        print(f"      Total strategies: {analytics.get('total_strategies', 0)}")
        print(f"      Active strategies: {analytics.get('active_strategies', 0)}")
        
        # Cleanup
        print("\n8. Cleaning up test data...")
        await strategy_repository.deactivate_strategy(strategy_id, "test_cleanup")
        print("   ✅ Test strategy deactivated")
        
        await memory_store.close()
        await knowledge_store.close()
        print("   ✅ Connections closed")
        
        print("\n🎉 All strategy evolution tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test entry point"""
    print("Strategy Evolution System Test")
    print("=" * 50)
    
    success = await test_strategy_system()
    return 0 if success else 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)