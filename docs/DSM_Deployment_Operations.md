# DSM Deployment & Operations Guide

This document provides comprehensive guidance for deploying, testing, and operating the DSM (Digital Scrum Master) microservices in Kubernetes environments. It incorporates recent enhancements related to comprehensive health checks, health check log filtering, and a standardized ConfigMap-based deployment strategy utilizing Python virtual environments.

For a detailed explanation of the overall system architecture, including core principles, service overview, and communication flow, please refer to the **[Architecture Overview](DSM_Architecture_Overview.md)** document. For detailed functional descriptions of Kubernetes Jobs and their roles, see **[Kubernetes Jobs Documentation](DSM_Kubernetes_Jobs.md)**.

## 1. Prerequisites

*   A running Kubernetes cluster
*   `kubectl` command-line tool configured to connect to your cluster
*   PostgreSQL databases deployed and running
*   Redis deployed and running for event processing
*   Namespace `dsm` created in the cluster

## 2. Database Setup and Migrations

### 2.1 Create Kubernetes Namespace

First, create the `dsm` namespace where all DSM components will reside.

```bash
kubectl apply -f ns-dsm.yml
```

### 2.2 Deploy PostgreSQL Databases

Deploy the PostgreSQL database instances for each service. Each service has its dedicated database following the database-per-service pattern. All PostgreSQL deployments are now configured with explicit CPU and memory requests and limits for predictable performance and efficient resource utilization.

#### 2.2.1 Main PostgreSQL Database

```bash
# Create PostgreSQL Secret for database credentials
kubectl apply -f postgres/postgres-secret.yml

# Create PostgreSQL ConfigMap for database configuration
kubectl apply -f postgres/postgres-config.yml

# Create PostgreSQL pg_hba.conf ConfigMap for client authentication
kubectl apply -f postgres/postgres-pg-hba-config.yml

# Create PostgreSQL Persistent Volume Claim for data storage
kubectl apply -f postgres/postgres-pvc.yml

# Deploy the PostgreSQL database
kubectl apply -f postgres/postgres-deployment.yml

# Create the PostgreSQL service
kubectl apply -f postgres/postgres-service.yml
```

#### 2.2.2 Service-Specific Databases

```bash
# Project Database
kubectl apply -f postgres-project/postgres-project-deployment.yml
kubectl apply -f postgres-project/postgres-project-service.yml

# Backlog Database
kubectl apply -f postgres-backlog/postgres-backlog-deployment.yml
kubectl apply -f postgres-backlog/postgres-backlog-service.yml

# Sprint Database
kubectl apply -f postgres-sprint/postgres-sprint-deployment.yml
kubectl apply -f postgres-sprint/postgres-sprint-service.yml

# Chronicle Database
kubectl apply -f postgres-chronicle/postgres-chronicle-secret.yml
kubectl apply -f postgres-chronicle/postgres-chronicle-config.yml
kubectl apply -f postgres-chronicle/postgres-chronicle-pvc.yml
kubectl apply -f postgres-chronicle/postgres-chronicle-deployment.yml
kubectl apply -f postgres-chronicle/postgres-chronicle-service.yml
```

Wait for all PostgreSQL pods to be in a `Running` state before proceeding:
```bash
kubectl get pods -n dsm -l app=postgres
```

### 2.3 Create Database Migration ConfigMaps

These ConfigMaps hold the SQL scripts necessary to create the database schemas. The order below is based on logical dependencies and versioning.

```bash
# ConfigMap for V9: Core project, team, designation, role, PTO, and holiday tables
kubectl delete configmap project-tables-sql-configmap -n dsm || true
kubectl create configmap project-tables-sql-configmap --from-file=create_project_tables.sql=postgres/migrations/V9__create_project_tables.sql -n dsm

# ConfigMap for V6: Backlog table
kubectl delete configmap backlog-tables-sql-configmap -n dsm || true
kubectl create configmap backlog-tables-sql-configmap --from-file=create_backlog_table.sql=postgres/migrations/V6__create_backlog_table.sql -n dsm

# ConfigMap for V7: Sprint, stories, sprint_stories, and story_tasks tables
kubectl delete configmap sprint-tables-sql-configmap -n dsm || true
kubectl create configmap sprint-tables-sql-configmap --from-file=create_sprint_tables.sql=postgres/migrations/V7__create_sprint_tables.sql -n dsm

# ConfigMap for V10: Additional backlog tables (tasks, stories, story_tasks)
kubectl delete configmap backlog-additional-tables-sql-configmap -n dsm || true
kubectl create configmap backlog-additional-tables-sql-configmap --from-file=create_backlog_additional_tables.sql=postgres/migrations/V10__create_backlog_additional_tables.sql -n dsm

# ConfigMap for V13: Chronicle notes table (v2 - extended schema for daily scrums)
kubectl delete configmap chronicle-notes-sql-configmap-v2 -n dsm || true
kubectl create configmap chronicle-notes-sql-configmap-v2 --from-file=create_chronicle_notes_table_v2.sql=postgres/migrations/V13__create_chronicle_notes_table_v2.sql -n dsm

# ConfigMap for dropping V11: Sprint daily scrum table (moved to Chronicle DB)
kubectl delete configmap drop-daily-scrum-updates-sql-configmap -n dsm || true
kubectl create configmap drop-daily-scrum-updates-sql-configmap --from-file=drop_daily_scrum_updates_table.sql=postgres/migrations/V14__drop_daily_scrum_updates_table.sql -n dsm

# ConfigMap for V15: Sprint retrospective tables
kubectl delete configmap chronicle-retrospective-sql-configmap -n dsm || true
kubectl create configmap chronicle-retrospective-sql-configmap --from-file=create_retrospective_tables.sql=postgres/migrations/V15__create_retrospective_tables.sql -n dsm
```

### 2.4 Apply Database Migrations

These Kubernetes Jobs execute the SQL scripts from the ConfigMaps against the PostgreSQL databases to create the necessary tables. The order of execution is crucial due to table dependencies.

For detailed database connection configurations, refer to the [Implementation Notes - Database Connection Configuration section in DSM_Data_Architecture.md](DSM_Data_Architecture.md#6.4-implementation-notes).

```bash
# Apply job to create project-related tables (from V9)
# This job creates the `project_db` database and applies its schema. For details, see [Create Project Database Job](DSM_Kubernetes_Jobs.md#21-create-project-database-job---create-project-db-jobyml).
kubectl apply -f create-project-db-job.yml

# Apply job to create backlog table (from V6)
# This job creates the `backlog_db` database and applies its schema. For details, see [Create Backlog Database Job](DSM_Kubernetes_Jobs.md#22-create-backlog-database-job---create-backlog-db-jobyml).
kubectl apply -f postgres/migrations/create-backlog-tables-job.yml

# Apply job to create sprint-related tables (from V7)
# This job creates the `sprint_db` database and applies its schema. For details, see [Create Sprint Database Job](DSM_Kubernetes_Jobs.md#23-create-sprint-database-job---postgresmigrationscreate-sprint-tables-jobyml).
kubectl apply -f postgres/migrations/create-sprint-tables-job.yml

# Apply job to create additional backlog tables (from V10)
# This job creates additional tables for the `backlog_db`. For details, see [Create Backlog Database Job](DSM_Kubernetes_Jobs.md#22-create-backlog-database-job---create-backlog-db-jobyml).
kubectl apply -f postgres/migrations/create-backlog-additional-tables-job.yml

# Apply job to create chronicle notes table (from V13 - v2)
# This job sets up the `chronicle_db` database and applies its schema. For details, see [Create Chronicle Database Job](DSM_Kubernetes_Jobs.md#24-create-chronicle-database-job---create-chronicle-db-jobyml).
kubectl apply -f create-chronicle-db-job.yml

# Apply job to drop sprint daily scrum table (from V14)
# This job removes the `daily_scrum_updates` table from the `sprint_db`. For details, see [Drop Daily Scrum Updates Job](DSM_Kubernetes_Jobs.md#25-drop-daily-scrum-updates-job---drop-daily-scrum-updates-jobyml).
kubectl apply -f drop-daily-scrum-updates-job.yml

# Apply job to create sprint retrospective tables (from V15)
# This job creates the `sprint_retrospectives` tables in the `chronicle_db`. For details, see [Create Chronicle Database Job](DSM_Kubernetes_Jobs.md#24-create-chronicle-database-job---create-chronicle-db-jobyml).
kubectl apply -f postgres/migrations/create-retrospective-tables-job.yml
```

Monitor the migration jobs to ensure they complete successfully:
```bash
kubectl get jobs -n dsm
kubectl logs -f -n dsm -l job-name=create-project-tables-job
```

### 2.5 Clean Up Migration Jobs

Once the jobs have successfully completed and the database tables are created, you can delete the job resources to keep the cluster clean. These jobs are not required after their initial run. For functional overviews of each job, refer to the **[Kubernetes Jobs Documentation - Database Schema Setup & Migration Jobs](DSM_Kubernetes_Jobs.md#2-database-schema-setup--migration-jobs)**.

```bash
# Clean up all completed migration jobs
kubectl delete job create-project-tables-job -n dsm
kubectl delete job create-backlog-tables-job -n dsm
kubectl delete job create-sprint-tables-job -n dsm
kubectl delete job create-backlog-additional-tables-job -n dsm
kubectl delete job create-chronicle-db-job -n dsm
kubectl delete job drop-daily-scrum-updates-job -n dsm
kubectl delete job create-retrospective-tables-job -n dsm
```

## 3. Service Deployment

Once the core infrastructure and database schemas are in place, the next step is to deploy the actual microservices. Each service runs as a Kubernetes Deployment and is exposed via a Kubernetes Service.

### 3.0 Common Service Deployment Strategy

All microservice deployments in the DSM system adhere to a standardized strategy:

-   **ConfigMap-based Deployment**: Source code and dependencies are copied from a ConfigMap to an `emptyDir` volume by an `initContainer`. Python dependencies are then installed into a virtual environment within that volume. The main container runs the FastAPI application from this virtual environment. This approach enables a registry-less deployment suitable for development and testing.
-   **Resource Management**: All services are configured with explicit CPU and memory requests and limits for predictable performance and efficient resource utilization.
-   **Health Checks**: All core services implement a refined health check strategy using both `startupProbe` (leveraging `/health/ready` for comprehensive dependency checks during initial startup) and `readinessProbe` (using the lightweight `/health` endpoint for ongoing process health). The `/health/ready` endpoint provides detailed JSON responses on dependency status. Uvicorn access logs for health check endpoints (`/health`, `/health/ready`) are filtered to reduce log noise. For detailed procedures on verifying service health and log filtering, refer to the **[Verifying Service Health and Log Filtering](#301-verifying-service-health-and-log-filtering)** subsection below.

### 3.0.1 Verifying Service Health and Log Filtering

After deploying services, verify their health and that health check logs are suppressed:

1.  **Check Pod Readiness**: Ensure all service pods are in a `Running` and `Ready` state.
    ```bash
    kubectl get pods -n dsm
    ```

2.  **Test Health Endpoints**: Use `kubectl exec` into `testapp-pod` (or any pod with `curl`) to hit the `/health` and `/health/ready` endpoints of each service. Verify the expected JSON responses.
    *Example for Project Service:*
    ```bash
    kubectl exec -it testapp-pod -n dsm -- curl -s http://project-service.dsm.svc.cluster.local/health
    kubectl exec -it testapp-pod -n dsm -- curl -s http://project-service.dsm.svc.cluster.local/health/ready | jq
    ```

3.  **Verify Log Filtering**: Check the logs of each service pod. You should *not* see Uvicorn access logs for `/health` or `/health/ready` requests. You *should* see logs for other application requests (e.g., API calls to create projects, tasks, etc.).
    *Example for Project Service:*
    ```bash
    POD_NAME=$(kubectl get pods -n dsm -l app=project-service -o jsonpath='{.items[0].metadata.name}')
    kubectl logs $POD_NAME -n dsm
    ```

4.  **Test Dependency Failure (Optional)**: To confirm the `/health/ready` probe's effectiveness, you can temporarily scale down a dependency (e.g., a database) and observe if dependent service pods eventually become `Not Ready`.
    *Example: Scale down project-db and observe project-service:*
    ```bash
    kubectl scale deployment/postgres-project --replicas=0 -n dsm
    kubectl get pods -n dsm -l app=project-service # Observe status change
    kubectl scale deployment/postgres-project --replicas=1 -n dsm # Scale back up
    ```

### 3.1 Test Log App (Proof of Concept)

The `test-log-app` serves as a proof of concept for health check log filtering and ConfigMap-based deployment.

#### 3.1.1 Deployment

```bash
# Create ConfigMap for test-log-app scripts
kubectl delete configmap test-log-app-config -n dsm || true
kubectl -n dsm create configmap test-log-app-config \
  --from-file=test-log-app/src/main.py \
  --from-file=test-log-app/src/log_config.py \
  --from-file=test-log-app/src/requirements.txt

# Apply test-log-app deployment
kubectl apply -f test-log-app/k8s/deployment.yml

# Apply test-log-app service
kubectl apply -f test-log-app/k8s/service.yml

# Check deployment status
kubectl get pods -n dsm -l app=test-log-app

# Check service status
kubectl get svc -n dsm test-log-app
```

### 3.2 Project Service (Projects + Calendar + Teams)


The Project Service is the foundation service that manages all project-related data, team management, and calendar operations. It now includes a comprehensive `/health/ready` endpoint and health check log filtering. For a detailed functional overview, see [Project Service](DSM_Kubernetes_Jobs.md#32-enhanced-project-service---projectsproject-servicek8sdeploymentyml--serviceyml).

#### 3.2.1 Deployment

```bash
# Create ConfigMap for Project Service scripts, including log_config.py
kubectl delete configmap project-service-scripts -n dsm || true
kubectl -n dsm create configmap project-service-scripts \
  --from-file=services/project-service/src/app.py \
  --from-file=services/project-service/src/utils.py \
  --from-file=services/project-service/src/requirements.txt \
  --from-file=services/project-service/src/log_config.py

# Apply Project Service deployment (now with initContainer for venv setup and updated probes)
kubectl apply -f services/project-service/k8s/deployment.yml

# Apply Project Service
kubectl apply -f services/project-service/k8s/service.yml

# Check deployment status
kubectl get pods -n dsm -l app=project-service

# Check service status
kubectl get svc -n dsm project-service
```

### 3.3 Backlog Service

The Backlog Service manages task backlog and story management with API integration. It now includes a comprehensive `/health/ready` endpoint (checking PostgreSQL, Redis, and Project Service) and health check log filtering. For a detailed functional overview, see [Backlog Service](DSM_Kubernetes_Jobs.md#32-backlog-service---projects/backlog-servicek8sdeploymentyml--serviceyml).

#### 3.3.1 Deployment

```bash
# Create ConfigMap for Backlog Service scripts, including log_config.py
kubectl delete configmap backlog-service-scripts -n dsm || true
kubectl -n dsm create configmap backlog-service-scripts \
  --from-file=services/backlog-service/src/app.py \
  --from-file=services/backlog-service/src/utils.py \
  --from-file=services/backlog-service/src/requirements.txt \
  --from-file=services/backlog-service/src/log_config.py

# Apply Backlog Service deployment (now with initContainer for venv setup and updated probes)
kubectl apply -f services/backlog-service/k8s/deployment.yml

# Apply Backlog Service
kubectl apply -f services/backlog-service/k8s/service.yml

# Check deployment status
kubectl get pods -n dsm -l app=backlog-service

# Check service status
kubectl get svc -n dsm backlog-service
```


### 3.3 Sprint Service

The Sprint Service handles sprint planning and progress tracking with event consumption. It is deployed with multiple replicas and protected by a Pod Disruption Budget (PDB) for enhanced high availability. It now includes a comprehensive `/health/ready` endpoint (checking PostgreSQL, Redis, Project Service, Backlog Service, and Chronicle Service) and health check log filtering. For a detailed functional overview, see [Sprint Service](DSM_Kubernetes_Jobs.md#33-sprint-service---projectssprint-servicek8sdeploymentyml--serviceyml).

#### 3.3.1 Deployment

```bash
# Create ConfigMap for Sprint Service scripts, including log_config.py
kubectl delete configmap sprint-service-scripts -n dsm || true
kubectl -n dsm create configmap sprint-service-scripts \
  --from-file=services/sprint-service/src/app.py \
  --from-file=services/sprint-service/src/utils.py \
  --from-file=services/sprint-service/src/requirements.txt \
  --from-file=services/sprint-service/src/log_config.py

# Apply Sprint Service deployment (now with multiple replicas, resource limits, initContainer, and updated probes)
kubectl apply -f services/sprint-service/k8s/deployment.yml

# Apply Sprint Service
kubectl apply -f services/sprint-service/k8s/service.yml

# Apply Pod Disruption Budget for Sprint Service
kubectl apply -f sprint-service-pdb.yml

# Check deployment status
kubectl get pods -n dsm -l app=sprint-service

# Check service status
kubectl get svc -n dsm sprint-service

# Check PDB status
kubectl get pdb -n dsm sprint-service-pdb
```


### 3.4 Daily Scrum Service

The Daily Scrum Service simulates daily work progress and publishes events to Redis Streams. It now includes health check log filtering. For a detailed functional overview, see [Daily Scrum Service](DSM_Kubernetes_Jobs.md#34-daily-scrum-service---projectsdaily-scrum-servicek8sdeploymentyml--serviceyml).

#### 3.4.1 Deployment

```bash
# Create ConfigMap for Daily Scrum Service scripts, including log_config.py
kubectl delete configmap daily-scrum-service-scripts -n dsm || true
kubectl -n dsm create configmap daily-scrum-service-scripts \
  --from-file=services/daily-scrum-service/src/app.py \
  --from-file=services/daily-scrum-service/src/utils.py \
  --from-file=services/daily-scrum-service/src/requirements.txt \
  --from-file=services/daily-scrum-service/src/log_config.py

# Apply Daily Scrum Service deployment (now with initContainer for venv setup and updated probes)
kubectl apply -f services/daily-scrum-service/k8s/deployment.yml

# Apply Daily Scrum Service
kubectl apply -f services/daily-scrum-service/k8s/service.yml

# Apply CronJob for scheduled execution
kubectl apply -f services/daily-scrum-service/k8s/cronjob.yml

# Check deployment status
kubectl get pods -n dsm -l app=daily-scrum-service

# Check service status
kubectl get svc -n dsm daily-scrum-service
```



### 3.5 Chronicle Service

The Chronicle Service manages historical records and notes, including structured sprint retrospectives and daily scrum reports. It now includes a comprehensive `/health/ready` endpoint (checking PostgreSQL) and health check log filtering. For a detailed functional overview, see [Chronicle Service](DSM_Kubernetes_Jobs.md#35-chronicle-service---projectschronicle-servicek8sdeploymentyml--serviceyml).

#### 3.5.1 Deployment

```bash
# Create ConfigMap for Chronicle Service scripts, including log_config.py
kubectl delete configmap chronicle-service-scripts -n dsm || true
kubectl -n dsm create configmap chronicle-service-scripts \
  --from-file=services/chronicle-service/src/app.py \
  --from-file=services/chronicle-service/src/utils.py \
  --from-file=services/chronicle-service/src/requirements.txt \
  --from-file=services/chronicle-service/src/log_config.py

# Apply Chronicle Service deployment (now with initContainer for venv setup and updated probes)
kubectl apply -f services/chronicle-service/k8s/deployment.yml

# Apply Chronicle Service
kubectl apply -f services/chronicle-service/k8s/service.yml

# Check deployment status
kubectl get pods -n dsm -l app=chronicle-service

# Check service status
kubectl get svc -n dsm chronicle-service
```



### 3.6 Redis Deployment

Redis is used for event processing and caching. Its deployment is now configured with explicit CPU and memory requests and limits for predictable performance and efficient resource utilization.

```bash
# Deploy Redis
kubectl apply -f redis/redis-deployment.yml
kubectl apply -f redis/redis-service.yml

# Check Redis status
kubectl get pods -n dsm -n dsm -l app=redis
kubectl get svc -n dsm redis-service
```

## 4. Setup Jobs

Setup jobs are Kubernetes Jobs that initialize individual microservices with sample data and configurations. They follow database-per-service principles and use API-driven communication for cross-service dependencies. These jobs also utilize the ConfigMap-based deployment strategy with virtual environments for their Python scripts, similar to the microservices themselves.

### 4.1 Project Setup Job

The Project Setup Job initializes the Project Service with sample projects, teams, designations, roles, and related configurations. For a detailed functional overview, see [Project Setup Job](DSM_Kubernetes_Jobs.md#41-project-setup-job---projectsproject-setupk8sproject-setup-jobyml).

```bash
# Create ConfigMap for Project Setup Job scripts
kubectl delete configmap project-setup-scripts -n dsm || true
kubectl -n dsm create configmap project-setup-scripts \
  --from-file=setups/project-setup/src/app.py \
  --from-file=setups/project-setup/src/us-holiday.json \
  --from-file=setups/project-setup/src/requirements.txt \
  --from-file=setups/project-setup/src/utils.py

# Apply Project Setup Job
kubectl apply -f setups/project-setup/k8s/project-setup-job.yml

# Monitor job execution
kubectl get jobs -n dsm project-setup-job
kubectl logs -f -n dsm -l job-name=project-setup-job
```


### 4.2 Backlog Setup Job

The Backlog Setup Job initializes the Backlog Service with sample backlog items, tasks, and stories. For a detailed functional overview, see [Backlog Setup Job](DSM_Kubernetes_Jobs.md#42-backlog-setup-job---setups/backlog-setupk8sbacklog-setup-jobyml).

```bash
# Create ConfigMap for Backlog Setup Job scripts
kubectl delete configmap backlog-setup-scripts -n dsm || true
kubectl -n dsm create configmap backlog-setup-scripts \
  --from-file=services/backlog-setup/src/app.py \
  --from-file=services/backlog-setup/src/utils.py \
  --from-file=services/backlog-setup/src/requirements.txt

# Apply Backlog Setup Job
kubectl apply -f services/backlog-setup/k8s/backlog-setup-job.yml

# Monitor job execution
kubectl get jobs -n dsm backlog-setup-job
kubectl logs -f -n dsm -l job-name=backlog-setup-job
```


### 4.3 Sprint Setup Job

The Sprint Setup Job initializes the Sprint Service with sample sprints and configurations. For a detailed functional overview, see [Sprint Setup Job](DSM_Kubernetes_Jobs.md#43-sprint-setup-job---projectssprint-setupk8ssprint-setup-jobyml).

```bash
# Create ConfigMap for Sprint Setup Job scripts
kubectl delete configmap sprint-setup-scripts -n dsm || true
kubectl -n dsm create configmap sprint-setup-scripts \
  --from-file=services/sprint-setup/src/app.py \
  --from-file=services/sprint-setup/src/requirements.txt \
  --from-file=services/sprint-setup/src/utils.py

# Apply Sprint Setup Job
kubectl apply -f services/sprint-setup/k8s/sprint-setup-job.yml

# Monitor job execution
kubectl get jobs -n dsm sprint-setup-job
kubectl logs -f -n dsm -l job-name=sprint-setup-job
```


### 4.4 Daily Scrum Setup Job

The Daily Scrum Setup Job initializes the Daily Scrum Service with sample daily scrum updates by calling the Daily Scrum Service API, which in turn sends them to the Chronicle Service. For a detailed functional overview, see [Daily Scrum Setup Job](DSM_Kubernetes_Jobs.md#44-daily-scrum-setup-job---projectsdaily-scrum-setupk8sdaily-scrum-setup-jobyml).

```bash
# Create ConfigMap for Daily Scrum Setup Job scripts
kubectl delete configmap daily-scrum-setup-scripts -n dsm || true
kubectl -n dsm create configmap daily-scrum-setup-scripts \
  --from-file=services/daily-scrum-setup/src/app.py \
  --from-file=services/daily-scrum-setup/src/requirements.txt \
  --from-file=services/daily-scrum-setup/src/utils.py

# Apply Daily Scrum Setup Job
kubectl apply -f services/daily-scrum-setup/k8s/daily-scrum-setup-job.yml

# Monitor job execution
kubectl get jobs -n dsm daily-scrum-setup-job
kubectl logs -f -n dsm -l job-name=daily-scrum-setup-job
```



## 5. Testing and Validation

This section provides guidance for testing and validating the DSM system. It now includes considerations for verifying comprehensive health checks and log filtering. For detailed information on debugging jobs and troubleshooting, refer to the **[Kubernetes Jobs Documentation - Testing, Validation, and Debugging](DSM_Kubernetes_Jobs.md#6-testing-validation-and-debugging)**.

### 5.1 Verifying Service Health and Log Filtering

For detailed procedures on verifying service health, testing health endpoints, and verifying log filtering, please refer to the **[Common Service Deployment Strategy - Verifying Service Health and Log Filtering](#301-verifying-service-health-and-log-filtering)** section.

### 5.2 API Testing Examples

This section provides `curl` commands for basic API interactions with each service. These examples can be executed from within a Kubernetes pod (e.g., `testapp-pod`) using `kubectl exec`.

#### Project Service Testing Examples

```bash
# Health Check
curl http://project-service:80/health
# Expected: {"status": "ok"}

# Create Project
curl -X POST -H "Content-Type: application/json" \
  -d '{"id": "TEST001", "name": "Test Project", "description": "A project created via API.", "status": "inactive"}' \
  http://project-service:80/projects

# List Projects
curl http://project-service:80/projects

# Get Specific Project
curl http://project-service:80/projects/TEST001

# Mark Project as Active
curl -X PUT -H "Content-Type: application/json" \
  -d '{"status": "active"}' \
  http://project-service:80/projects/TEST001/status
```

#### Backlog Service Testing Examples

```bash
# Health Check
curl http://backlog-service:80/health

# Generate Backlog
curl -X POST http://backlog-service:80/backlogs/TEST001

# Get Tasks
curl http://backlog-service:80/backlogs/TEST001

# Get Summary
curl http://backlog-service:80/backlogs/TEST001/summary

# Update Task
curl -X PUT -H "Content-Type: application/json" \
  -d '{"status": "assigned", "assigned_to": "E001"}' \
  http://backlog-service:80/tasks/TEST001-TASK001
```

#### Sprint Service Testing Examples

```bash
# Health Check
curl http://sprint-service:80/health

# Create Sprint
curl -X POST -H "Content-Type: application/json" \
  -d '{"sprint_name": "Test Sprint 1", "duration_weeks": 2}' \
  http://sprint-service:80/sprints/TEST001

# Get Sprint Details
curl http://sprint-service:80/sprints/TEST001-S01

# Update Task Progress
curl -X POST -H "Content-Type: application/json" \
  -d '{"status": "in_progress", "progress_percentage": 50}' \
  http://sprint-service:80/tasks/TEST001-TASK001/progress

# List Project Sprints
curl http://sprint-service:80/sprints/list_projects
```

#### Daily Scrum Service Testing Examples

```bash
# Health Check
curl http://daily-scrum-service:80/health

# Run Daily Scrum Simulation
curl -X POST http://daily-scrum-service:80/scrums/TEST001-S01/run

# Check Redis Events (via Redis CLI)
redis-cli XLEN daily_scrum_events
redis-cli XREAD STREAMS daily_scrum_events 0
```

#### Chronicle Service Testing Examples

```bash
# Health Check
curl http://chronicle-service:80/health
# Expected: {"status": "ok"}

# Create Sprint Retrospective Note
curl -X POST -H "Content-Type: application/json" \
  -d ",
      "sprint_id": "TEST-001-S05",
      "project_id": "TEST-001",
      "what_went_well": "Team collaborated well under pressure.",
      "what_could_be_improved": "Better backlog grooming needed.",
      "action_items": [
        {"description": "Schedule backlog refinement earlier.", "status": "open"},
        {"description": "Ensure story points are discussed during planning.", "status": "open"}
      ],
      "facilitator_id": "EMP1234",
      "attendees": ["EMP1234", "EMP4567", "EMP7890"]
    }" \
  http://chronicle-service:80/notes/sprint_retrospective
# Expected: {"message": "Sprint retrospective recorded successfully", "retrospective_id": "UUID"}
```
