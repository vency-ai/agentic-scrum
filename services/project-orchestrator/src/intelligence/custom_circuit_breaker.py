import asyncio
import time
import httpx
import structlog
from enum import Enum
from functools import wraps
from typing import Callable, List, Type, Any, Optional

logger = structlog.get_logger()

class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBroken(Exception):
    """Custom exception raised when the circuit is open."""
    pass

class CustomCircuitBreaker:
    def __init__(
        self,
        error_ratio: float = 0.5,
        response_time: float = 10,
        exceptions: Optional[List[Type[Exception]]] = None,
        broken_time: float = 30,
        name: str = "default",
    ):
        self.error_ratio = error_ratio
        self.response_time = response_time
        self.exceptions = exceptions or [httpx.RequestError, httpx.HTTPStatusError]
        self.broken_time = broken_time
        self.name = name

        self.state = CircuitBreakerState.CLOSED
        self.last_failure_time = 0.0
        self.failures = 0
        self.successes = 0
        self.last_reset_time = time.monotonic()

        logger.info("CircuitBreaker initialized", name=self.name, error_ratio=error_ratio, response_time=response_time, broken_time=broken_time)

    async def __aenter__(self):
        if self.state == CircuitBreakerState.OPEN:
            if time.monotonic() - self.last_failure_time > self.broken_time:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.warning("CircuitBreaker state changed to HALF_OPEN", name=self.name)
            else:
                raise CircuitBroken(f"Circuit breaker '{self.name}' is OPEN.")
        elif self.state == CircuitBreakerState.HALF_OPEN:
            # In HALF_OPEN, allow one request to go through, others fail fast
            if self.failures > 0: # If there was a recent failure in HALF_OPEN, keep it open for others
                 raise CircuitBroken(f"Circuit breaker '{self.name}' is HALF_OPEN and recently failed.")
            # Allow this one to proceed, but reset counts for the test request
            self.failures = 0
            self.successes = 0

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.state == CircuitBreakerState.HALF_OPEN:
            if exc_type is None:
                self.successes += 1
                if self.successes >= 1: # One successful request is enough to close
                    self._reset()
                    logger.info("CircuitBreaker state changed to CLOSED after HALF_OPEN success", name=self.name)
            else:
                self.failures += 1
                self.state = CircuitBreakerState.OPEN
                self.last_failure_time = time.monotonic()
                logger.error("CircuitBreaker state changed to OPEN after HALF_OPEN failure", name=self.name)
        elif self.state == CircuitBreakerState.CLOSED:
            if exc_type is not None and any(isinstance(exc_val, exc_class) for exc_class in self.exceptions):
                self.failures += 1
                self.last_failure_time = time.monotonic()
                logger.warning("CircuitBreaker recorded a failure", name=self.name, failures=self.failures)
            else:
                self.successes += 1

            self._check_threshold()

    def _check_threshold(self):
        current_time = time.monotonic()
        if current_time - self.last_reset_time > self.response_time:
            # Reset counts if outside the response_time window
            self.failures = 0
            self.successes = 0
            self.last_reset_time = current_time
            self.state = CircuitBreakerState.CLOSED # Ensure it's closed after a full window of no checks
            return

        total_requests = self.failures + self.successes
        if total_requests >= 5 and self.failures / total_requests >= self.error_ratio:
            self.state = CircuitBreakerState.OPEN
            self.last_failure_time = current_time
            logger.error("CircuitBreaker state changed to OPEN due to high error ratio", name=self.name, failures=self.failures, total_requests=total_requests)

    def _reset(self):
        self.state = CircuitBreakerState.CLOSED
        self.failures = 0
        self.successes = 0
        self.last_failure_time = 0.0
        self.last_reset_time = time.monotonic()
        logger.info("CircuitBreaker reset to CLOSED", name=self.name)

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            async with self:
                return await func(*args, **kwargs)
        return wrapper