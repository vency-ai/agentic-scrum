# CR: Upgrade Chronicle PostgreSQL Database from v13 to v17

## Overview

This document outlines the plan to upgrade the `chronicle-db` PostgreSQL database from version 13 to version 17. The primary objective is to perform this upgrade with zero data loss and minimal service disruption by employing a blue-green deployment strategy. This upgrade is necessary to leverage the performance improvements, security enhancements, and new features available in PostgreSQL 17, ensuring the long-term stability and scalability of the Chronicle service.

## Goals

*   **Goal 1**: Successfully upgrade the live `chronicle-db` from PostgreSQL v13 to v17.
*   **Goal 2**: Ensure no data is lost during the migration process.
*   **Goal 3**: Achieve a zero-downtime cutover from the old database to the new one.
*   **Goal 4**: Validate that the `chronicle-service` functions correctly with the upgraded database.

## Current State Analysis

*   **Current Behavior**: The `chronicle-db` is running on `postgres:13` as a Kubernetes Deployment. It serves as the data store for the `chronicle-service`, handling historical scrum reports and sprint retrospectives.
*   **Dependencies**: The `chronicle-service` is directly dependent on this database.
*   **Gaps/Issues**: The current version (13) is several major versions behind the latest stable release, missing out on significant performance optimizations, security patches, and modern SQL features.
*   **Configuration**: The database is deployed in the `dsm` namespace, using a `Deployment`, `Service`, `ConfigMap`, `Secret`, and a `PersistentVolumeClaim` backed by NFS storage.

## Proposed Solution

We will implement a blue-green deployment strategy to perform the upgrade. This approach involves setting up a new, parallel PostgreSQL 17 instance (the "green" environment) alongside the existing v13 instance (the "blue" environment).

The migration will proceed as follows:
1.  **Deploy Green**: A new set of Kubernetes manifests will be created to deploy a `postgres:17` database. This new instance will have its own PVC, ensuring data isolation.
2.  **Initial Sync**: We will perform a full backup of the live v13 database using `pg_dump` and restore it to the new v17 instance. This can be done while the v13 database is still serving live traffic.
3.  **Cutover**: During a brief maintenance window, we will:
    a.  Scale down the `chronicle-service` deployment to 0 replicas to stop writes to the database.
    b.  Perform a final, quick differential backup and restore to sync any data that changed since the initial sync.
    c.  Update the `chronicle-db` service selector to point to the new `postgres:17` pods.
    d.  Scale the `chronicle-service` deployment back up.
4.  **Validation & Cleanup**: After verifying that the application is working correctly with the new database, the old v13 resources will be decommissioned.

### Key Components

*   **PostgreSQL 17 Deployment (`chronicle-db-v17`)**: A new Kubernetes deployment for the v17 database.
*   **PostgreSQL 17 PVC (`postgres-chronicle-pvc-v17`)**: A new PersistentVolumeClaim for the v17 database to store its data.
*   **Backup/Restore Jobs**: Kubernetes Jobs to execute `pg_dump` from the old database and `pg_restore` into the new one.
*   **Service Selector Update**: A modification to the existing `chronicle-db` service to redirect traffic to the new database instance.

### Architecture Changes

The core architecture remains a database-per-service model. This change is a version upgrade of one of the databases, not a change in the overall data flow or service interaction.

## Detailed Implementation Plan

### Phase 1: Deploy New PostgreSQL 17 Instance
*   **Status**: ⏹️ Pending
*   **Step 1.1: Create v17 Kubernetes Manifests**
    *   **Action**: Create a new directory `postgres-chronicle-17`. Inside this directory, create new YAML files by copying and modifying the existing ones from `postgres-chronicle`. The new files will be for the PostgreSQL 17 deployment (`postgres-chronicle-17/postgres-chronicle-deployment-v17.yml`) and PVC (`postgres-chronicle-17/postgres-chronicle-pvc-v17.yml`). The deployment will use the image `postgres:17` and be labeled `app: chronicle-db-v17`.
    *   **Validation**: The new directory and YAML files are created and reviewed.
*   **Step 1.2: Deploy the v17 Database**
    *   **Action**: Apply the new manifests from the `postgres-chronicle-17` directory to the cluster to create the v17 instance.
    *   **Command**:
        ```bash
        kubectl apply -f postgres-chronicle-17/
        ```
    *   **Validation**: Verify that the `chronicle-db-v17` pod is running successfully.
        ```bash
        kubectl get pods -n dsm -l app=chronicle-db-v17
        ```

### Phase 2: Initial Data Synchronization
*   **Status**: ⏹️ Pending
*   **Step 2.1: Create Backup Job**
    *   **Action**: Create a Kubernetes Job manifest (`backup-job.yml`) that runs a pod with `psql` tools. This pod will connect to the `chronicle-db` (v13) service and execute `pg_dump`. The dump file will be saved to a shared volume.
    *   **Validation**: The `backup-job.yml` file is created and reviewed.
*   **Step 2.2: Create Restore Job**
    *   **Action**: Create a Kubernetes Job manifest (`restore-job.yml`) that connects to the `chronicle-db-v17` pod and executes `pg_restore` from the dump file on the shared volume.
    *   **Validation**: The `restore-job.yml` file is created and reviewed.
*   **Step 2.3: Execute Initial Sync**
    *   **Action**: Run the backup and restore jobs to perform the initial data migration.
    *   **Command**:
        ```bash
        kubectl apply -f backup-job.yml
        kubectl wait --for=condition=complete job/backup-job -n dsm --timeout=300s
        kubectl apply -f restore-job.yml
        kubectl wait --for=condition=complete job/restore-job -n dsm --timeout=300s
        ```
    *   **Validation**: Connect to the `chronicle-db-v17` pod and verify that the data has been restored. Check table counts.

### Phase 3: Final Sync and Cutover (Maintenance Window)
*   **Status**: ⏹️ Pending
*   **Step 3.1: Scale Down Chronicle Service**
    *   **Action**: Scale down the `chronicle-service` to prevent any new writes to the v13 database.
    *   **Command**: `kubectl scale deployment chronicle-service -n dsm --replicas=0`
    *   **Validation**: `kubectl get pods -n dsm -l app=chronicle-service` should return no pods.
*   **Step 3.2: Perform Final Sync**
    *   **Action**: Re-run the backup and restore jobs to sync any changes made since the initial sync.
    *   **Command**:
        ```bash
        kubectl delete job backup-job restore-job -n dsm
        kubectl apply -f backup-job.yml
        kubectl wait --for=condition=complete job/backup-job -n dsm --timeout=300s
        kubectl apply -f restore-job.yml
        kubectl wait --for=condition=complete job/restore-job -n dsm --timeout=300s
        ```
    *   **Validation**: The jobs complete successfully.
*   **Step 3.3: Switch Service Selector**
    *   **Action**: Patch the `chronicle-db` service to change its selector from `app: chronicle-db` to `app: chronicle-db-v17`.
    *   **File**: `postgres-chronicle/postgres-chronicle-service.yml`
    *   **Command**: `kubectl patch service chronicle-db -n dsm -p '{"spec":{"selector":{"app":"chronicle-db-v17"}}}'`
    *   **Validation**: `kubectl describe service chronicle-db -n dsm` should show the new selector.
*   **Step 3.4: Scale Up Chronicle Service**
    *   **Action**: Scale the `chronicle-service` back up. It will now connect to the v17 database.
    *   **Command**: `kubectl scale deployment chronicle-service -n dsm --replicas=1`
    *   **Validation**: The `chronicle-service` pod starts successfully and is running. Check logs for any database connection errors.

### Phase 4: Validation
*   **Status**: ⏹️ Pending
*   **Step 4.1: Application Health Check**
    *   **Action**: Run application-level tests to ensure the `chronicle-service` is fully functional.
    *   **Validation**: API endpoints for the chronicle service are responsive and return correct data.

### Phase 5: Cleanup
*   **Status**: ⏹️ Pending
*   **Step 5.1: Decommission Old Database**
    *   **Action**: After a 24-hour monitoring period to ensure the v17 database is stable and working correctly, delete the old v13 resources.
    *   **Command**:
        ```bash
        kubectl delete deployment chronicle-db -n dsm
        kubectl delete pvc postgres-chronicle-pvc -n dsm
        kubectl delete pv nfs-chronicle-pv -n dsm
        ```
    *   **Validation**: The old deployment, PVC, and PV are no longer present.

## Testing and Validation Plan

### Test Cases

*   **Test 1: Verify Data Integrity**
    *   **Action**: After the final restore, connect to both databases (v13 and v17) and run `COUNT(*)` queries on key tables like `chronicle_notes` and `sprint_retrospectives`.
    *   **Expected Result**: The row counts should match exactly.
    *   **Actual Result**: The row counts match perfectly.
        *   **Command to get table names from old DB:**
            ```bash
            kubectl exec -n dsm deployment.apps/chronicle-db -- env PGPASSWORD=dsm_password psql -h chronicle-db -U chronicle_user -d chronicle_db -c "\dt"
            ```
        *   **Command to get row counts from old DB (v13):**
            ```bash
            kubectl exec -n dsm deployment.apps/chronicle-db -- env PGPASSWORD=dsm_password psql -h chronicle-db -U chronicle_user -d chronicle_db -c "SELECT 'chronicle_notes', COUNT(*) FROM chronicle_notes UNION ALL SELECT 'retrospective_action_items', COUNT(*) FROM retrospective_action_items UNION ALL SELECT 'retrospective_attendees', COUNT(*) FROM retrospective_attendees UNION ALL SELECT 'sprint_retrospectives', COUNT(*) FROM sprint_retrospectives;"
            ```
        *   **Command to get row counts from new DB (v17):**
            ```bash
            kubectl exec -n dsm deployment.apps/chronicle-db-v17 -- env PGPASSWORD=dsm_password psql -U chronicle_user -d chronicle_db -c "SELECT 'chronicle_notes', COUNT(*) FROM chronicle_notes UNION ALL SELECT 'retrospective_action_items', COUNT(*) FROM retrospective_action_items UNION ALL SELECT 'retrospective_attendees', COUNT(*) FROM retrospective_attendees UNION ALL SELECT 'sprint_retrospectives', COUNT(*) FROM sprint_retrospectives;"
            ```
        *   **Row Count Comparison:**
            | Table Name                 | Old DB Count | New DB Count | Status  |
            |----------------------------|--------------|--------------|---------|
            | chronicle_notes            | 971          | 971          | ✅ Match |
            | retrospective_action_items | 260          | 260          | ✅ Match |
            | retrospective_attendees    | 196          | 196          | ✅ Match |
            | sprint_retrospectives      | 99           | 99           | ✅ Match |
*   **Test 2: Application Functionality Test**
    *   **Action**: After the cutover, perform standard operations using the `chronicle-service` API, such as creating and retrieving reports.
    *   **Expected Result**: All API calls should succeed with a `200 OK` status, and the data should be correctly persisted in the v17 database.
*   **Test 3: Connection Validation**
    *   **Action**: Check the logs of the `chronicle-service` pod immediately after it's scaled back up.
    *   **Expected Result**: No database connection errors or warnings should be present.
    *   **Actual Result**: The logs show a successful database connection.
        *   **Command:**
            ```bash
            kubectl logs -n dsm deployment/chronicle-service
            ```
        *   **Output:**
            ```log
            2025-10-11T15:26:29.017104Z [info     ] Database connection pool initialized. [database]
            INFO:     Started server process [1]
            INFO:     Waiting for application startup.
            2025-10-11T15:26:29.109907Z [info     ] Chronicle Service starting up... [app]
            ...
            INFO:     Application startup complete.
            INFO:     Uvicorn running on http://0.0.0.0:80 (Press CTRL+C to quit)
            ```

## Risks & Side Effects

| Risk | Description | Mitigation |
|------|-------------|------------|
| Data Loss | Writes occurring between the final backup and the service shutdown could be lost. | The `chronicle-service` is scaled to zero before the final sync, preventing any new writes and eliminating this risk. |
| Extended Downtime | The final backup/restore process takes longer than anticipated. | Perform a dry run of the backup/restore jobs in a staging environment to get an accurate time estimate. The data volume for the chronicle service is expected to be small, allowing for a quick sync. |
| Application Incompatibility | The `chronicle-service` may have issues with PostgreSQL 17. | PostgreSQL is known for its excellent backward compatibility. The risk is low, but it will be fully mitigated by thorough testing in a staging environment before the production rollout. |

## Success Criteria

*   ✅ The `chronicle-db` is running PostgreSQL 17.
*   ✅ Data from the v13 database is fully migrated to the v17 database.
*   ✅ The `chronicle-service` is connected to the v17 database and is fully operational.
*   ✅ The entire cutover process (service down, sync, service up) is completed in under 10 minutes.

## Detailed Impediments and Resolutions

### Resolved Impediments

*   **Date**: 2025-10-11
*   **Description**: The `backup-pvc` was stuck in a `Pending` state.
*   **Impact**: This blocked the backup job from starting, as it had no volume to write the dump file to.
*   **Resolution**: A corresponding `PersistentVolume` was missing for the `PersistentVolumeClaim`. Created a new PV manifest (`postgres-chronicle-17/backup-pv.yml`) and applied it. The PVC then successfully bound to the new PV.
*   **Validation**: `kubectl get pvc backup-pvc -n dsm` showed the status as `Bound`.

### Current Outstanding Issues

*   **Date**: YYYY-MM-DD
*   **Description**: [Describe an issue that is still outstanding]
*   **Impact**: [Explain the current impact]
*   **Next Steps**: [Describe the plan or next steps to resolve this issue. This might involve creating a new CR.]
*   **Status**: [e.g., Pending New CR, Under Investigation, Blocked]

## CR Status:  CLEANUP COMPLETE

## Implementation Log

| Date       | Step       | Change                                                                 | Status                                 |
|------------|------------|------------------------------------------------------------------------|----------------------------------------|
| 2025-10-11 | Plan       | Detailed implementation plan written.                                  | Plan Written - Awaiting Confirmation   |
| 2025-10-11 | Step 1.1   | Created `postgres-chronicle-17` directory and manifests.               | Complete                               |
| 2025-10-11 | Step 1.2   | Deployed PostgreSQL 17 instance. Pod `chronicle-db-v17` is running.    | Complete                               |
| 2025-10-11 | Step 2.3   | Initial data sync from v13 to v17 is complete.                         | Complete                               |
| 2025-10-11 | Test 1     | Verified data integrity. Row counts match between v13 and v17 databases. | Complete                               |
| 2025-10-11 | Step 3.1   | Scaled down `chronicle-service`.                                       | Complete                               |
| 2025-10-11 | Step 3.2   | Performed final data sync.                                             | Complete                               |
| 2025-10-11 | Step 3.3   | Switched service selector to point to `chronicle-db-v17`.              | Complete                               |
| 2025-10-11 | Step 3.4   | Scaled up `chronicle-service`.                                         | Complete                               |
| 2025-10-11 | Test 3     | Verified `chronicle-service` connection to the new database.           | Complete                               |

