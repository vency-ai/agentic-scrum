# Agent AI Service

## 1. Overview

The Agent AI Service provides core AI functionalities to the DSM ecosystem, primarily focusing on generating text embeddings and serving language models. It is designed as a composite service that includes a dedicated language model server and a proxy service to interact with it.

This service is composed of two main components:
1.  **Ollama Server (`ollama-srv`)**: A self-hosted server for hosting and serving Large Language Models (LLMs).
2.  **Embedding Service (`embedding-service`)**: A lightweight FastAPI proxy that exposes endpoints for generating text embeddings using the models served by Ollama.

## 2. Architecture

The two components work in tandem to provide a robust and scalable AI backend:
- The **Ollama Server** runs as a stateful service with persistent storage to cache LLM models. This ensures that large model files persist across pod restarts, saving significant time and bandwidth.
- The **Embedding Service** acts as a stateless proxy that receives API requests, forwards them to the Ollama Server for processing, and returns the results. This decouples the AI model serving from the client-facing API, allowing for independent scaling and management.

---

## 3. Components

### 3.1. Ollama Server (`ollama-srv`)

This component is responsible for serving the language models required for embedding generation and other AI tasks. It is designed to be a stateful, single-replica deployment to ensure model consistency and efficient use of storage.

-   **Purpose**: Hosts and serves LLMs using the Ollama platform.
-   **Key Features**:
    -   Uses a PersistentVolume to cache models on an NFS share.
    -   Automatically pulls models specified in `models.json` on startup.
-   **Detailed Documentation**: For complete setup and deployment instructions, see the **[Ollama Server Setup Guide](./ollama-srv/README.md)**.

### 3.2. Embedding Service (`embedding-service`)

This is a high-performance, scalable microservice that provides a clean API for generating text embeddings. It is designed to be stateless and can be scaled horizontally to handle high request volumes.

-   **Purpose**: Acts as a proxy to the Ollama Server, providing a stable and authenticated endpoint for other services.
-   **Key Features**:
    -   Built with Python/FastAPI for asynchronous, non-blocking I/O.
    -   Provides endpoints for single and batch embedding generation.
    -   Includes `/health` and `/metrics` endpoints for observability.
-   **Detailed Documentation**: For complete setup and deployment instructions, see the **[Embedding Service Setup Guide](./embedding-service/README.md)**.

---

## 4. Deployment Workflow

To ensure the system functions correctly, the components must be deployed in the following order:

1.  **Deploy the Ollama Server**: The `embedding-service` depends on the `ollama-srv`, so it must be deployed and running first. Follow the instructions in its [README](./ollama-srv/README.md).
2.  **Deploy the Embedding Service**: Once the Ollama server is healthy, deploy the `embedding-service`. Follow the instructions in its [README](./embedding-service/README.md).

---

## 5. Configuration

Global configurations for the Agent AI's cognitive functions are managed via a central ConfigMap.

-   **File**: `configmaps/agent-memory-config.yaml`
-   **Purpose**: This file contains feature flags that control various aspects of the agent's memory and learning capabilities, such as:
    -   `enable_episodic_memory`
    -   `enable_working_memory`
    -   `enable_knowledge_store`
    -   `enable_async_learning`
    -   `enable_strategy_evolution`

---

## 6. Monitoring

The service is monitored via a dedicated Grafana dashboard.

-   **File**: `monitoring/grafana-dashboard-agent-memory.yaml`
-   **Purpose**: This ConfigMap defines a Grafana dashboard titled "Agent Memory Infrastructure". It includes panels for monitoring key metrics of the embedding service and related components, such as:
    -   Database Connection Pool statistics.
    -   Embedding Service Latency (p95).
    -   Total Embedding Generation Failures.
    -   Circuit Breaker State.