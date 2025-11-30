# Embedding Service Setup Guide

## 1. Overview

This guide provides step-by-step instructions for deploying the Embedding Service within the `dsm` Kubernetes namespace. This service acts as a high-performance, scalable proxy to the Ollama server, providing a stable API for generating text embeddings.

The setup includes:
- A Docker image built for production use.
- A Kubernetes Deployment to run the service with multiple replicas for high availability.
- A Kubernetes Service to expose the service to other applications within the cluster.

## 2. Prerequisites

- A running Kubernetes cluster.
- `kubectl` configured to connect to your cluster.
- A private Docker registry (`myreg.agile-corp.org:5000`) accessible from the cluster.
- An existing `docker-registry` secret named `agile-corp-reg-secret` in the `dsm` namespace for image pulls.
- The **Ollama Server** must be deployed and running within the cluster, as this service depends on it.

## 3. Build and Push Docker Image

The service is containerized and requires building and pushing the image to your private registry.

### 3.1. Dockerfile

The Dockerfile sets up a Python 3.11 environment, installs dependencies, and configures the container to run as a non-root user.

**File:** `agent-ai/embedding-service/Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (minimal)
RUN apt-get clean && apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Create non-root user
RUN useradd -m -u 1000 embeduser && chown -R embeduser:embeduser /app
USER embeduser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### 3.2. Build and Push Commands

Run these commands from the project's root directory to build the image and push it to the private registry.

```bash
# 1. Build the Docker image
docker build -t myreg.agile-corp.org:5000/embedding-service:1.0.0 -f agent-ai/embedding-service/Dockerfile agent-ai/embedding-service/

# 2. Push the Docker image
docker push myreg.agile-corp.org:5000/embedding-service:1.0.0
```

## 4. Kubernetes Deployment and Service

### 4.1. Deployment Manifest

This manifest defines the Embedding Service deployment, including replica count, resource limits, and health probes.

**File:** `agent-ai/embedding-service/k8s/embedding-service-deployment.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: embedding-service
  namespace: dsm
  labels:
    app: embedding-service
    version: "1.0.0"
spec:
  replicas: 4
  selector:
    matchLabels:
      app: embedding-service
  template:
    metadata:
      labels:
        app: embedding-service
    spec:
      containers:
      - name: embedding-service
        image: myreg.agile-corp.org:5000/embedding-service:1.0.0
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: OLLAMA_BASE_URL
          value: "http://ollama-server.dsm.svc.cluster.local:11434"
        - name: OLLAMA_MODEL
          value: "mxbai-embed-large:latest"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 30
          timeoutSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
      imagePullSecrets:
        - name: agile-corp-reg-secret
```

### 4.2. Service Manifest

This manifest exposes the Embedding Service deployment via a ClusterIP service, making it accessible to other services within the Kubernetes cluster.

**File:** `agent-ai/embedding-service/k8s/embedding-service-service.yaml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: embedding-service
  namespace: dsm
  labels:
    app: embedding-service
spec:
  type: ClusterIP
  selector:
    app: embedding-service
  ports:
  - name: http
    port: 80
    targetPort: 8000
    protocol: TCP
```

## 5. Deployment Steps

Apply the Kubernetes manifests in the following order to deploy the Embedding Service.

```bash
# 1. Apply the Deployment
kubectl apply -f agent-ai/embedding-service/k8s/embedding-service-deployment.yaml

# 2. Apply the Service
kubectl apply -f agent-ai/embedding-service/k8s/embedding-service-service.yaml
```

## 6. Verification

After applying the manifests, use these commands to verify that the deployment is successful.

```bash
# Check if the pods are running (you should see 4 replicas)
kubectl get pods -n dsm -l app=embedding-service
# Expected STATUS: Running

# Check the logs of one of the pods to ensure it started without errors
POD_NAME=$(kubectl get pods -n dsm -l app=embedding-service -o jsonpath='{.items[0].metadata.name}')
kubectl logs -f $POD_NAME -n dsm
# Expected output: "Embedding proxy service started, connecting to http://ollama-server.dsm.svc.cluster.local:11434"

# Check if the service is created
kubectl get svc embedding-service -n dsm
# Expected: A ClusterIP service is listed on port 80
```

## 7. API Endpoints

The service exposes the following RESTful endpoints for generating embeddings:

#### `POST /embed`
- **Description**: Generates an embedding for a single piece of text.
- **Request Body**: `{"text": "This is a sample sentence."}`

#### `POST /embed/batch`
- **Description**: Generates embeddings for multiple texts concurrently.
- **Request Body**: `{"texts": ["First sentence.", "Second sentence."]}`

#### `GET /health`
- **Description**: Health check endpoint used by Kubernetes probes.

#### `GET /metrics`
- **Description**: Exposes key performance indicators for monitoring.