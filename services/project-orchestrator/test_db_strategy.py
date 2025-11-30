#!/usr/bin/env python3
"""
Simple Database Test for Strategy Evolution

Tests that our database migration worked correctly.
"""

import asyncio
import asyncpg
import sys
from datetime import datetime
from uuid import uuid4
import json

async def test_database():
    """Test database strategy tables"""
    print("🧪 Testing Strategy Evolution Database...")
    
    db_connection = "postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory"
    
    try:
        print("\n1. Connecting to database...")
        conn = await asyncpg.connect(db_connection)
        print("   ✅ Connected to agent_memory database")
        
        # Test strategy_performance_log table structure
        print("\n2. Testing strategy_performance_log table...")
        result = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'strategy_performance_log' ORDER BY ordinal_position")
        
        expected_columns = [
            'log_id', 'strategy_id', 'episode_id', 'project_id',
            'application_timestamp', 'predicted_outcome', 'actual_outcome',
            'outcome_quality', 'strategy_confidence', 'context_similarity',
            'performance_delta', 'created_at', 'updated_at'
        ]
        
        actual_columns = [row['column_name'] for row in result]
        print(f"   📋 Table columns: {len(actual_columns)}")
        
        for col in expected_columns:
            if col in actual_columns:
                print(f"      ✅ {col}")
            else:
                print(f"      ❌ Missing: {col}")
                return False
        
        # Test indexes
        print("\n3. Testing indexes...")
        indexes = await conn.fetch("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename = 'strategy_performance_log'
            ORDER BY indexname
        """)
        
        expected_indexes = [
            'idx_strategy_performance_log_episode_id',
            'idx_strategy_performance_log_project_id', 
            'idx_strategy_performance_log_quality',
            'idx_strategy_performance_log_strategy_id',
            'idx_strategy_performance_log_timestamp'
        ]
        
        actual_indexes = [row['indexname'] for row in indexes if not row['indexname'].endswith('_pkey')]
        print(f"   📋 Performance indexes: {len(actual_indexes)}")
        
        for idx in expected_indexes:
            if idx in actual_indexes:
                print(f"      ✅ {idx}")
            else:
                print(f"      ❌ Missing: {idx}")
        
        # Test agent_knowledge strategy indexes
        print("\n4. Testing agent_knowledge strategy indexes...")
        ak_indexes = await conn.fetch("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename = 'agent_knowledge' AND indexname LIKE '%strategy%'
            ORDER BY indexname
        """)
        
        strategy_indexes = [row['indexname'] for row in ak_indexes]
        print(f"   📋 Strategy indexes: {len(strategy_indexes)}")
        for idx in strategy_indexes:
            print(f"      ✅ {idx}")
        
        # Test trigger
        print("\n5. Testing triggers...")
        triggers = await conn.fetch("""
            SELECT trigger_name FROM information_schema.triggers 
            WHERE event_object_table = 'strategy_performance_log'
        """)
        
        if triggers:
            for trigger in triggers:
                print(f"      ✅ {trigger['trigger_name']}")
        else:
            print("      ❌ No triggers found")
        
        # Test table constraints
        print("\n6. Testing check constraints...")
        constraints = await conn.fetch("""
            SELECT constraint_name FROM information_schema.check_constraints
            WHERE constraint_name LIKE '%strategy_performance_log%'
            ORDER BY constraint_name
        """)
        
        print(f"   📋 Check constraints: {len(constraints)}")
        for constraint in constraints:
            print(f"      ✅ {constraint['constraint_name']}")
        
        # Test foreign key constraints
        print("\n7. Testing foreign key constraints...")
        fk_constraints = await conn.fetch("""
            SELECT 
                kcu.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.constraint_column_usage ccu
                ON kcu.constraint_name = ccu.constraint_name
            WHERE kcu.table_name = 'strategy_performance_log'
            AND kcu.constraint_name LIKE '%fkey%'
        """)
        
        print(f"   📋 Foreign key constraints: {len(fk_constraints)}")
        for fk in fk_constraints:
            print(f"      ✅ {fk['column_name']} -> {fk['foreign_table_name']}.{fk['foreign_column_name']}")
        
        # Test a simple insert/select/delete cycle
        print("\n8. Testing basic CRUD operations...")
        
        # First create a test strategy in agent_knowledge
        strategy_id = await conn.fetchval("""
            INSERT INTO agent_knowledge 
            (knowledge_type, content, description, confidence, supporting_episodes, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING knowledge_id
        """, 'strategy', json.dumps({'test': 'data'}), 'Test strategy', 0.8, [uuid4(), uuid4(), uuid4()], 'test')
        
        print(f"      ✅ Test strategy created: {strategy_id}")
        
        # Create a test episode
        episode_id = await conn.fetchval("""
            INSERT INTO agent_episodes
            (project_id, timestamp, perception, reasoning, action, agent_version, control_mode, decision_source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING episode_id
        """, 'TEST-001', datetime.utcnow(), json.dumps({'test': 'perception'}), 
        json.dumps({'test': 'reasoning'}), json.dumps({'test': 'action'}), 
        '2.0.0', 'test', 'test')
        
        print(f"      ✅ Test episode created: {episode_id}")
        
        # Insert into strategy_performance_log
        log_id = await conn.fetchval("""
            INSERT INTO strategy_performance_log
            (strategy_id, episode_id, project_id, predicted_outcome, actual_outcome, 
             outcome_quality, strategy_confidence, context_similarity, performance_delta)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING log_id
        """, strategy_id, episode_id, 'TEST-001', 
        json.dumps({'expected': 0.8}), json.dumps({'actual': 0.9}),
        0.9, 0.8, 0.75, 0.1)
        
        print(f"      ✅ Performance log created: {log_id}")
        
        # Test retrieval
        result = await conn.fetchrow("""
            SELECT spl.*, ak.description as strategy_description
            FROM strategy_performance_log spl
            JOIN agent_knowledge ak ON spl.strategy_id = ak.knowledge_id
            WHERE spl.log_id = $1
        """, log_id)
        
        if result:
            print(f"      ✅ Performance log retrieved successfully")
            print(f"         Strategy: {result['strategy_description']}")
            print(f"         Quality: {result['outcome_quality']}")
            print(f"         Confidence: {result['strategy_confidence']}")
        else:
            print("      ❌ Failed to retrieve performance log")
            return False
        
        # Cleanup test data
        await conn.execute("DELETE FROM strategy_performance_log WHERE log_id = $1", log_id)
        await conn.execute("DELETE FROM agent_episodes WHERE episode_id = $1", episode_id)
        await conn.execute("DELETE FROM agent_knowledge WHERE knowledge_id = $1", strategy_id)
        print("      ✅ Test data cleaned up")
        
        await conn.close()
        print("\n🎉 All database tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test entry point"""
    print("Strategy Evolution Database Test")
    print("=" * 40)
    
    success = await test_database()
    return 0 if success else 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)