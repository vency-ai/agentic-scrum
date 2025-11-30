"""
Custom Circuit Breaker Implementation
Replacement for broken aiomisc CircuitBreaker with proper async context manager support
"""
import asyncio
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Type, Any, Optional, Callable, Awaitable
import structlog

logger = structlog.get_logger()


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"      # Normal operation, requests allowed
    OPEN = "OPEN"          # Circuit is open, requests blocked  
    HALF_OPEN = "HALF_OPEN"  # Testing if service has recovered


class CircuitBrokenError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Production-ready Circuit Breaker with async context manager support
    
    Drop-in replacement for aiomisc.CircuitBreaker with the same API:
    - error_ratio: Failure ratio threshold (0.0-1.0)
    - response_time: Time window for failure tracking (seconds)
    - exceptions: List of exception types to count as failures  
    - broken_time: Time to stay open before attempting recovery (seconds)
    """
    
    def __init__(
        self,
        error_ratio: float = 0.5,
        response_time: int = 10,
        exceptions: Optional[List[Type[Exception]]] = None,
        broken_time: int = 30,
        min_requests: int = 3  # Minimum requests before evaluating error ratio
    ):
        self.error_ratio = error_ratio
        self.response_time = response_time
        self.exceptions = exceptions or [Exception]
        self.broken_time = broken_time
        self.min_requests = min_requests
        
        # State tracking
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._last_request_time: Optional[datetime] = None
        self._state_change_time = datetime.now()
        
        # Request history for sliding window
        self._request_history: List[tuple[datetime, bool]] = []  # (timestamp, success)
        
        logger.info(
            "Circuit breaker initialized",
            error_ratio=error_ratio,
            response_time=response_time,
            broken_time=broken_time,
            exceptions=[e.__name__ for e in self.exceptions]
        )
    
    def _clean_request_history(self) -> None:
        """Remove requests outside the response_time window"""
        cutoff_time = datetime.now() - timedelta(seconds=self.response_time)
        self._request_history = [
            (timestamp, success) for timestamp, success in self._request_history
            if timestamp > cutoff_time
        ]
    
    def _calculate_failure_rate(self) -> float:
        """Calculate current failure rate within the response_time window"""
        self._clean_request_history()
        
        if not self._request_history:
            return 0.0
            
        total_requests = len(self._request_history)
        failures = sum(1 for _, success in self._request_history if not success)
        
        return failures / total_requests if total_requests > 0 else 0.0
    
    def _should_open_circuit(self) -> bool:
        """Determine if circuit should open based on failure rate"""
        if len(self._request_history) < self.min_requests:
            return False
            
        failure_rate = self._calculate_failure_rate()
        return failure_rate >= self.error_ratio
    
    def _should_close_circuit(self) -> bool:
        """Determine if circuit should close (from HALF_OPEN to CLOSED)"""
        return self._state == CircuitState.HALF_OPEN
    
    def _transition_to_half_open(self) -> bool:
        """Check if enough time has passed to try HALF_OPEN state"""
        if self._state != CircuitState.OPEN:
            return False
            
        if self._last_failure_time is None:
            return True
            
        time_since_failure = datetime.now() - self._last_failure_time
        return time_since_failure.total_seconds() >= self.broken_time
    
    def _record_success(self) -> None:
        """Record a successful request"""
        now = datetime.now()
        self._request_history.append((now, True))
        self._success_count += 1
        self._last_request_time = now
        
        # Transition from HALF_OPEN to CLOSED on success
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._state_change_time = now
            logger.info("Circuit breaker closed (recovered)", state=self._state.value)
    
    def _record_failure(self) -> None:
        """Record a failed request"""
        now = datetime.now()
        self._request_history.append((now, False))
        self._failure_count += 1
        self._last_failure_time = now
        self._last_request_time = now
        
        # Check if circuit should open
        if self._state == CircuitState.CLOSED and self._should_open_circuit():
            self._state = CircuitState.OPEN
            self._state_change_time = now
            logger.warning(
                "Circuit breaker opened",
                state=self._state.value,
                failure_rate=self._calculate_failure_rate(),
                error_ratio=self.error_ratio
            )
        elif self._state == CircuitState.HALF_OPEN:
            # Failed during HALF_OPEN, go back to OPEN
            self._state = CircuitState.OPEN
            self._state_change_time = now
            logger.warning("Circuit breaker re-opened after half-open failure", state=self._state.value)
    
    def _check_state_transitions(self) -> None:
        """Check and perform state transitions"""
        if self._state == CircuitState.OPEN and self._transition_to_half_open():
            self._state = CircuitState.HALF_OPEN
            self._state_change_time = datetime.now()
            logger.info("Circuit breaker half-open (testing recovery)", state=self._state.value)
    
    async def __aenter__(self):
        """Async context manager entry"""
        self._check_state_transitions()
        
        if self._state == CircuitState.OPEN:
            raise CircuitBrokenError(f"Circuit breaker is {self._state.value}")
        
        # For CLOSED and HALF_OPEN states, allow the request to proceed
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with success/failure recording"""
        if exc_type is None:
            # Success - no exception occurred
            self._record_success()
        elif any(isinstance(exc_val, exc) for exc in self.exceptions):
            # Failure - exception matches our tracked exceptions
            self._record_failure()
        # If exception is not in our tracked exceptions, don't count it as failure
        
        # Don't suppress exceptions
        return False
    
    def context(self):
        """
        Return self for async context manager usage
        Maintains API compatibility with aiomisc.CircuitBreaker
        """
        return self
    
    @property
    def state(self) -> str:
        """Get current circuit state"""
        return self._state.value
    
    @property
    def failure_count(self) -> int:
        """Get total failure count"""
        return self._failure_count
    
    @property
    def success_count(self) -> int:
        """Get total success count"""
        return self._success_count
    
    @property
    def current_failure_rate(self) -> float:
        """Get current failure rate"""
        return self._calculate_failure_rate()
    
    def reset(self) -> None:
        """Reset circuit breaker to initial state"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._last_request_time = None
        self._state_change_time = datetime.now()
        self._request_history.clear()
        logger.info("Circuit breaker reset", state=self._state.value)
    
    def __str__(self) -> str:
        return f"CircuitBreaker(state={self._state.value}, failure_rate={self.current_failure_rate:.2f})"
    
    def __repr__(self) -> str:
        return (
            f"CircuitBreaker("
            f"state={self._state.value}, "
            f"error_ratio={self.error_ratio}, "
            f"response_time={self.response_time}, "
            f"broken_time={self.broken_time}, "
            f"failures={self._failure_count}, "
            f"successes={self._success_count}"
            f")"
        )


# Alias for backward compatibility with aiomisc
CircuitBroken = CircuitBrokenError