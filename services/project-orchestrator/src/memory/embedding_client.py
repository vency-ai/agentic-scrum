import httpx
import logging
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
import time # New import

from intelligence.custom_circuit_breaker import CustomCircuitBreaker, CircuitBroken # New import
from monitoring.agent_memory_metrics import (
    EMBEDDING_GENERATION_LATENCY_SECONDS,
    EMBEDDING_GENERATION_FAILURES_TOTAL,
    EMBEDDING_SERVICE_CIRCUIT_BREAKER_STATE
) # New import

logger = logging.getLogger(__name__)

class EmbeddingClient:
    """Async HTTP client for embedding generation service"""
    
    def __init__(
        self,
        base_url: str = "http://embedding-service.dsm.svc.cluster.local",
        timeout: float = 10.0,
        max_retries: int = 3
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        self.circuit_breaker = CustomCircuitBreaker(
            error_ratio=0.5,
            response_time=10,
            exceptions=[httpx.RequestError, httpx.HTTPStatusError],
            broken_time=30,
            name="embedding_service_client"
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        start_time = time.monotonic()
        try:
            async with self.circuit_breaker:
                response = await self.client.post(
                    f"{self.base_url}/embed",
                    json={"text": text}
                )
                response.raise_for_status()
                data = response.json()
                latency_ms = (time.monotonic() - start_time) * 1000
                logger.debug(f"Embedding generated in {latency_ms:.2f}ms")
                EMBEDDING_GENERATION_LATENCY_SECONDS.observe(latency_ms / 1000.0) # Convert to seconds
                return data["embedding"]
        except CircuitBroken:
            EMBEDDING_GENERATION_FAILURES_TOTAL.inc()
            logger.warning("Embedding service circuit breaker is open, skipping embedding generation.")
            raise
        except httpx.HTTPError as e:
            EMBEDDING_GENERATION_FAILURES_TOTAL.inc()
            logger.error(f"Embedding generation failed: {e}")
            raise
        except Exception as e:
            EMBEDDING_GENERATION_FAILURES_TOTAL.inc()
            logger.error(f"Unexpected error during embedding generation: {e}")
            raise
    
    async def generate_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        start_time = time.monotonic()
        try:
            async with self.circuit_breaker:
                response = await self.client.post(
                    f"{self.base_url}/embed/batch",
                    json={"texts": texts}
                )
                response.raise_for_status()
                data = response.json()
                latency_ms = (time.monotonic() - start_time) * 1000
                logger.debug(f"Batch embeddings generated in {latency_ms:.2f}ms")
                EMBEDDING_GENERATION_LATENCY_SECONDS.observe(latency_ms / 1000.0) # Convert to seconds
                return data["embeddings"]
        except CircuitBroken:
            EMBEDDING_GENERATION_FAILURES_TOTAL.inc()
            logger.warning("Embedding service circuit breaker is open, skipping batch embedding generation.")
            raise
        except httpx.HTTPError as e:
            EMBEDDING_GENERATION_FAILURES_TOTAL.inc()
            logger.error(f"Batch embedding generation failed: {e}")
            raise
        except Exception as e:
            EMBEDDING_GENERATION_FAILURES_TOTAL.inc()
            logger.error(f"Unexpected error during batch embedding generation: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if embedding service is healthy and return circuit breaker state and latency"""
        status = "ok"
        latency_ms = 0
        error_message = None
        try:
            start_time = time.monotonic()
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            latency_ms = (time.monotonic() - start_time) * 1000
        except httpx.HTTPStatusError as e:
            status = "error"
            error_message = f"HTTP error: {e.response.status_code}"
        except httpx.RequestError as e:
            status = "error"
            error_message = f"Request error: {e}"
        except Exception as e:
            status = "error"
            error_message = f"Unexpected error: {e}"

        # Update circuit breaker state metric
        state_value = 0.0 # CLOSED
        if self.circuit_breaker.state == "OPEN":
            state_value = 1.0
        elif self.circuit_breaker.state == "HALF_OPEN":
            state_value = 0.5
        EMBEDDING_SERVICE_CIRCUIT_BREAKER_STATE.set(state_value)

        return {
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "circuit_breaker_state": self.circuit_breaker.state,
            "error_message": error_message
        }
    
    async def close(self):
        """Close HTTP client connection pool"""
        await self.client.aclose()