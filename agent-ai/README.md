# Agent AI Service

## Overview

The Agent AI Service provides core AI functionalities to the DSM ecosystem, primarily focusing on generating text embeddings and serving language models. It is designed as a composite service that includes a dedicated language model server and a proxy service to interact with it.

This service is composed of two main components:
1.  **Ollama Server (`ollama-srv`)**: A self-hosted server for hosting and serving Large Language Models (LLMs).
2.  **Embedding Service (`embedding-service`)**: A lightweight FastAPI proxy that exposes endpoints for generating text embeddings using the models served by Ollama.

## Architecture

The two components work in tandem:
- The **Ollama Server** runs as a stateful service with persistent storage to cache LLM models, ensuring they are not re-downloaded on restarts.
- The **Embedding Service** acts as a stateless proxy that receives API requests, forwards them to the Ollama Server for processing, and returns the results. This decouples the AI model serving from the client-facing API, allowing for independent scaling and management.

---

## Components

### 1. Ollama Server (`ollama-srv`)

This component is responsible for serving the language models required for embedding generation and other AI tasks.

-   **Purpose**: Hosts and serves LLMs using the Ollama platform.
-   **Deployment**: Runs as a Kubernetes Deployment with a single replica to ensure model consistency.
-   **Storage**: Utilizes a Kubernetes PersistentVolume and PersistentVolumeClaim to store downloaded models on an NFS share. This ensures that large model files persist across pod restarts, saving significant time and bandwidth.
-   **Model Management**: The specific models to be served are defined in the `ollama-srv/models.json` file. An `entrypoint.sh` script in the Docker image reads this file on startup and automatically pulls the specified models.
-   **Documentation**: For detailed setup and deployment instructions, see the [Ollama Server README](ollama-srv/README.md).

### 2. Embedding Service (`embedding-service`)

This is a high-performance, scalable microservice that provides a clean API for generating text embeddings.

-   **Purpose**: Acts as a proxy to the Ollama Server, providing a stable and authenticated endpoint for other services to generate embeddings.
-   **Technology**: Built with Python using the FastAPI framework for asynchronous request handling.
-   **API Endpoints**:
    -   `POST /embed`: Generates an embedding for a single string of text.
    -   `POST /embed/batch`: Generates embeddings for a list of texts concurrently for better performance.
    -   `GET /health`: A health check endpoint that verifies its own status and connectivity to the Ollama server.
    -   `GET /metrics`: Exposes key performance indicators, such as request count, latency, and error rates.
-   **Deployment**: Deployed as a Kubernetes Deployment and exposed internally within the cluster via a `ClusterIP` Service. It is configured to run with multiple replicas for high availability.

---

## Configuration

Global configurations for the Agent AI's cognitive functions are managed via a central ConfigMap.

-   **File**: `configmaps/agent-memory-config.yaml`
-   **Purpose**: This file contains feature flags that control various aspects of the agent's memory and learning capabilities, such as:
    -   `enable_episodic_memory`
    -   `enable_working_memory`
    -   `enable_knowledge_store`
    -   `enable_async_learning`
    -   `enable_strategy_evolution`

---

## Monitoring

The service is monitored via a dedicated Grafana dashboard.

-   **File**: `monitoring/grafana-dashboard-agent-memory.yaml`
-   **Purpose**: This ConfigMap defines a Grafana dashboard titled "Agent Memory Infrastructure". It includes panels for monitoring key metrics of the embedding service and related components, such as:
    -   Database Connection Pool statistics.
    -   Embedding Service Latency (p95).
    -   Total Embedding Generation Failures.
    -   Circuit Breaker State.
