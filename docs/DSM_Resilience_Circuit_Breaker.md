# DSM Architecture: Resilience Patterns

## 1. Overview

In a distributed microservices ecosystem like the Digital Sprint Manager (DSM), ensuring resilience and fault tolerance is paramount. Services frequently communicate with each other, and failures in one downstream service can cascade, leading to widespread outages. To mitigate this, the DSM platform has adopted a standardized approach to resilience for inter-service communication.

This document outlines the design, architecture, and implementation of the **Circuit Breaker pattern**, which has been integrated into key services to protect them from downstream failures and enhance overall system stability. This pattern is a foundational element of our strategy for building a robust, self-healing, and fault-tolerant system.

The Circuit Breaker pattern has been implemented in the following services:
*   **Backlog Service**: Protecting calls to the Project Service.
*   **Sprint Service**: Protecting calls to the Project, Backlog, and Chronicle services.
*   **Project Orchestrator Service**: Protecting calls to the Project, Backlog, Sprint, and Chronicle services.

## 2. The Custom Circuit Breaker Implementation

### 2.1. Rationale for a Custom Solution

During the initial implementation phase, several third-party libraries were evaluated, including `aiobreaker` and `aiomisc`. However, both presented significant challenges in our production environment:

*   **`aiobreaker`**: Exhibited unreliable behavior when integrated with the FastAPI asynchronous framework, failing to consistently open the circuit and transform underlying exceptions as expected.
*   **`aiomisc` (v13.0.0)**: Was found to have a **fundamental bug in its async context manager support**. The `__aenter__` method was not correctly implemented, causing `AttributeError` exceptions when used with the `async with` syntax, which is essential for our `httpx`-based service clients.

Given the critical need for a reliable, non-blocking, and async-native solution, the decision was made to develop a **custom, in-house Circuit Breaker implementation**. This approach provided full control, ensured seamless integration with our FastAPI/`httpx` stack, and eliminated dependencies on broken or unreliable external libraries. The custom implementation was first developed for the Sprint Service and subsequently rolled out as the standard across all other services.

### 2.2. Key Features of the Custom Implementation

The custom `CircuitBreaker` is a production-ready solution with the following features:
*   **Reliable Asynchronous Support**: Natively designed for `asyncio`, ensuring non-blocking operation within the FastAPI event loop.
*   **Correct `async with` Context Manager**: Provides fully functional `__aenter__` and `__aexit__` methods for idiomatic use with `httpx` clients.
*   **Sliding Window Failure Tracking**: Monitors failure rates over a configurable time window (`response_time`) based on a defined error ratio (`error_ratio`).
*   **Standard Three-State Operation**: Implements the classic CLOSED, OPEN, and HALF-OPEN states for robust fault tolerance.
*   **API Compatibility**: Designed with a similar constructor API to libraries like `aiomisc` for consistency and ease of use.

## 3. Circuit Breaker Functionality Explained

The custom `CircuitBreaker` follows the classic pattern with three distinct states:

#### **1. Closed State (Normal Operation)**
- This is the **default state**. All requests to the downstream service are allowed to pass through.
- The circuit breaker continuously monitors each call for failures (e.g., connection errors, 5xx responses).
- If the failure rate remains below the configured threshold, the circuit stays **CLOSED**.

#### **2. Open State (Failure Protection)**
- If the failure rate exceeds the threshold (e.g., 50% of requests fail within 10 seconds), the circuit **"trips"** and transitions to the **OPEN** state.
- In this state, the circuit breaker **immediately rejects** all subsequent requests without attempting to contact the downstream service. This is the "fail-fast" mechanism.
- It returns a `CircuitBrokenError` instantly, preventing the service from waiting for long timeouts and conserving resources.
- The circuit remains OPEN for a configured `broken_time` (e.g., 30 seconds), giving the downstream service time to recover.

#### **3. Half-Open State (Recovery Testing)**
- After the `broken_time` expires, the circuit transitions to the **HALF-OPEN** state.
- In this state, it allows a **single trial request** to pass through to the downstream service.
- **If the trial request succeeds**: The circuit breaker assumes the service has recovered and transitions back to the **CLOSED** state, resuming normal operation.
- **If the trial request fails**: The circuit breaker immediately returns to the **OPEN** state for another `broken_time` period to avoid flooding a still-unhealthy service.

### Operational Flow

**Normal Flow (Closed State):**
```
Client → Service → Circuit Breaker → Downstream Service → Success → Client
```

**Failure Detection (Transitioning to Open):**
```
Client → Service → Circuit Breaker → Downstream Service → Error
                   ↓ (Failure count increases)
Client → Service → Circuit Breaker → Downstream Service → Error
                   ↓ (Failure threshold reached)
              [Circuit Opens]
```

**Protection Mode (Open State):**
```
Client → Service → Circuit Breaker → [BLOCKED] → CircuitBrokenError → 503 Response → Client
                                ↓
                 (No call to Downstream Service)
```

**Recovery Testing (Half-Open State):**
```
[After 30 seconds]
Client → Service → Circuit Breaker → [TRIAL CALL] → Downstream Service
                                     ↓
                             Success: Close Circuit
                             Failure: Reopen Circuit
```

## 4. Standard Configuration

The custom circuit breaker is instantiated with a standard set of parameters, allowing for consistent configuration across all services while remaining tunable for specific needs.

```python
# Standard configuration for a service's circuit breaker
from circuit_breaker import CircuitBreaker

# Example: Circuit breaker for calls to the Project Service
project_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,        # Open circuit if 50% of calls fail
    response_time=10,       # Monitor failures within a 10-second window
    exceptions=[Exception], # Count all exceptions as failures
    broken_time=30          # Stay open for 30 seconds before attempting recovery
)
```

- **`error_ratio`**: The percentage of failures within the `response_time` window that will cause the circuit to open.
- **`response_time`**: The duration of the sliding window (in seconds) for monitoring failures.
- **`exceptions`**: A list of exception types to be treated as failures. `Exception` is typically used to catch all issues.
- **`broken_time`**: The duration (in seconds) the circuit will remain open before transitioning to half-open.

## 5. Architectural Integration and Service Implementations

The circuit breaker is integrated at the service-to-service communication layer. In each microservice, a `utils.py` or `service_clients.py` file encapsulates the `httpx` calls to downstream dependencies. The circuit breaker is applied to these outgoing calls using the `async with` pattern. A global exception handler in `app.py` catches the `CircuitBrokenError` and returns a standard `HTTP 503 Service Unavailable` response.

### 5.1. Backlog Service

*   **Protected Dependency**: Project Service.
*   **Flow Diagram**:
    ```mermaid
    graph TD
        A[Client Request] --> B[Backlog Service]
        B --> C{Custom Circuit Breaker}
        C -->|CLOSED/HALF_OPEN| D[Project Service Call]
        C -->|OPEN| E[HTTP 503 Response]
        D -->|Success| F[Process Backlog/Tasks]
        D -->|Failure| G[Circuit Opens]
        F --> H[Backlog Processed]
        G --> E
        E --> I[Client Receives 503]
        H --> J[Client Receives Success]
    ```

### 5.2. Sprint Service

*   **Protected Dependencies**: Project Service, Backlog Service, Chronicle Service.
*   **Flow Diagram**:
    ```mermaid
    graph TD
        A[Sprint Creation Request] --> B[Sprint Service]
        B --> C{Custom Circuit Breaker}
        C -->|CLOSED/HALF_OPEN| D[Project Service Call]
        C -->|OPEN| E[HTTP 503 Response]
        D -->|Success| F[Backlog Service Call]
        D -->|Failure| G[Circuit Opens]
        F -->|Success| H[Task Assignment]
        F -->|Failure| G
        H --> I[Sprint Created with Tasks]
        G --> E
        E --> J[Client Receives 503]
        I --> K[Client Receives 201]
    ```

### 5.3. Project Orchestrator Service

*   **Protected Dependencies**: Project Service, Backlog Service, Sprint Service, Chronicle Service.
*   **Flow Diagram**:
    ```mermaid
    graph TD
    A[Client Request] --> B[Project Orchestrator]
    B --> C{Custom Circuit Breaker Layer}

    C -->|Call Service 1| D1[Project Service]
    C -->|Call Service 2| D2[Backlog Service]
    C -->|Call Service 3| D3[Sprint Service]
    C -->|Call Service 4| D4[Chronicle Service]

    D1 -->|Service 1 Response| E
    D2 -->|Service 2 Response| E
    D3 -->|Service 3 Response| E
    D4 -->|Service 4 Response| E

    E[Aggregated Responses / Failures] --> F[Orchestration Logic]
    F --> G[Generate Orchestration Response]
    G --> H[Client Receives Response]

    %% FIXED LABEL — avoid special characters like () directly
    C -->|"Circuit Open → Fallback"| I[HTTP 503: Service Unavailable]
    I --> H

    %% Optional Styling (optional — if you want to make it easier to read)
    classDef node fill:#e3f2fd,stroke:#0288d1,stroke-width:2px,color:#01579b
    class A,B,C,D1,D2,D3,D4,E,F,G,H,I node

    %% Improve connector line visibility
    linkStyle default stroke:#ffffff,stroke-width:2.5px

    ```

## 6. Standard Deployment and Testing

### 6.1. Deployment Process

The integration of the circuit breaker follows a standard workflow:
1.  **Add Module**: The custom `circuit_breaker.py` module is added to the service's source code directory.
2.  **Update Dockerfile**: The `Dockerfile` is updated to ensure `circuit_breaker.py` is copied into the image.
3.  **Integrate Logic**: Service client methods are updated to use the `async with circuit_breaker.context()` pattern.
4.  **Add Exception Handler**: An exception handler for `CircuitBrokenError` is added to the main `app.py` file.
5.  **Build and Push**: A new versioned Docker image is built and pushed to the private registry.
6.  **Deploy**: The Kubernetes `deployment.yml` is updated with the new image tag and applied to the cluster using `kubectl apply`.

### 6.2. Build, Push, and Deploy Images

#### Backlog Service
*   **Build and Push Docker Image**:
    *   **Action**: Build the Docker image for the `backlog-service` with the custom circuit breaker, tag it with version `1.2.4`, and push it to the private registry.
    *   **Commands**:
        ```bash
        docker build -t myreg.agile-corp.org:5000/backlog-service:1.2.4 services/backlog-service/
        docker push myreg.agile-corp.org:5000/backlog-service:1.2.4
        ```
*   **Update and Verify Deployment**:
    *   **Action**: Update the `image` tag in the Kubernetes deployment manifest, redeploy the service, and verify the rollout.
    *   **Commands**:
        ```bash
        # Ensure the deployment.yml has the correct image tag (e.g., 1.2.4)
        # Force a new deployment by deleting the old one
        kubectl delete deployment backlog-service -n dsm
        # Create the deployment with the new configuration
        kubectl apply -f services/backlog-service/k8s/deployment.yml
        # Verify the rollout status
        kubectl rollout status deployment/backlog-service -n dsm
        ```

#### Sprint Service
*   **Build and Push Docker Image**:
    *   **Action**: Build the Docker image for the `sprint-service` with the custom circuit breaker, tag it with version `1.2.0`, and push it to the private registry.
    *   **Commands**:
        ```bash
        docker build -t myreg.agile-corp.org:5000/sprint-service:1.2.0 services/sprint-service/
        docker push myreg.agile-corp.org:5000/sprint-service:1.2.0
        ```
*   **Update and Verify Deployment**:
    *   **Action**: Update the `image` tag in the Kubernetes deployment manifest, redeploy the service, and verify the rollout.
    *   **Commands**:
        ```bash
        # Ensure the deployment.yml has the correct image tag (e.g., 1.2.0)
        # Force a new deployment by deleting the old one
        kubectl delete deployment sprint-service -n dsm
        # Create the deployment with the new configuration
        kubectl apply -f services/sprint-service/k8s/deployment.yml
        # Verify the deployment status
        kubectl get pods -n dsm | grep sprint-service
        ```

#### Project Orchestrator Service
*   **Build and Push Docker Image**:
    *   **Action**: Build the Docker image for the `project-orchestrator` service with the custom circuit breaker, tag it with version `1.1.0`, and push it to the private registry.
    *   **Commands**:
        ```bash
        docker build -t myreg.agile-corp.org:5000/project-orchestrator:1.1.0 services/project-orchestrator/
        docker push myreg.agile-corp.org:5000/project-orchestrator:1.1.0
        ```
*   **Update and Verify Deployment**:
    *   **Action**: Update the `image` tag in the Kubernetes deployment manifest, redeploy the service, and verify the rollout.
    *   **Commands**:
        ```bash
        # Ensure the deployment.yml has the correct image tag (e.g., 1.1.0)
        # Force a new deployment by deleting the old one
        kubectl delete deployment project-orchestrator -n dsm
        # Create the deployment with the new configuration
        kubectl apply -f services/project-orchestrator/k8s/deployment.yml
        # Verify the deployment status
        kubectl get pods -n dsm | grep project-orchestrator
        ```

### 6.3. Validation and Testing Strategy

A consistent testing strategy is used to validate the circuit breaker's functionality in a live environment:
1.  **Simulate Failure**: The downstream dependency is scaled down to zero replicas to make it unavailable.
    ```bash
    kubectl scale deployment <dependency-service-name> -n dsm --replicas=0
    ```
2.  **Verify Circuit Opening**: Multiple requests are sent to the service under test. After a few initial failures, subsequent requests should fail immediately with an `HTTP 503` status, confirming the circuit is open.
3.  **Simulate Recovery**: The downstream dependency is scaled back up to one replica.
    ```bash
    kubectl scale deployment <dependency-service-name> -n dsm --replicas=1
    ```
4.  **Verify Circuit Closing**: After the `broken_time` has elapsed, new requests are sent. They should now succeed, confirming the circuit has transitioned through the half-open state and is now closed.

### 6.4. Detailed Testing and Validation Logs

This section provides a summary of the actual test results and observations gathered during the implementation and validation of the circuit breaker pattern in each service.

#### Backlog Service
*   **Test Environment**: `backlog-service` (v1.2.4) with custom circuit breaker deployed. `project-service` is the dependency under test.
*   **Test 1: Circuit Opening**
    1.  **Setup**: The `project-service` was scaled to 0 replicas.
    2.  **Action**: Multiple requests were sent to the backlog generation endpoint: `curl -X POST http://backlog-service.dsm.svc.cluster.local/backlogs/TEST001`
    3.  **Result**: ✅ **Success**. After the initial requests failed (as expected), the circuit breaker opened. Subsequent calls failed immediately.
    4.  **Logs**: Service logs clearly showed the state transition: `"Trial call failed, circuit breaker opened"` followed by `"Timeout not elapsed yet, circuit breaker still open"` for subsequent requests.
    5.  **HTTP Status**: With the final custom implementation, the service correctly returned an **HTTP 503 Service Unavailable** status code, confirming the exception handler was working as designed. (Note: An earlier implementation with `aiomisc` incorrectly returned 500, an issue that was resolved by the custom module).

*   **Test 2: Circuit Closing (Recovery)**
    1.  **Setup**: The `project-service` was scaled back to 1 replica.
    2.  **Action**: After the 30-second `broken_time` expired, a new request was sent to the same endpoint.
    3.  **Result**: ✅ **Success**. The service successfully communicated with the recovered `project-service`, and the request was processed normally, returning an HTTP 200 status. The circuit correctly transitioned to the CLOSED state.

#### Sprint Service
*   **Test Environment**: `sprint-service` (v1.2.0) with custom circuit breaker deployed. Tests were performed against its three dependencies: `project-service`, `backlog-service`, and `chronicle-service`.
*   **Key Feature Tested**: Graceful Degradation. The Sprint Service is designed to maintain core functionality even if a dependency is down.

*   **Test 1: Project Service Failure**
    1.  **Setup**: `project-service` scaled to 0 replicas.
    2.  **Action**: A new sprint was created: `curl -X POST -d '{"sprint_name": "CB Test Sprint", "duration_weeks": 2}' http://sprint-service.dsm.svc.cluster.local/sprints/CB-TEST-001`
    3.  **Result**: ✅ **Success**. The circuit breaker for the project service opened, but the sprint was still created successfully (**HTTP 201**) with a graceful degradation message, as project validation is a non-critical step.

*   **Test 2: Backlog Service Failure**
    1.  **Setup**: `backlog-service` scaled to 0 replicas.
    2.  **Action**: A new sprint was created.
    3.  **Result**: ✅ **Success**. The circuit breaker for the backlog service opened. The sprint was created, but the service gracefully handled the failure to assign tasks from the backlog.

*   **Test 3: Chronicle Service Failure**
    1.  **Setup**: `chronicle-service` scaled to 0 replicas.
    2.  **Action**: Daily scrum operations were triggered, which normally post reports to the Chronicle Service.
    3.  **Result**: ✅ **Success**. The circuit breaker for the chronicle service opened, and the daily scrum process completed successfully while logging the failure to communicate with the chronicle service.

#### Project Orchestrator Service
*   **Test Environment**: `project-orchestrator` (v1.1.0) with custom circuit breakers for each of its four dependencies.
*   **Test 1: Circuit Opening (Project Service)**
    1.  **Setup**: `project-service` scaled to 0 replicas.
    2.  **Action**: The orchestration status endpoint was called: `curl -s -w "%{{http_code}}
" -X GET ... http://project-orchestrator.dsm.svc.cluster.local/orchestrate/project/PROJ-001/status`
    3.  **Result**: ✅ **Success**. All calls consistently and immediately returned an **HTTP 503** status code.
    4.  **Error Message**: The response body correctly identified the source of the failure: `{"detail":"Could not connect to Project Service: All connection attempts failed"}`.

*   **Test 2: Circuit Closing and Service-Level Errors**
    1.  **Setup**: `project-service` was scaled back to 1 replica. Note: The underlying database for the project service was known to be in a faulty state.
    2.  **Action**: The same orchestration status endpoint was called again.
    3.  **Result**: ✅ **Success**. The circuit breaker correctly closed and allowed the request to pass through. The orchestrator then received a service-level error from the `project-service` and returned an **HTTP 500** status code.
    4.  **Key Observation**: This test successfully demonstrated the circuit breaker's ability to distinguish between a **connection failure (503)** and a **downstream application error (500)**, which is critical for accurate system monitoring.


## 7. Benefits and Risks

### 7.1. Benefits Achieved

*   **Cascading Failure Prevention**: Isolates failures and prevents them from propagating through the system.
*   **Fast Failure Response**: Provides immediate feedback to clients when a downstream service is unavailable, avoiding long timeouts.
*   **Resource Conservation**: Prevents the exhaustion of connection pools, threads, and other resources by not attempting to contact a known-failing service.
*   **Automatic Recovery**: Provides a self-healing mechanism that automatically detects when a downstream service has recovered.
*   **Graceful Degradation**: Enables services like the Project Orchestrator and Sprint Service to continue operating with reduced or partial functionality when a dependency is down.

### 7.2. Risks and Mitigations

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Custom Implementation Maintenance** | The custom circuit breaker requires internal maintenance instead of relying on an external library. | The implementation is simple, well-documented, and follows established software patterns. It has been thoroughly tested across multiple services, reducing the maintenance burden. |
| **Configuration Tuning** | The circuit breaker's `error_ratio`, `response_time`, and `broken_time` values may need tuning for optimal performance in different environments. | We start with sensible, conservative defaults and monitor service behavior and logs under load. Parameters can be adjusted via environment variables without code changes if tuning is required. |

## 8. Conclusion

The standardized, custom Circuit Breaker implementation is a cornerstone of the DSM platform's resilience strategy. By moving away from unreliable third-party libraries and creating a solution tailored to our asynchronous architecture, we have significantly improved the stability and fault tolerance of our key services. This pattern ensures that our system can handle transient failures gracefully, prevent cascading outages, and maintain a high level of availability, which is essential for a mission-critical application.

## Related Documentation

- **[DSM Architecture Overview](DSM_Architecture_Overview.md)** - The main architecture document providing a high-level overview of the DSM system.

## Appendix: Circuit Breaker Configurations

### Backlog Service
```python
project_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,  # Open circuit if 50% of calls fail
    response_time=10, # Monitor failures within a 10-second window
    exceptions=(httpx.RequestError, httpx.HTTPStatusError), # Count these as failures
    broken_time=30    # Stay open for 30 seconds before attempting recovery
)
```

### Project Orchestrator Service
```python
# Individual circuit breakers for each service dependency
project_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,  # Open if 50% of calls fail
    response_time=10, # Monitor failures within a 10-second window
    exceptions=(httpx.RequestError, httpx.HTTPStatusError),
    broken_time=30    # Stay open for 30 seconds before attempting recovery
)

backlog_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5, response_time=10,
    exceptions=(httpx.RequestError, httpx.HTTPStatusError), broken_time=30
)

sprint_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5, response_time=10,
    exceptions=(httpx.RequestError, httpx.HTTPStatusError), broken_time=30
)

chronicle_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5, response_time=10,
    exceptions=(httpx.RequestError, httpx.HTTPStatusError), broken_time=30
)
```

### Sprint Service
```python
# Individual circuit breakers for each service dependency
project_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,  # Open if 50% of calls fail
    response_time=10, # Monitor failures within a 10-second window
    exceptions=[httpx.RequestError, httpx.HTTPStatusError],
    broken_time=30    # Stay open for 30 seconds before attempting recovery
)

backlog_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5, response_time=10,
    exceptions=[httpx.RequestError, httpx.HTTPStatusError], broken_time=30
)

chronicle_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5, response_time=10,
    exceptions=[httpx.RequestError, httpx.HTTPStatusError], broken_time=30
)
```
