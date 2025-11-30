import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import UUID, uuid4
import sys
import os

# Add the src directory to the path so we can import from memory module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from memory.agent_memory_store import AgentMemoryStore
from memory.models import Episode

@pytest.fixture
def sample_episode():
    return Episode(
        episode_id=uuid4(),
        project_id="test-project-123",
        timestamp=datetime.now(timezone.utc),
        perception={"test": "perception"},
        reasoning={"test": "reasoning"},
        action={"test": "action"},
        agent_version="1.0.0",
        control_mode="rule_based_only",
        decision_source="rule_based_only"
    )

@pytest.fixture
async def mock_store():
    store = AgentMemoryStore("mock://connection")
    # Mock the pool
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__.return_value = None
    store._pool = mock_pool
    return store, mock_conn

@pytest.mark.asyncio
async def test_store_episode(mock_store, sample_episode):
    store, mock_conn = mock_store
    expected_id = uuid4()
    
    mock_conn.fetchval.return_value = expected_id
    
    result = await store.store_episode(sample_episode)
    
    assert result == expected_id
    mock_conn.fetchval.assert_called_once()
    
    # Verify the SQL call
    call_args = mock_conn.fetchval.call_args
    assert "INSERT INTO agent_episodes" in call_args[0][0]
    assert sample_episode.project_id in call_args[0]

@pytest.mark.asyncio
async def test_get_episode(mock_store):
    store, mock_conn = mock_store
    episode_id = uuid4()
    
    # Mock database row
    mock_row = {
        'episode_id': episode_id,
        'project_id': 'test-project',
        'timestamp': datetime.now(timezone.utc),
        'perception': {'test': 'data'},
        'reasoning': {'test': 'data'},
        'action': {'test': 'data'},
        'outcome': None,
        'outcome_quality': None,
        'outcome_recorded_at': None,
        'agent_version': '1.0.0',
        'control_mode': 'rule_based_only',
        'decision_source': 'rule_based_only',
        'sprint_id': None,
        'chronicle_note_id': None,
        'similarity': None
    }
    
    mock_conn.fetchrow.return_value = mock_row
    
    result = await store.get_episode(episode_id)
    
    assert result is not None
    assert isinstance(result, Episode)
    assert result.episode_id == episode_id
    assert result.project_id == 'test-project'

@pytest.mark.asyncio
async def test_get_episode_not_found(mock_store):
    store, mock_conn = mock_store
    episode_id = uuid4()
    
    mock_conn.fetchrow.return_value = None
    
    result = await store.get_episode(episode_id)
    
    assert result is None

@pytest.mark.asyncio
async def test_get_project_episodes(mock_store):
    store, mock_conn = mock_store
    project_id = "test-project-123"
    
    # Mock multiple episodes
    mock_rows = [
        {
            'episode_id': uuid4(),
            'project_id': project_id,
            'timestamp': datetime.now(timezone.utc),
            'perception': {'test': 'data1'},
            'reasoning': {'test': 'data1'},
            'action': {'test': 'data1'},
            'outcome': None,
            'outcome_quality': None,
            'outcome_recorded_at': None,
            'agent_version': '1.0.0',
            'control_mode': 'rule_based_only',
            'decision_source': 'rule_based_only',
            'sprint_id': None,
            'chronicle_note_id': None,
            'similarity': None
        },
        {
            'episode_id': uuid4(),
            'project_id': project_id,
            'timestamp': datetime.now(timezone.utc),
            'perception': {'test': 'data2'},
            'reasoning': {'test': 'data2'},
            'action': {'test': 'data2'},
            'outcome': None,
            'outcome_quality': None,
            'outcome_recorded_at': None,
            'agent_version': '1.0.0',
            'control_mode': 'rule_based_only',
            'decision_source': 'rule_based_only',
            'sprint_id': None,
            'chronicle_note_id': None,
            'similarity': None
        }
    ]
    
    mock_conn.fetch.return_value = mock_rows
    
    result = await store.get_project_episodes(project_id, limit=10)
    
    assert len(result) == 2
    assert all(isinstance(ep, Episode) for ep in result)
    assert all(ep.project_id == project_id for ep in result)

@pytest.mark.asyncio
async def test_update_episode_embedding(mock_store):
    store, mock_conn = mock_store
    episode_id = uuid4()
    embedding = [0.1] * 1024
    
    mock_conn.execute.return_value = None
    
    await store.update_episode_embedding(episode_id, embedding)
    
    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args
    assert "UPDATE agent_episodes" in call_args[0][0]
    assert "embedding = $1::vector(1024)" in call_args[0][0]

@pytest.mark.asyncio
async def test_update_episode_outcome(mock_store):
    store, mock_conn = mock_store
    episode_id = uuid4()
    outcome = {"result": "success"}
    quality = 0.8
    
    mock_conn.execute.return_value = None
    
    await store.update_episode_outcome(episode_id, outcome, quality)
    
    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args
    assert "UPDATE agent_episodes" in call_args[0][0]
    assert "outcome = $1" in call_args[0][0]

@pytest.mark.asyncio
async def test_search_similar_episodes(mock_store):
    store, mock_conn = mock_store
    query_embedding = [0.5] * 1024
    project_id = "test-project"
    
    # Mock similar episodes with similarity scores
    mock_rows = [
        {
            'episode_id': uuid4(),
            'project_id': project_id,
            'timestamp': datetime.now(timezone.utc),
            'perception': {'test': 'similar1'},
            'reasoning': {'test': 'similar1'},
            'action': {'test': 'similar1'},
            'outcome': None,
            'outcome_quality': None,
            'outcome_recorded_at': None,
            'agent_version': '1.0.0',
            'control_mode': 'rule_based_only',
            'decision_source': 'rule_based_only',
            'sprint_id': None,
            'chronicle_note_id': None,
            'similarity': 0.85
        }
    ]
    
    mock_conn.fetch.return_value = mock_rows
    
    result = await store.search_similar_episodes(query_embedding, project_id, limit=5)
    
    assert len(result) == 1
    assert isinstance(result[0], Episode)
    assert result[0].similarity == 0.85

@pytest.mark.asyncio
async def test_get_episode_count(mock_store):
    store, mock_conn = mock_store
    
    mock_conn.fetchval.return_value = 42
    
    result = await store.get_episode_count("test-project")
    
    assert result == 42
    mock_conn.fetchval.assert_called_once()

@pytest.mark.asyncio
async def test_delete_episode(mock_store):
    store, mock_conn = mock_store
    episode_id = uuid4()
    
    mock_conn.execute.return_value = "DELETE 1"
    
    result = await store.delete_episode(episode_id)
    
    assert result is True
    mock_conn.execute.assert_called_once()

@pytest.mark.asyncio
async def test_health_check_success(mock_store):
    store, mock_conn = mock_store
    
    mock_conn.fetchval.return_value = 1
    
    result = await store.health_check()
    
    assert result is True

@pytest.mark.asyncio
async def test_health_check_failure():
    store = AgentMemoryStore("mock://connection")
    store._pool = None  # Simulate uninitialized store
    
    result = await store.health_check()
    
    assert result is False

@pytest.mark.asyncio
async def test_store_not_initialized():
    store = AgentMemoryStore("mock://connection")
    # Don't initialize the pool
    
    with pytest.raises(RuntimeError, match="AgentMemoryStore not initialized"):
        await store.get_episode_count()