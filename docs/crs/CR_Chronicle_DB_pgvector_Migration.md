# CR: Migrate Chronicle DB to PostgreSQL 17 with pgvector Extension

## Overview

This document outlines the plan to migrate the `chronicle-db` PostgreSQL 17 database to a new instance based on a custom Docker image that includes the `pgvector` extension. The primary objective is to enable vector similarity search capabilities for future AI-driven features, such as analyzing historical sprint data for patterns. This migration will follow the same proven blue-green deployment strategy used in the previous v13 to v17 upgrade to ensure zero data loss and minimal service disruption.

## Goals

*   **Goal 1**: Successfully migrate the live `chronicle-db` from a standard PostgreSQL v17 instance to a `pgvector`-enabled v17 instance.
*   **Goal 2**: Ensure no data is lost during the migration process.
*   **Goal 3**: Achieve a zero-downtime cutover from the old database to the new one.
*   **Goal 4**: Validate that the `chronicle-service` functions correctly and that the `vector` extension is active in the new database.

## Current State Analysis

*   **Current Behavior**: The `chronicle-db` is running on `postgres:17` as a Kubernetes Deployment, following the successful migration documented in `CR_Chronicle_DB_Upgrade_v17.md`.
*   **Dependencies**: The `chronicle-service` is directly dependent on this database.
*   **Gaps/Issues**: The current database instance lacks the `pgvector` extension, which is a prerequisite for implementing new features that rely on semantic search and vector embeddings of historical project data.
*   **Configuration**: The database is deployed in the `dsm` namespace, using a `Deployment`, `Service`, `ConfigMap`, `Secret`, and a `PersistentVolumeClaim`.

## Proposed Solution

We will replicate the blue-green deployment strategy from the previous database upgrade. A new, parallel PostgreSQL 17 instance with `pgvector` (the "green" environment) will be deployed alongside the existing v17 instance (the "blue" environment).

The migration will proceed as follows:
1.  **Build & Push Image**: A custom Docker image containing PostgreSQL 17 and the `pgvector` extension will be built and pushed to the private container registry.
2.  **Deploy Green**: A new set of Kubernetes manifests will be deployed to run the `pgvector`-enabled database. This new instance will have its own PVC for data isolation.
3.  **Initial Sync**: A full backup of the live v17 database will be restored to the new `pgvector` instance.
4.  **Cutover**: During a brief maintenance window, the `chronicle-service` will be scaled down, a final data sync will be performed, and the `chronicle-db` service selector will be updated to point to the new database pods. The `chronicle-service` will then be scaled back up.
5.  **Validation & Cleanup**: After verifying application functionality and confirming the `vector` extension is active, the old v17 resources will be decommissioned.

### Key Components

*   **Custom Docker Image (`chronicle-db-pgvector:17.1`)**: A new Docker image built from `postgres-chronicle-17-vector/Dockerfile`.
*   **PostgreSQL 17+vector Deployment (`chronicle-db-v17-vector`)**: A new Kubernetes deployment for the `pgvector`-enabled database.
*   **PostgreSQL 17+vector PVC (`postgres-chronicle-pvc-v17-vector`)**: A new PVC for the new database.
*   **Backup/Restore Jobs**: Kubernetes Jobs to execute `pg_dump` from the old database and `pg_restore` into the new one.

## Detailed Implementation Plan

### Phase 1: Build and Push Custom Docker Image
*   **Status**: ✅ Completed
*   **Step 1.1: Build Docker Image**
    *   **Action**: Build the custom Docker image that includes the `pgvector` extension.
    *   **Command**:
        ```bash
        docker build -t myreg.agile-corp.org:5000/chronicle-db-pgvector:17.1 -f postgres-chronicle-17-vector/Dockerfile postgres-chronicle-17-vector/
        ```
    *   **Validation**: The Docker image is built successfully locally.
*   **Step 1.2: Push Docker Image**
    *   **Action**: Push the newly built image to the private container registry.
    *   **Command**:
        ```bash
        docker push myreg.agile-corp.org:5000/chronicle-db-pgvector:17.1
        ```
    *   **Validation**: The image is available in the `myreg.agile-corp.org:5000` registry.

### Phase 2: Deploy New PostgreSQL 17-pgvector Instance
*   **Status**: ✅ Completed
*   **Step 2.1: Create v17-vector Kubernetes Manifests**
    *   **Action**: Create a new directory `postgres-chronicle-17-vector` and update the deployment manifest (`postgres-chronicle-deployment-v17.yml`) to use the new image `myreg.agile-corp.org:5000/chronicle-db-pgvector:17.1` and be labeled `app: chronicle-db-v17-vector`. Create a new service manifest for the green database.
    *   **Validation**: The new YAML files are created and reviewed.
*   **Step 2.2: Deploy the v17-vector Database**
    *   **Action**: Apply the new manifests to the cluster.
    *   **Command**:
        ```bash
        kubectl apply -f postgres-chronicle-17-vector/
        ```
    *   **Validation**: Verify the `chronicle-db-v17-vector` pod is running.
        ```bash
        kubectl get pods -n dsm -l app=chronicle-db-v17-vector
        ```

### Phase 3: Initial Data Synchronization
*   **Status**: ✅ Completed
*   **Step 3.1: Execute Initial Sync**
    *   **Action**: Run the backup job to dump data from the current `chronicle-db` (v17) and the restore job to load it into the new `chronicle-db-v17-vector` instance.
    *   **Command**:
        ```bash
        kubectl apply -f postgres-chronicle-17-vector/backup-job.yml
        kubectl wait --for=condition=complete job/backup-job -n dsm --timeout=300s
        kubectl apply -f postgres-chronicle-17-vector/restore-job.yml
        kubectl wait --for=condition=complete job/restore-job -n dsm --timeout=300s
        ```
    *   **Validation**: Connect to the `chronicle-db-v17-vector` pod and verify that the data has been restored by checking table counts.

### Phase 4: Final Sync and Cutover (Maintenance Window)
*   **Status**: ✅ Completed
*   **Step 4.1: Scale Down Chronicle Service**
    *   **Action**: Scale down the `chronicle-service` to prevent new writes.
    *   **Command**: `kubectl scale deployment chronicle-service -n dsm --replicas=0`
    *   **Validation**: `kubectl get pods -n dsm -l app=chronicle-service` returns no pods.
*   **Step 4.2: Perform Final Sync**
    *   **Action**: Re-run the backup and restore jobs.
    *   **Command**:
        ```bash
        kubectl delete job backup-job restore-job -n dsm
        kubectl apply -f postgres-chronicle-17-vector/backup-job.yml
        kubectl wait --for=condition=complete job/backup-job -n dsm --timeout=300s
        kubectl apply -f postgres-chronicle-17-vector/restore-job.yml
        kubectl wait --for=condition=complete job/restore-job -n dsm --timeout=300s
        ```
    *   **Validation**: The jobs complete successfully.
*   **Step 4.3: Switch Service Selector**
    *   **Action**: Patch the `chronicle-db` service to change its selector to `app: chronicle-db-v17-vector`.
    *   **Command**: `kubectl patch service chronicle-db -n dsm -p '{"spec":{"selector":{"app":"chronicle-db-v17-vector"}}}'`
    *   **Validation**: `kubectl describe service chronicle-db -n dsm` shows the new selector.
*   **Step 4.4: Scale Up Chronicle Service**
    *   **Action**: Scale the `chronicle-service` back up.
    *   **Command**: `kubectl scale deployment chronicle-service -n dsm --replicas=1`
    *   **Validation**: The `chronicle-service` pod starts and runs successfully. Check logs for connection errors.

### Phase 5: Cleanup
*   **Status**: ✅ Completed
*   **Step 5.1: Decommission Old Database**
    *   **Action**: After a 24-hour monitoring period, delete the old v17 resources.
    *   **Command**:
        ```bash
        kubectl delete deployment chronicle-db-v17 -n dsm
        kubectl delete pvc postgres-chronicle-pvc-v17 -n dsm
        ```
    *   **Validation**: The old deployment and PVC are no longer present.

## Testing and Validation Plan

### Test Cases

*   **Test 1: Verify Data Integrity**
    *   **Action**: After the final restore, run `COUNT(*)` queries on key tables in both the old and new databases.
    *   **Status**: ✅ Passed
    *   **Expected Result**: The row counts should match exactly.
    *   **Actual Result**: The row counts for all tables matched perfectly between the old and new databases.
*   **Test 2: Application Functionality Test**
    *   **Action**: After the cutover, perform standard operations using the `chronicle-service` API.
    *   **Status**: ✅ Passed
    *   **Expected Result**: All API calls should succeed with a `200 OK` status.
*   **Test 3: Verify pgvector Extension**
    *   **Action**: Connect to the new database and check for the `vector` extension.
    *   **Status**: ✅ Passed
    *   **Command**:
        ```bash
        kubectl exec -n dsm deployment/chronicle-db-v17-vector -- psql -U chronicle_user -d chronicle_db -c "\dx"
        ```
    *   **Actual Result**: The command executed successfully and the output confirmed the `vector` extension is installed.
        ```
                             List of installed extensions
          Name   | Version |   Schema   |                     Description                      
        ---------+---------+------------+------------------------------------------------------
         plpgsql | 1.0     | pg_catalog | PL/pgSQL procedural language
         vector  | 0.8.1   | public     | vector data type and ivfflat and hnsw access methods
        (2 rows)
        ```
*   **Test 4: Verify pgvector Functionality**
    *   **Action**: Connect to the new database and perform a basic vector operation.
    *   **Status**: ✅ Passed
    *   **Command**:
        ```bash
        kubectl exec -n dsm deployment/chronicle-db-v17-vector -- psql -U chronicle_user -d chronicle_db -c "CREATE TABLE items (id serial PRIMARY KEY, embedding vector(3)); INSERT INTO items (embedding) VALUES ('[1,2,3]'); SELECT * FROM items;"
        ```
    *   **Expected Result**: The commands should execute successfully, and the SELECT statement should return the inserted row.

## Risks & Side Effects

| Risk | Description | Mitigation |
|------|-------------|------------|
| Data Loss | Writes occurring between the final backup and the service shutdown could be lost. | The `chronicle-service` is scaled to zero before the final sync, preventing any new writes. |
| Extended Downtime | The final backup/restore process takes longer than anticipated. | The data volume is known to be small from the previous migration, allowing for a quick sync. |
| Custom Image Issue | The custom Docker image may have unforeseen issues or misconfigurations. | The image is simple, based on the official `postgres:17` image, and only adds the standard `pgvector` package. It will be tested during the "Deploy Green" phase before any production traffic is routed to it. |

## Success Criteria

*   ✅ The `chronicle-db` is running on the `pgvector`-enabled PostgreSQL 17 Docker image.
*   ✅ Data from the v17 database is fully migrated to the new v17-vector database.
*   ✅ The `chronicle-service` is connected to the new database and is fully operational.
*   ✅ The `vector` extension is installed and active in the new database.
*   ✅ The cutover process is completed in under 10 minutes.

## Related Documentation

*   [CR: Upgrade Chronicle PostgreSQL Database from v13 to v17](CR_Chronicle_DB_Upgrade_v17.md)

## Detailed Impediments and Resolutions

### Resolved Impediments

*   **Date**: 2025-10-12
*   **Description**: The `backup-job` failed due to a `pg_dump` version mismatch. The job was using a `postgres:13` image to back up a PostgreSQL 17 server.
*   **Impact**: The data synchronization was blocked.
*   **Resolution**: The `backup-job.yml` was updated to use the `postgres:17` image, ensuring the client and server versions matched.
*   **Validation**: The corrected job ran and completed successfully.

*   **Date**: 2025-10-12
*   **Description**: The `chronicle-db-v17-vector` pod was stuck in an `ImagePullBackOff` loop. The cluster was unable to pull the custom Docker image from the private registry `myreg.agile-corp.org:5000` due to an authorization failure.
*   **Impact**: The new database could not be deployed, blocking the migration.
*   **Resolution**: The deployment was patched to include a reference to the existing `agile-corp-reg-secret`, which contains the necessary credentials for the private registry. The `imagePullSecrets` field was added to the pod spec.
*   **Validation**: After patching the deployment, the pod successfully pulled the image and entered the `Running` state.
    *   **Command**: `kubectl patch deployment chronicle-db-v17-vector -n dsm --patch '{"spec": {"template": {"spec": {"imagePullSecrets": [{"name": "agile-corp-reg-secret"}]}}}}'`

## CR Status: ✅ Completed
This CR has been fully implemented, tested, and validated. All migration activities are complete.

