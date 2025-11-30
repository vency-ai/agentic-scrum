# Ollama Server Local Setup Guide

## 1. Overview

This guide provides step-by-step instructions for deploying a self-hosted Ollama server within the `dsm` Kubernetes namespace. This server will host and serve Large Language Models (LLMs) for various AI-driven features in the DSM ecosystem.

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

## 3. Storage Setup (PersistentVolume & PersistentVolumeClaim)

To ensure that the downloaded LLM models persist across pod restarts, we need to set up a persistent volume.

### 3.1. Persistent Volume (PV)

This manifest defines the physical storage location on the NFS server.

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

### 3.2. Persistent Volume Claim (PVC)

This manifest requests storage and binds to the PersistentVolume created above.

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

## 4. Configuration (ConfigMap)

A ConfigMap is used to manage the `models.json` file, which specifies which models the Ollama server should download on startup.

### 4.1. Create the ConfigMap

This command creates the `ollama-models-config` ConfigMap from the local `models.json` file.

```bash
kubectl create configmap ollama-models-config \
  --from-file=agent-ai/ollama-srv/models.json \
  -n dsm --dry-run=client -o yaml | kubectl apply -f -
```

## 5. Build and Push Docker Image

The Ollama server runs from a custom Docker image that contains the application and a startup script to pull the required models.

### 5.1. Dockerfile

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

### 5.2. Build and Push Commands

Run these commands from the root of the project directory to build the image and push it to the private registry.

```bash
# 1. Build the Docker image
docker build -t myreg.agile-corp.org:5000/ollama-server:1.0.0 -f agent-ai/ollama-srv/Dockerfile_ollama agent-ai/ollama-srv/

# 2. Push the Docker image
docker push myreg.agile-corp.org:5000/ollama-server:1.0.0
```

## 6. Kubernetes Deployment and Service

### 6.1. Deployment Manifest

This manifest defines the Ollama server deployment, mounting the persistent volume for model storage and the ConfigMap for the model list.

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

### 6.2. Service Manifest

This manifest exposes the Ollama deployment via a ClusterIP service, making it accessible to other services within the Kubernetes cluster.

**File:** `agent-ai/ollama-srv/k8s/service.yml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: ollama-server-svc
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

## 7. Deployment Steps

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

## 8. Verification

After applying the manifests, use these commands to verify that the deployment is successful.

```bash
# Check if the PVC is bound to the PV
kubectl get pvc ollama-models-pvc -n dsm
# Expected STATUS: Bound

# Check if the Ollama pod is running
kubectl get pods -n dsm -l app=ollama-server
# Expected STATUS: Running

# Check the logs to see the model pulling process
POD_NAME=$(kubectl get pods -n dsm -l app=ollama-server -o jsonpath='{.items[0].metadata.name}')
kubectl logs -f $POD_NAME -n dsm
# Expected output: Logs showing models being pulled, followed by "Starting Ollama server in foreground..."

# Check if the service is created
kubectl get svc ollama-server-svc -n dsm
# Expected: A ClusterIP service is listed
```