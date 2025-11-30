import asyncio
import sys
sys.path.append('/tmp/memory')

from models import Episode
from datetime import datetime, timezone
from uuid import uuid4
import httpx

async def test_episode_embedder():
    print('=== EpisodeEmbedder Basic Test ===')
    
    try:
        # Create test episode
        episode = Episode(
            project_id='embedder-test-basic',
            perception={'backlog_tasks': 10, 'team_size': 3},
            reasoning={'decision': 'create_sprint', 'confidence': 0.8},
            action={'sprint_created': True, 'tasks_assigned': 5},
            agent_version='1.0.0',
            control_mode='rule_based_only',
            decision_source='rule_based_only'
        )
        
        # Convert to text
        text_parts = []
        text_parts.append(f'Project: {episode.project_id}')
        
        perception_text = ', '.join(f'{k}: {v}' for k, v in episode.perception.items())
        text_parts.append(f'Context: {perception_text}')
        
        reasoning_text = ', '.join(f'{k}: {v}' for k, v in episode.reasoning.items())  
        text_parts.append(f'Analysis: {reasoning_text}')
        
        action_text = ', '.join(f'{k}: {v}' for k, v in episode.action.items())
        text_parts.append(f'Decision: {action_text}')
        
        episode_text = ' | '.join(text_parts)
        print(f'✓ Episode text: {episode_text}')
        
        # Test embedding generation
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'http://embedding-service.dsm.svc.cluster.local/embed',
                json={'text': episode_text}
            )
            data = response.json()
            embedding = data['embedding']
            
            print(f'✓ Generated embedding: {len(embedding)} dimensions')
            print(f'  First 3: {embedding[:3]}')
        
        print('\n=== EpisodeEmbedder Basic Test Complete ===')
        
    except Exception as e:
        print(f'✗ Test failed: {e}')
        import traceback
        traceback.print_exc()

asyncio.run(test_episode_embedder())
