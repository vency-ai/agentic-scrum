# CR: Comprehensive Service Observability Enhancement

## Overview

This Change Request addresses critical observability gaps in the current microservices architecture by implementing two key enhancements: comprehensive readiness probes and health check log filtering. At present, core services implement basic `/health` endpoints that only confirm process uptime, lacking validation of critical dependencies like PostgreSQL, Redis, or other interconnected services. Additionally, standard Uvicorn access logs for frequent health checks contribute to excessive log volume.

This CR proposes the implementation of new, comprehensive readiness probe endpoints (`/health/ready`) for all core services, providing a true assessment of their ability to perform functions. Concurrently, a custom logging filter will be applied to suppress Uvicorn access logs for these health check endpoints, significantly reducing log noise in production environments. This enhancement covers `test-log-app` (as a proof of concept), `project-service`, `chronicle-service`, `backlog-service`, and `sprint-service`.

## Goals

*   **Implement Comprehensive Readiness Probes**: Introduce and enhance `/health/ready` endpoints in `sprint-service`, `backlog-service`, `project-service`, and `chronicle-service` to validate critical dependencies.
*   **Implement Custom Log Filtering**: Integrate a `logging.Filter` to prevent Uvicorn access logs for `/health` and `/health/ready` endpoints from appearing in service output.
*   **Improve Service Observability**: Provide detailed, real-time status of each service and its dependencies, while reducing log noise.
*   **Enhance System Reliability**: Ensure that traffic is only routed to service instances that are fully operational and ready to serve requests.
*   **Enable Faster Issue Diagnosis**: Drastically reduce debugging time by pinpointing failures to specific dependencies through detailed health check API responses.
*   **Standardize Health Checks**: Establish a consistent pattern for health and readiness checks across all microservices in the ecosystem.
*   **ConfigMap-based Deployment**: Standardize and apply robust ConfigMap-based deployment of Python applications to Kubernetes using virtual environments, without relying on a Docker registry.

## Current State Analysis

*   **Basic Liveness Probes**: All core services have a `/health` endpoint returning a static `{"status": "ok"}`, suitable only for basic Kubernetes `livenessProbe`s.
*   **Readiness Gap**: There is no endpoint that functions as a proper `readinessProbe` validating external dependencies. Kubernetes currently considers a pod "Ready" if the process is running, even if it cannot connect to its database or other downstream services.
*   **Silent Failures**: Failures in dependencies (e.g., database connection issues) do not cause services to become "Not Ready", leading to continued traffic routing, failed requests, and difficult-to-trace silent failures.
*   **Excessive Log Volume**: Standard Uvicorn access logs are generated for all incoming HTTP requests, including frequent health checks, leading to excessive log volume that obscures critical application logs.
*   **Suboptimal Deployment**: Existing Python services may not be optimally configured for ConfigMap-based deployments with virtual environments, leading to less efficient dependency management.

## Proposed Solution

A custom `HealthCheckFilter` will be implemented and applied to the `uvicorn.access` logger for all targeted FastAPI applications. This filter will prevent access logs for `/health` and `/health/ready` from being generated, significantly reducing log noise.

To optimize resource utilization and enhance startup robustness, a refined health check strategy using both `startupProbe` and `readinessProbe` will be implemented for each core service:

*   **`startupProbe` (using `GET /health/ready`)**: This probe will be used during the initial startup phase of the pod. It will leverage the comprehensive `/health/ready` endpoint, which performs checks against all critical external dependencies (PostgreSQL, Redis, other services). This ensures that the application is fully initialized and all its dependencies are available before it is considered ready to receive traffic. The `startupProbe` will have a `failureThreshold` of 1 minute (e.g., 12 periods of 5 seconds) to accommodate slower startup times while ensuring faster detection of critical startup failures.

*   **`readinessProbe` (using `GET /health`)**: Once the `startupProbe` has succeeded, the `readinessProbe` will take over. It will use the lightweight `/health` endpoint, which simply confirms the service process is running. This reduces the constant load on backend dependencies during normal operation, as the comprehensive checks are primarily performed once at startup.

The JSON response body for `/health/ready` will continue to provide a detailed breakdown of each dependency's status, returning `200 OK` if all checks pass and `503 Service Unavailable` if any fail. The `/health` endpoint will return a static `200 OK` with `{"status": "ok"}`.

For each service, the application's source code (`app.py`, `log_config.py`, `requirements.txt`, `utils.py` where applicable) will be packaged into a Kubernetes ConfigMap. The Kubernetes Deployment will be configured with an `initContainer` to copy these files from the ConfigMap into a shared `emptyDir` volume and install Python dependencies into a virtual environment within that volume. The main application container will then execute the FastAPI application from this shared volume, utilizing the virtual environment.

## Functional Workflow

1.  **ConfigMap Creation**: The service-specific ConfigMap (e.g., `test-log-app-config`, `project-service-scripts`, etc.) is created/updated from the application's source files.
2.  **Pod Initialization**:
    *   A service pod starts.
    *   The `install-dependencies` initContainer copies necessary source files from the ConfigMap to the `/app` `emptyDir` volume.
    *   The initContainer then creates a Python virtual environment at `/app/venv` and installs dependencies from `/app/requirements.txt` into it.
3.  **Application Startup**:
    *   The main container starts.
    *   It executes the FastAPI application using the Python interpreter from `/app/venv/bin/uvicorn`.
    *   The FastAPI application starts, and the `HealthCheckFilter` is applied to the `uvicorn.access` logger.
4.  **Health Check Requests**:
    *   Kubernetes (Kubelet) or external monitoring tools make requests to `/health` and `/health/ready`.
    *   The `HealthCheckFilter` intercepts these requests, preventing their access logs from being printed to stdout.
    *   The `/health/ready` endpoint for each service performs live checks against its configured dependencies (e.g., PostgreSQL, Redis, other internal services).
    *   Based on dependency status, the `/health/ready` endpoint returns `200 OK` (ready) or `503 Service Unavailable` (not ready).
5.  **Other Requests**:
    *   Requests to other application paths (e.g., a non-existent path like `/`) are made.
    *   These requests are not filtered by `HealthCheckFilter`, and their access logs are printed to stdout.

## API Changes

### New/Enhanced Endpoints (All Services)

*   **`GET /health/ready`**
    *   **Purpose**: Provides a detailed health check of the service and its dependencies to determine if it is ready to handle traffic.
    *   **Success Response**: `200 OK` with a JSON body detailing the "ok" status of each dependency.
    *   **Failure Response**: `503 Service Unavailable` with a JSON body detailing which dependency check failed.

---

### 1. `project-service`
*   **Dependencies Checked**: PostgreSQL
*   **Response Body**:
    ```json
    {
        "service": "project-service",
        "status": "ready" | "not_ready",
        "database": "ok" | "error",
        "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff"
    }
    ```

### 2. `chronicle-service`
*   **Dependencies Checked**: PostgreSQL
*   **Response Body**:
    ```json
    {
        "service": "chronicle-service",
        "status": "ready" | "not_ready",
        "database": "ok" | "error",
        "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff"
    }
    ```

### 3. `backlog-service`
*   **Dependencies Checked**: PostgreSQL, Redis, `project-service`
*   **Response Body**:
    ```json
    {
        "service": "backlog-service",
        "status": "ready" | "not_ready",
        "database": "ok" | "error",
        "redis": "ok" | "error",
        "external_apis": {
            "project_service": "ok" | "error"
        },
        "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff"
    }
    ```

### 4. `sprint-service`
*   **Dependencies Checked**: PostgreSQL, Redis, `project-service`, `backlog-service`, `chronicle-service`
*   **Response Body**:
    ```json
    {
        "service": "sprint-service",
        "status": "ready" | "not_ready",
        "database": "ok" | "error",
        "redis": "ok" | "error",
        "external_apis": {
            "project_service": "ok" | "error",
            "backlog_service": "ok" | "error",
            "chronicle_service": "ok" | "error"
        },
        "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff"
    }
    ```

## Data Model Changes

No changes to the database data models are required for this enhancement.

## Interdependencies & Communication Flow

```mermaid
graph TD
    K8s(Kubernetes Kubelet) -->|GET /health/ready| ServiceApp(Service Application)
    ServiceApp -->|Check Connection| PostgreSQL(PostgreSQL Database)
    ServiceApp -->|PING| Redis(Redis Cache)
    ServiceApp -->|GET /health/ready| DownstreamService(Downstream Service)

    PostgreSQL -- Status --> ServiceApp
    Redis -- Status --> ServiceApp
    DownstreamService -- Status --> ServiceApp

    ServiceApp -->|Filtered Logs| SuppressedLogs[Suppressed Logs]
    ServiceApp -->|Other Logs| PodLogs[Pod Logs (stdout)]

    ServiceApp -->|200 OK / 503 Service Unavailable| K8s

    subgraph Log Filtering
        ServiceApp -- Uvicorn Access Logger --> UAL(Uvicorn Access Logger)
        UAL --> HealthCheckFilter(HealthCheckFilter)
        HealthCheckFilter -- Filtered --> SuppressedLogs
        HealthCheckFilter -- Not Filtered --> PodLogs
    end

    subgraph Deployment Flow
        User --> KubernetesAPI: kubectl apply
        KubernetesAPI --> ConfigMap: Create/Update Service ConfigMap
        KubernetesAPI --> Deployment: Create/Update Service Deployment
        Deployment --> Pod: Create Service Pod
        Pod --> InitContainer[Init Container: install-dependencies]: Copy files & Install dependencies
        InitContainer --> ConfigMap: Read source files
        InitContainer --> EmptyDirVolume: Write files & venv
        Pod --> MainContainer[Main Container: Service App]: Run FastAPI app
        MainContainer --> EmptyDirVolume: Read files & venv
    end
```

## Implementation and Verification

The implementation and verification steps were performed iteratively for each service:

### Phase 1: `test-log-app` Implementation and Verification (Proof of Concept)
*   **Status**: ✅ Completed
*   **Actions**:
    *   Created `test-log-app/src` and `test-log-app/k8s` directories.
    *   Created `test-log-app/src/main.py` with the FastAPI application.
    *   Created `test-log-app/src/log_config.py` with the `HealthCheckFilter`.
    *   Created `test-log-app/src/requirements.txt` with `fastapi` and `uvicorn` dependencies.
    *   Created `test-log-app/k8s/service.yml` for the Kubernetes Service.
    *   Deleted any pre-existing `test-log-app-config` ConfigMap.
    *   Created `test-log-app-config` ConfigMap from `main.py`, `log_config.py`, and `requirements.txt`.
    *   Created `test-log-app/k8s/deployment.yml` to mount the ConfigMap and run the application, including an `initContainer` for virtual environment setup and correct `workingDir`.
    *   Applied the Kubernetes manifests (`deployment.yml` and `service.yml`).
    *   Waited for the `test-log-app` pod to reach a `Ready` state.
    *   Retrieved logs from the `test-log-app` container to confirm "Uvicorn running" message.
    *   Provided instructions for manual verification by the user (port-forwarding and `curl` commands) to confirm log filtering.

### Phase 2: `project-service` Implementation and Verification
*   **Status**: ✅ Completed
*   **Actions**:
    *   Created `services/project-service/src/log_config.py` with the `HealthCheckFilter`.
    *   Modified `services/project-service/src/app.py` to:
        *   Import `logging`, `HealthCheckFilter`, and `JSONResponse`.
        *   Apply the `HealthCheckFilter` to `uvicorn.access` logger.
        *   Add the `/health/ready` endpoint with PostgreSQL database connectivity check.
    *   Confirmed `requirements.txt` (`fastapi`, `uvicorn`, `psycopg2-binary`, `structlog`) was sufficient.
    *   Deleted and recreated the `project-service-scripts` ConfigMap with the updated `app.py`, `log_config.py`, `requirements.txt`, and `utils.py`.
    *   Modified `services/project-service/k8s/deployment.yml` to:
        *   Include an `initContainer` for virtual environment setup, copying all necessary source files (`app.py`, `log_config.py`, `requirements.txt`, `utils.py`).
        *   Update the main container's `command` to use the virtual environment's `uvicorn`.
        *   Ensure `startupProbe` and `readinessProbe` are correctly configured to use `/health/ready` and `/health` respectively.
    *   Applied the updated Kubernetes manifests (`deployment.yml` and `service.yml`).
    *   Waited for the `project-service` pod to reach a `Ready` state.
    *   Tested `/health` and `/health/ready` endpoints from `testapp-pod` using `curl` to confirm expected JSON responses.
    *   Retrieved logs from the `project-service` pod to verify that health check requests were filtered out, while other logs (e.g., for project creation) were visible.

### Phase 3: `chronicle-service` Implementation and Verification
*   **Status**: ✅ Completed
*   **Actions**:
    *   Created `services/chronicle-service/src/log_config.py`.
    *   Modified `services/chronicle-service/src/app.py` to:
        *   Import `logging`, `HealthCheckFilter`, and `JSONResponse`.
        *   Apply the `HealthCheckFilter` to `uvicorn.access` logger.
        *   Add the `/health/ready` endpoint with PostgreSQL database connectivity check.
    *   Confirmed `requirements.txt` (`fastapi`, `uvicorn`, `psycopg2-binary`, `structlog`) was sufficient.
    *   Deleted and recreated the `chronicle-service-scripts` ConfigMap with the updated `app.py`, `log_config.py`, `requirements.txt`, and `utils.py`.
    *   Modified `services/chronicle-service/k8s/deployment.yml` to:
        *   Include an `initContainer` for virtual environment setup, copying all necessary source files.
        *   Update the main container's `command` to use the virtual environment's `uvicorn`.
        *   Ensure `startupProbe` and `readinessProbe` are correctly configured.
    *   Applied the updated Kubernetes manifests.
    *   Waited for the `chronicle-service` pod to reach a `Ready` state.
    *   Tested `/health` and `/health/ready` endpoints from `testapp-pod` using `curl` to confirm expected JSON responses.
    *   Retrieved logs from the `chronicle-service` pod to verify that health check requests were filtered out, while other logs were visible.

### Phase 4: `backlog-service` Implementation and Verification
*   **Status**: ✅ Completed
*   **Actions**:
    *   Created `services/backlog-service/src/log_config.py`.
    *   Modified `services/backlog-service/src/app.py` to:
        *   Import `logging`, `HealthCheckFilter`, `JSONResponse`, `httpx`, and `redis`.
        *   Apply the `HealthCheckFilter` to `uvicorn.access` logger.
        *   Add the `/health/ready` endpoint with PostgreSQL, Redis, and `project-service` connectivity checks.
    *   Confirmed `requirements.txt` (`fastapi`, `uvicorn`, `psycopg2-binary`, `structlog`, `httpx`, `redis`) was sufficient.
    *   Deleted and recreated the `backlog-service-scripts` ConfigMap with the updated `app.py`, `log_config.py`, `requirements.txt`, and `utils.py`.
    *   Modified `services/backlog-service/k8s/deployment.yml` to:
        *   Include an `initContainer` for virtual environment setup, copying all necessary source files.
        *   Update the main container's `command` to use the virtual environment's `uvicorn`.
        *   Ensure `startupProbe` and `readinessProbe` are correctly configured.
    *   Applied the updated Kubernetes manifests.
    *   Waited for the `backlog-service` pod to reach a `Ready` state.
    *   Tested `/health` and `/health/ready` endpoints from `testapp-pod` using `curl` to confirm expected JSON responses.
    *   Retrieved logs from the `backlog-service` pod to verify that health check requests were filtered out, while other logs were visible.

### Phase 5: `sprint-service` Implementation and Verification
*   **Status**: ✅ Completed
*   **Actions**:
    *   Created `services/sprint-service/src/log_config.py`.
    *   Modified `services/sprint-service/src/app.py` to:
        *   Import `logging`, `HealthCheckFilter`, `JSONResponse`, `httpx`, and `redis`.
        *   Apply the `HealthCheckFilter` to `uvicorn.access` logger.
        *   Add the `/health/ready` endpoint with PostgreSQL, Redis, `project-service`, `backlog-service`, and `chronicle-service` connectivity checks.
    *   Confirmed `requirements.txt` (`fastapi`, `uvicorn`, `psycopg2-binary`, `structlog`, `httpx`, `redis`) was sufficient.
    *   Deleted and recreated the `sprint-service-scripts` ConfigMap with the updated `app.py`, `log_config.py`, `requirements.txt`, and `utils.py`.
    *   Modified `services/sprint-service/k8s/deployment.yml` to:
        *   Include an `initContainer` for virtual environment setup, copying all necessary source files.
        *   Update the main container's `command` to use the virtual environment's `uvicorn`.
        *   Ensure `startupProbe` and `readinessProbe` are correctly configured.
    *   Applied the updated Kubernetes manifests.
    *   Waited for the `sprint-service` pod to reach a `Ready` state.
    *   Tested `/health` and `/health/ready` endpoints from `testapp-pod` using `curl` to confirm expected JSON responses.
    *   Retrieved logs from the `sprint-service` pod to verify that health check requests were filtered out, while other logs were visible.

## Final System State

*   The `test-log-app` pod is running and demonstrates health check log filtering.
*   All core services (`project-service`, `chronicle-service`, `backlog-service`, `sprint-service`) are running with:
    *   A functional `HealthCheckFilter` suppressing health check access logs.
    *   A comprehensive `/health/ready` endpoint that checks all relevant dependencies.
    *   A robust ConfigMap-based deployment using a virtual environment.

## Risks & Side Effects

*   **Manual Port-Forwarding**: Testing `test-log-app` requires manual port-forwarding, which is a temporary step for verification.
*   **No Persistent Storage for Venv**: The `emptyDir` volume for the virtual environment is ephemeral. This is acceptable for test/development deployments but would require persistent storage for a production deployment.
*   **Increased Load**: The comprehensive readiness probes will generate a small amount of network traffic and load on the dependencies. Given typical polling intervals, this load is expected to be negligible.

## Conclusion

This CR outlines the comprehensive implementation and verification of health check log filtering and enhanced readiness probes across core DSM microservices. These changes will significantly improve system observability, reduce log noise, and provide accurate service readiness status, contributing to a more robust and efficient microservices architecture.

### Key Benefits Realized:
-   Reduced log noise from health checks across multiple services.
-   Demonstrated and applied robust ConfigMap-based deployment for Python applications.
-   Provided a clear example for implementing custom logging filters in FastAPI/Uvicorn.
-   Enhanced core service readiness, improving system reliability and diagnosability.

## CR Status: ✅ COMPLETED
