# DSM Setup Guide

This document provides a detailed, step-by-step guide to deploying the complete DSM (Digital Scrum Master) system on a local Kubernetes cluster.

## Prerequisites

- **Docker**: For building and running containerized services.
- **Local Kubernetes Cluster**: A running instance of `kind`, `k3d`, `minikube`, or a similar tool.
- **`kubectl`**: The Kubernetes command-line tool, configured to connect to your cluster.

## 1. Clone the Repository
First, clone the `agentic-scrum` repository to your local machine.

```bash
git clone https://github.com/vency-ai/agentic-scrum.git
cd agentic-scrum
```

## 2. Deploy Core Infrastructure
This step deploys all the necessary stateful components: the PostgreSQL databases for each microservice and the Redis instance for event streaming.

```bash
# Create the 'dsm' namespace where all resources will live
kubectl apply -f setups/ns-dsm.yml

# Deploy all database and redis resources
# These commands apply the configurations for secrets, configmaps, persistent volumes, deployments, and services.
kubectl apply -f db/postgres/
kubectl apply -f db/postgres-project/
kubectl apply -f db/postgres-backlog/
kubectl apply -f db/postgres-sprint/
kubectl apply -f db/postgres-chronicle/
kubectl apply -f db/postgres-chronicle-17-vector/
kubectl apply -f services/redis/
```
Before proceeding, wait for all database and Redis pods to be in a `Running` state. You can monitor their status with:
```bash
kubectl get pods -n dsm
```

## 3. Run Database Migrations
These Kubernetes Jobs execute SQL scripts to create the necessary database schemas and tables for each service.

```bash
kubectl apply -f db/jobs/create-project-db-job.yml
kubectl apply -f db/jobs/create-backlog-db-job.yml
# Note: Add other migration jobs here if they are not consolidated
kubectl apply -f db/jobs/create-chronicle-db-job.yml
```
Ensure these jobs complete successfully before moving to the next step. You can check their status:
```bash
kubectl get jobs -n dsm
```

## 4. Deploy All DSM Microservices
This step deploys the stateless application services, including the core "digital scrum team" and the AI components.

```bash
# Deploy the core microservices
kubectl apply -f services/project-service/
kubectl apply -f services/backlog-service/
kubectl apply -f services/sprint-service/
kubectl apply -f services/chronicle-service/

# Deploy the AI infrastructure (Ollama, Embedding Service) and the AI Orchestrator
kubectl apply -f services/agent-ai/ollama/
kubectl apply -f services/agent-ai/embedding-service/
kubectl apply -f services/project-orchestrator/

# Apply the PodDisruptionBudget to ensure high availability for the critical sprint-service
kubectl apply -f pdb/sprint-service-pdb.yml
```

## 5. Run Setup Jobs
These one-off jobs populate the newly deployed services with initial sample data (e.g., projects, teams, backlog tasks) so the system is ready to use.

```bash
kubectl apply -f setups/project-setup/
kubectl apply -f setups/backlog-setup/
kubectl apply -f setups/sprint-setup/
```

## 6. Verify the Deployment
After completing the steps above, the entire DSM system should be running. To verify and interact with it, you can deploy a temporary debugging pod that contains tools like `curl`.

```bash
# Deploy a temporary pod for API testing
kubectl apply -f Debug-tools/debug-curl-pod.yml

# Wait for the pod to enter the 'Running' state
kubectl get pod debug-pod -n dsm --watch

# Once running, you can exec into it to run commands.
# For example, check the readiness probe of the Project Orchestrator:
kubectl exec -it debug-pod -n dsm -- curl -s http://project-orchestrator.dsm.svc.cluster.local/health/ready | jq
```
A successful response will be a JSON object showing an `"ok"` status for the service and all its dependencies. You are now ready to interact with the DSM APIs to orchestrate a project.
