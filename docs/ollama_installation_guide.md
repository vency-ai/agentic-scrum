# Ollama Server Offline Installation Guide

## 1. Overview

This guide provides step-by-step instructions for deploying a self-hosted Ollama server within the `dsm` Kubernetes namespace. This server is designed to work in an offline environment, hosting and serving Large Language Models (LLMs) for various AI-driven features in the DSM ecosystem.

The setup includes:
- A custom Docker image to manage model pulling.
- Persistent storage to cache downloaded models, avoiding re-downloads when pods restart.
- A Kubernetes Deployment to run the server.
- A Kubernetes Service to expose the server to other services within the cluster.

## 2. Prerequisites

- A running Kubernetes cluster.
- `kubectl` configured to connect to your cluster.
- A private Docker registry (`myreg.agile-corp.org:5000`) accessible from the cluster.
- An existing `docker-registry` secret named `agile-corp-reg-secret` in the `dsm` namespace for image pulls.
- An NFS server accessible from the cluster for persistent storage.
- Docker installed on your local machine.

## 3. File Structure

All the necessary files for this setup are located in the `agent-ai/ollama-srv/` directory.

```
agent-ai/ollama-srv/
├── Dockerfile_ollama
├── entrypoint.sh
├── k8s/
│   ├── deployment.yml
│   ├── ollama-models-pv.yml
│   ├── ollama-models-pvc.yml
│   └── service.yml
├── models.json
└── pull_models.py
```

## 4. Storage Setup (PersistentVolume & PersistentVolumeClaim)

To ensure that the downloaded LLM models persist across pod restarts, we need to set up a persistent volume.

### 4.1. Persistent Volume (PV)

**File:** `agent-ai/ollama-srv/k8s/ollama-models-pv.yml`
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ollama-models-pv
  namespace: dsm
spec:
  storageClassName: nfs-client
  capacity:
    storage: 30Gi
  accessModes:
    - ReadWriteOnce
  nfs:
    path: /nfs/k8s/gt/ollama-llm-data
    server: 10.204.32.7
  claimRef:
    name: ollama-models-pvc
    namespace: dsm
```

### 4.2. Persistent Volume Claim (PVC)

**File:** `agent-ai/ollama-srv/k8s/ollama-models-pvc.yml`
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-models-pvc
  namespace: dsm
spec:
  storageClassName: nfs-client
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 30Gi
  volumeName: ollama-models-pv
```

## 5. Configuration (ConfigMap)

A ConfigMap manages the `models.json` file, which specifies which models the Ollama server should download on startup.

### 5.1. `models.json`

```json
{
  "models": [
    "mxbai-embed-large:latest",
    "llama3.2:latest",
    "all-minilm:l6-v2"
  ]
}
```

### 5.2. Create the ConfigMap

```bash
kubectl create configmap ollama-models-config \
  --from-file=agent-ai/ollama-srv/models.json \
  -n dsm --dry-run=client -o yaml | kubectl apply -f -
```

## 6. Build and Push Docker Image

The server runs from a custom Docker image that contains the application and a startup script to pull the required models.

### 6.1. Dockerfile

**File:** `agent-ai/ollama-srv/Dockerfile_ollama`
```dockerfile
FROM ubuntu:22.04

# Install curl + jq + Ollama
RUN apt-get update && apt-get install -y curl jq gnupg \
 && curl -fsSL https://ollama.com/install.sh | sh

# Set path to Ollama
ENV PATH="/root/.ollama/bin:$PATH"

# Copy model config
WORKDIR /app
COPY models.json .

# Expose Ollama port
EXPOSE 11434

# Entry script that starts Ollama and pulls models
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
```

### 6.2. `entrypoint.sh`

This script starts the Ollama server, pulls the models listed in `models.json`, and then restarts the server in the foreground.

```bash
#!/bin/bash

# Start Ollama server in background just to pull models
echo "📦 Pulling models from models.json..."
ollama serve &
OLLAMA_PID=$!

# Wait a bit for the Ollama server to become ready
sleep 5

# Pull each model from JSON
jq -r '.models[]' models.json | while read model; do
  echo "📥 Pulling model: $model"
  ollama pull "$model"
done

# Stop the temporary background Ollama
kill $OLLAMA_PID
wait $OLLAMA_PID 2>/dev/null

echo "🚀 Starting Ollama server in foreground..."
# This keeps container logs active and useful
exec ollama serve
```

### 6.3. Build and Push Commands

```bash
# 1. Build the Docker image
docker build -t myreg.agile-corp.org:5000/ollama-server:1.0.0 -f agent-ai/ollama-srv/Dockerfile_ollama agent-ai/ollama-srv/

# 2. Push the Docker image
docker push myreg.agile-corp.org:5000/ollama-server:1.0.0
```

## 7. Kubernetes Deployment and Service

### 7.1. Deployment Manifest

**File:** `agent-ai/ollama-srv/k8s/deployment.yml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama-server
  namespace: dsm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama-server
  template:
    metadata:
      labels:
        app: ollama-server
    spec:
      containers:
      - name: ollama
        image: myreg.agile-corp.org:5000/ollama-server:1.0.0
        ports:
        - containerPort: 11434
        env:
        - name: OLLAMA_HOST
          value: "0.0.0.0:11434"
        volumeMounts:
        - name: ollama-models-storage
          mountPath: /root/.ollama/models
        - name: ollama-models-config
          mountPath: /app/models.json
          subPath: models.json
      volumes:
      - name: ollama-models-storage
        persistentVolumeClaim:
          claimName: ollama-models-pvc
      - name: ollama-models-config
        configMap:
          name: ollama-models-config
      imagePullSecrets:
      - name: agile-corp-reg-secret
```

### 7.2. Service Manifest

**File:** `agent-ai/ollama-srv/k8s/service.yml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: ollama-server
  namespace: dsm
spec:
  selector:
    app: ollama-server
  ports:
    - protocol: TCP
      port: 11434
      targetPort: 11434
  type: ClusterIP
```

## 8. Deployment Steps

Apply the Kubernetes manifests in the following order to deploy the Ollama server.

```bash
# 1. Apply the PersistentVolume
kubectl apply -f agent-ai/ollama-srv/k8s/ollama-models-pv.yml

# 2. Apply the PersistentVolumeClaim
kubectl apply -f agent-ai/ollama-srv/k8s/ollama-models-pvc.yml

# 3. Apply the Deployment
kubectl apply -f agent-ai/ollama-srv/k8s/deployment.yml

# 4. Apply the Service
kubectl apply -f agent-ai/ollama-srv/k8s/service.yml
```

## 9. Verification

After applying the manifests, use these commands to verify that the deployment is successful.

### 9.1. Check PVC Status

```bash
kubectl get pvc ollama-models-pvc -n dsm
```
**Expected Output:**
```
NAME                STATUS   VOLUME             CAPACITY   ACCESS MODES   STORAGECLASS   AGE
ollama-models-pvc   Bound    ollama-models-pv   30Gi       RWO            nfs-client     3m30s
```

### 9.2. Check Pod Status

```bash
kubectl get pods -n dsm -l app=ollama-server
```
**Expected Output:**
```
NAME                            READY   STATUS    RESTARTS   AGE
ollama-server-f95964746-ngsdw   1/1     Running   0          2m17s
```

### 9.3. Check Logs

```bash
# Get the pod name
POD_NAME=$(kubectl get pods -n dsm -l app=ollama-server -o jsonpath='{.items[0].metadata.name}')

# View the logs
kubectl logs -f $POD_NAME -n dsm
```
**Expected Output:** The logs should show the models being pulled successfully, followed by the server starting.
```
... (model pulling logs) ...
verifying sha256 digest
writing manifest
success
🚀 Starting Ollama server in foreground...
time=2025-10-13T17:40:40.710Z level=INFO source=routes.go:1481 msg="server config" env="map[...]