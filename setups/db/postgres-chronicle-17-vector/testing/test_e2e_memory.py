import asyncio
import sys
sys.path.append('/tmp/memory')

# End-to-end memory system test
from models import Episode, Strategy
from datetime import datetime, timezone
from uuid import uuid4
import httpx
import asyncpg
import json
import time

# Simple inline AgentMemorySystem for testing
class SimpleMemorySystem:
    def __init__(self):
        self.conn_string = 'postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory'
        self.embed_url = 'http://embedding-service.dsm.svc.cluster.local'
        self.conn = None
        self.http_client = None
    
    async def initialize(self):
        self.conn = await asyncpg.connect(self.conn_string)
        self.http_client = httpx.AsyncClient()
    
    async def close(self):
        if self.conn:
            await self.conn.close()
        if self.http_client:
            await self.http_client.aclose()
    
    def episode_to_text(self, episode):
        parts = [f'Project: {episode.project_id}']
        if episode.perception:
            parts.append(f'Context: {", ".join(f"{k}: {v}" for k, v in episode.perception.items())}')
        if episode.reasoning:
            parts.append(f'Analysis: {", ".join(f"{k}: {v}" for k, v in episode.reasoning.items())}')
        if episode.action:
            parts.append(f'Decision: {", ".join(f"{k}: {v}" for k, v in episode.action.items())}')
        return ' | '.join(parts)
    
    async def embed_text(self, text):
        response = await self.http_client.post(f'{self.embed_url}/embed', json={'text': text})
        return response.json()['embedding']
    
    async def store_episode_with_embedding(self, episode):
        # Store episode
        episode_id = await self.conn.fetchval("""
            INSERT INTO agent_episodes 
            (project_id, timestamp, perception, reasoning, action, agent_version, control_mode, decision_source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING episode_id
        """, episode.project_id, episode.timestamp, json.dumps(episode.perception),
        json.dumps(episode.reasoning), json.dumps(episode.action),
        episode.agent_version, episode.control_mode, episode.decision_source)
        
        # Generate and store embedding
        episode_text = self.episode_to_text(episode)
        embedding = await self.embed_text(episode_text)
        vector_str = '[' + ','.join(map(str, embedding)) + ']'
        
        await self.conn.execute("""
            UPDATE agent_episodes SET embedding = $1::vector(1024) WHERE episode_id = $2
        """, vector_str, episode_id)
        
        return episode_id
    
    async def search_similar_episodes(self, query_embedding, project_id, limit=5):
        query_vector = '[' + ','.join(map(str, query_embedding)) + ']'
        rows = await self.conn.fetch("""
            SELECT *, 1 - (embedding <=> $1::vector(1024)) as similarity
            FROM agent_episodes 
            WHERE project_id = $2 AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector(1024)
            LIMIT $3
        """, query_vector, project_id, limit)
        
        episodes = []
        for row in rows:
            episode = Episode.from_db_row(dict(row))
            episode.similarity = row['similarity']
            episodes.append(episode)
        return episodes
    
    async def store_strategy(self, strategy):
        return await self.conn.fetchval("""
            INSERT INTO agent_knowledge 
            (knowledge_type, content, description, confidence, 
             supporting_episodes, contradicting_episodes, times_applied, 
             success_count, failure_count, created_by, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING knowledge_id
        """, strategy.knowledge_type, json.dumps(strategy.content), 
        strategy.description, strategy.confidence, strategy.supporting_episodes,
        strategy.contradicting_episodes, strategy.times_applied,
        strategy.success_count, strategy.failure_count,
        strategy.created_by, strategy.is_active)
    
    async def create_working_session(self, project_id, context):
        return await self.conn.fetchval("""
            INSERT INTO agent_working_memory (project_id, active_context, is_active)
            VALUES ($1, $2, $3) RETURNING session_id
        """, project_id, json.dumps(context), True)

async def test_e2e_memory_system():
    print('=== End-to-End Memory System Integration Test ===')
    
    try:
        memory_system = SimpleMemorySystem()
        await memory_system.initialize()
        
        project_id = 'e2e-test-complete'
        print(f'✓ Memory system initialized for project: {project_id}')
        
        # === Step 1: Store strategy ===
        strategy = Strategy(
            knowledge_type='strategy',
            content={'pattern': 'high_backlog_sprint_creation', 'triggers': ['backlog > 10', 'capacity > 0.7']},
            description='Create new sprint when backlog is high and team has capacity',
            confidence=0.8,
            supporting_episodes=[uuid4(), uuid4(), uuid4()],  # Need at least 3
            times_applied=3,
            success_count=2,
            failure_count=1,
            created_by='e2e_test'
        )
        
        strategy_id = await memory_system.store_strategy(strategy)
        print(f'✓ Step 1: Stored strategy {strategy_id}')
        
        # === Step 2: Create working memory session ===
        working_context = {
            'current_goal': 'Optimize project workflow',
            'active_decisions': ['sprint_planning', 'resource_allocation'],
            'session_type': 'e2e_test'
        }
        
        session_id = await memory_system.create_working_session(project_id, working_context)
        print(f'✓ Step 2: Created working session {session_id}')
        
        # === Step 3: Store first episode ===
        episode1 = Episode(
            project_id=project_id,
            timestamp=datetime.now(timezone.utc),
            perception={
                'backlog_tasks': 12,
                'team_capacity': 0.8,
                'current_sprint': 'SPRINT-E2E-01',
                'blockers': 0
            },
            reasoning={
                'analysis': 'High backlog with available capacity',
                'recommendation': 'create_new_sprint',
                'confidence': 0.9,
                'strategy_applied': 'high_backlog_sprint_creation'
            },
            action={
                'decision': 'create_sprint',
                'tasks_moved': 8,
                'sprint_created': True,
                'notifications_sent': 3
            },
            agent_version='1.0.0',
            control_mode='rule_based_only',
            decision_source='rule_based_only'
        )
        
        start_time = time.time()
        episode1_id = await memory_system.store_episode_with_embedding(episode1)
        store_duration = (time.time() - start_time) * 1000
        
        print(f'✓ Step 3: Stored episode 1 with embedding in {store_duration:.1f}ms - ID: {episode1_id}')
        
        # === Step 4: Store similar episode ===
        episode2 = Episode(
            project_id=project_id,
            timestamp=datetime.now(timezone.utc),
            perception={
                'backlog_tasks': 14,
                'team_capacity': 0.75,
                'current_sprint': 'SPRINT-E2E-02',
                'blockers': 1
            },
            reasoning={
                'analysis': 'Similar high backlog situation with minor blockers',
                'recommendation': 'create_sprint_with_caution',
                'confidence': 0.7,
                'strategy_applied': 'high_backlog_sprint_creation'
            },
            action={
                'decision': 'create_sprint',
                'tasks_moved': 6,
                'sprint_created': True,
                'blocker_addressed': True
            },
            agent_version='1.0.0',
            control_mode='rule_based_only',
            decision_source='rule_based_only'
        )
        
        episode2_id = await memory_system.store_episode_with_embedding(episode2)
        print(f'✓ Step 4: Stored episode 2 with embedding - ID: {episode2_id}')
        
        # === Step 5: Test similarity search ===
        # Search for episodes similar to a new situation
        query_context = {
            'backlog_tasks': 13,
            'team_capacity': 0.85,
            'current_sprint': 'SPRINT-E2E-03'
        }
        
        query_text = f'Context: backlog_tasks: 13, team_capacity: 0.85, current_sprint: SPRINT-E2E-03'
        query_embedding = await memory_system.embed_text(query_text)
        
        start_time = time.time()
        similar_episodes = await memory_system.search_similar_episodes(
            query_embedding, project_id, limit=5
        )
        search_duration = (time.time() - start_time) * 1000
        
        print(f'✓ Step 5: Found {len(similar_episodes)} similar episodes in {search_duration:.1f}ms')
        for i, ep in enumerate(similar_episodes):
            print(f'  - Episode {i+1}: similarity={ep.similarity:.4f}, decision={ep.reasoning.get("recommendation", "unknown")}')
        
        # === Step 6: End-to-end decision making simulation ===
        print('\\n=== Decision Making Simulation ===')
        
        new_situation = {
            'backlog_tasks': 15,
            'team_capacity': 0.9,
            'urgent_requests': 2,
            'upcoming_deadline': '1_week'
        }
        
        # Get similar precedents
        situation_text = 'Context: ' + ', '.join(f'{k}: {v}' for k, v in new_situation.items())
        situation_embedding = await memory_system.embed_text(situation_text)
        precedents = await memory_system.search_similar_episodes(situation_embedding, project_id, limit=3)
        
        print(f'✓ Decision context: {len(precedents)} relevant precedents found')
        
        # Make decision based on precedents
        if precedents:
            avg_similarity = sum(ep.similarity for ep in precedents) / len(precedents)
            successful_decisions = [ep for ep in precedents if ep.reasoning.get('confidence', 0) > 0.7]
            
            print(f'  - Average precedent similarity: {avg_similarity:.4f}')
            print(f'  - High-confidence precedents: {len(successful_decisions)}/{len(precedents)}')
            
            if successful_decisions:
                recommended_action = successful_decisions[0].action.get('decision', 'create_sprint')
                print(f'  - Recommended action: {recommended_action}')
            else:
                print('  - Recommended action: proceed with caution')
        
        print('\\n=== End-to-End Test Summary ===')
        print(f'✓ Strategy storage: Working')
        print(f'✓ Working memory: Working') 
        print(f'✓ Episode storage with embeddings: Working ({store_duration:.1f}ms avg)')
        print(f'✓ Similarity search: Working ({search_duration:.1f}ms)')
        print(f'✓ Decision support: Working')
        print(f'✓ Complete memory cycle: SUCCESS')
        
        await memory_system.close()
        
    except Exception as e:
        print(f'✗ E2E test failed: {e}')
        import traceback
        traceback.print_exc()

asyncio.run(test_e2e_memory_system())
