import pytest
from unittest.mock import AsyncMock, patch
import httpx
import sys
import os

# Add the src directory to the path so we can import from memory module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from memory.embedding_client import EmbeddingClient

@pytest.mark.asyncio
async def test_generate_embedding_success():
    client = EmbeddingClient()
    
    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "embedding": [0.1] * 1024,
            "dimensions": 1024
        }
        mock_response.raise_for_status = AsyncMock()
        mock_post.return_value = mock_response
        
        embedding = await client.generate_embedding("test text")
        
        assert len(embedding) == 1024
        assert isinstance(embedding[0], float)
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_generate_embedding_retry_on_failure():
    client = EmbeddingClient()
    
    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        # First two calls fail, third succeeds
        mock_response_success = AsyncMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"embedding": [0.1] * 1024}
        mock_response_success.raise_for_status = AsyncMock()
        
        mock_post.side_effect = [
            httpx.HTTPError("Connection failed"),
            httpx.HTTPError("Connection failed"),
            mock_response_success
        ]
        
        embedding = await client.generate_embedding("test text")
        assert len(embedding) == 1024
        assert mock_post.call_count == 3

@pytest.mark.asyncio
async def test_generate_batch_embeddings():
    client = EmbeddingClient()
    
    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "embeddings": [[0.1] * 1024, [0.2] * 1024],
            "count": 2
        }
        mock_response.raise_for_status = AsyncMock()
        mock_post.return_value = mock_response
        
        embeddings = await client.generate_batch_embeddings(["text 1", "text 2"])
        
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1024
        assert len(embeddings[1]) == 1024

@pytest.mark.asyncio
async def test_health_check_success():
    client = EmbeddingClient()
    
    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        health = await client.health_check()
        assert health is True

@pytest.mark.asyncio
async def test_health_check_failure():
    client = EmbeddingClient()
    
    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPError("Service unavailable")
        
        health = await client.health_check()
        assert health is False

@pytest.mark.asyncio
async def test_client_close():
    client = EmbeddingClient()
    
    with patch.object(client.client, 'aclose', new_callable=AsyncMock) as mock_close:
        await client.close()
        mock_close.assert_called_once()