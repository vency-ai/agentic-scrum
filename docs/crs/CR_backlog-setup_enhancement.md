# CR: Backlog Setup Job Enhancement

## Overview

This Change Request addresses two key areas for improvement in the `backlog-setup` Kubernetes Job: standardizing its logging configuration to use `structlog` for consistency with other DSM services, and externalizing hardcoded `TEST_PROJECT_ID` and `TEST_SPRINT_ID` values into environment variables for greater flexibility and reusability. Currently, the `backlog-setup` job uses Python's default `logging` module, which deviates from the `structlog` standard adopted by core microservices. Additionally, critical identifiers are hardcoded, limiting the job's adaptability to different project and sprint contexts without code modification.

This CR proposes modifying the `app.py` and `utils.py` scripts within the `backlog-setup` job to integrate `structlog` and retrieve `TEST_PROJECT_ID` and `TEST_SPRINT_ID` from environment variables. The Kubernetes Job manifest (`backlog-setup-job.yml`) will be updated to pass these environment variables. These changes will enhance observability, improve configuration management, and align the `backlog-setup` job with the overall DSM system's best practices.

## Goals

*   **Standardize Logging**: Align `backlog-setup` job's logging with `structlog` for consistent, structured logs across the DSM ecosystem.
*   **Externalize Configuration**: Make `TEST_PROJECT_ID` and `TEST_SPRINT_ID` configurable via environment variables, removing hardcoded values.
*   **Improve Flexibility**: Enable the `backlog-setup` job to be easily adapted for different projects and sprints without code changes.
*   **Enhance Observability**: Provide richer, machine-readable logs for easier debugging and monitoring.
*   **Align with Best Practices**: Adhere to established configuration and logging patterns within the DSM microservices.

## Current State Analysis

*   **Standard Logging**: The `backlog-setup/src/app.py` and `utils.py` currently use Python's built-in `logging` module. This results in unstructured logs that are less amenable to automated parsing and analysis compared to `structlog`.
*   **Hardcoded Identifiers**: The `TEST_PROJECT_ID` ("TEST-001") and `TEST_SPRINT_ID` ("SPRINT-001") are hardcoded within `backlog-setup/src/app.py`. This means that to run the setup job for a different project or sprint, the Python script itself needs to be modified and the ConfigMap rebuilt, which is inefficient and error-prone.
*   **Operational Inflexibility**: The hardcoded values limit the job's utility to a single, predefined test scenario, making it difficult to use for other development or testing environments.

## Proposed Solution

The solution involves modifying the Python scripts to use `structlog` and read configuration from environment variables, then updating the Kubernetes Job manifest to supply these variables.

### 1. Python Code Modifications (`app.py`, `utils.py`)

*   **`structlog` Integration**: Replace `logging` calls with `structlog` in both `app.py` and `utils.py`. Configure `structlog` for JSON output to match other services.
*   **Environment Variable Reading**: Modify `app.py` to read `PROJECT_ID` and `SPRINT_ID` from environment variables using `os.getenv()` instead of hardcoded constants. Provide sensible defaults if the environment variables are not set (e.g., for local development).

### 2. Kubernetes Job Manifest Update (`backlog-setup-job.yml`)

*   **Environment Variables**: Add `env` section to the job's container specification to pass `PROJECT_ID` and `SPRINT_ID` to the pod.
*   **ConfigMap Update**: The ConfigMap (`backlog-setup-scripts`) will need to be recreated with the updated `app.py` and `utils.py` files.

## Detailed Implementation Plan

### Phase 1: Code Modifications

*   **Step 1.1: Update `backlog-setup/src/app.py`**
    *   **Action**: Modify `app.py` to import `structlog`, configure it, replace `logging` calls, and read `PROJECT_ID` and `SPRINT_ID` from environment variables.
    *   **Status**: Not Started

*   **Step 1.2: Update `backlog-setup/src/utils.py`**
    *   **Action**: Modify `utils.py` to import `structlog` and replace `logging` calls.
    *   **Status**: Not Started

*   **Step 1.3: Update `backlog-setup/src/requirements.txt`**
    *   **Action**: Add `structlog` to `requirements.txt`.
    *   **Status**: Not Started

### Phase 2: Kubernetes Manifest and ConfigMap Update

*   **Step 2.1: Recreate `backlog-setup-scripts` ConfigMap**
    *   **Action**: Delete the existing ConfigMap and recreate it with the updated `app.py`, `utils.py`, and `requirements.txt`.
    *   **Command**: 
        ```bash
        kubectl delete configmap backlog-setup-scripts -n dsm || true
        kubectl -n dsm create configmap backlog-setup-scripts \
          --from-file=setups/backlog-setup/src/app.py \
          --from-file=setups/backlog-setup/src/utils.py \
          --from-file=setups/backlog-setup/src/requirements.txt
        ```
    *   **Status**: Not Started

*   **Step 2.2: Update `setups/backlog-setup/k8s/backlog-setup-job.yml`**
    *   **Action**: Add `env` variables for `PROJECT_ID` and `SPRINT_ID` to the job definition. Example snippet:
        ```yaml
        spec:
          template:
            spec:
              containers:
              - name: backlog-setup
                env:
                - name: PROJECT_ID
                  value: "TEST-001" # Or a dynamic value from another source
                - name: SPRINT_ID
                  value: "SPRINT-001" # Or a dynamic value
        ```
    *   **Status**: Not Started

*   **Step 2.3: Apply and Verify Job Deployment**
    *   **Action**: Apply the updated job manifest and monitor its execution and logs to ensure `structlog` is active and environment variables are correctly used.
    *   **Command**: 
        ```bash
        kubectl apply -f setups/backlog-setup/k8s/backlog-setup-job.yml
        kubectl get jobs -n dsm backlog-setup-job
        kubectl logs -f -n dsm -l job-name=backlog-setup-job
        ```
    *   **Verification**: Check job logs for structured output and confirmation that the correct project/sprint IDs were used.
    *   **Status**: Not Started

### Phase 3: Testing and Validation

*   **Step 3.1: Verify Job Completion and Logs**
    *   **Action**: Confirm the job completes successfully and inspect logs for `structlog` formatted output.
    *   **Verification**: 
        ```bash
        kubectl get jobs -n dsm setup-backlog
        kubectl logs -n dsm -l job-name=setup-backlog | grep '"event":'
        ```
    *   **Status**: Complete

*   **Step 3.2: Verify Data in Backlog Service**
    *   **Action**: Use `curl` via `testapp-pod` to query the Backlog Service and confirm that tasks for the configured `PROJECT_ID` and `SPRINT_ID` have been created.
    *   **Verification**: 
        ```bash
        kubectl exec -it testapp-pod -n dsm -- curl http://backlog-service.dsm.svc.cluster.local/backlogs/TEST-001/summary | jq
        kubectl exec -it testapp-pod -n dsm -- curl http://backlog-service.dsm.svc.cluster.local/backlogs/TEST-001 | jq
        ```
    *   **Status**: Complete

## Testing and Verification

This section details the specific steps taken to verify the successful implementation of the changes outlined in this Change Request, including the commands executed and their expected outputs.

### 1. Verify `backlog-setup/src/app.py` Modifications

*   **Objective**: Confirm `app.py` uses `structlog` and reads `PROJECT_ID`/`SPRINT_ID` from environment variables.
*   **Method**: Manual inspection of the file after modification.
*   **Expected Change**:
    *   `import logging` removed, `import structlog` added.
    *   `structlog.configure(...)` and `logger = structlog.get_logger()` added.
    *   `TEST_PROJECT_ID = os.getenv("PROJECT_ID", "TEST-001")`
    *   `TEST_SPRINT_ID = os.getenv("SPRINT_ID", "SPRINT-001")`
    *   All `logging.info/warning/error` calls replaced with `logger.info/warning/error` with structured key-value pairs.

### 2. Verify `backlog-setup/src/utils.py` Modifications

*   **Objective**: Confirm `utils.py` uses `structlog`.
*   **Method**: Manual inspection of the file after modification.
*   **Expected Change**:
    *   `import structlog` added (if not already present).
    *   `structlog.configure(...)` and `logger = structlog.get_logger(__name__)` added (if not already present).
    *   All `logger.info/error` calls replaced with `logger.info/error` with structured key-value pairs.

### 3. Verify `backlog-setup/src/requirements.txt` Update

*   **Objective**: Confirm `structlog` is added to the dependencies.
*   **Method**: Read the file content.
*   **Command**:
    ```bash
    cat setups/backlog-setup/src/requirements.txt
    ```
*   **Expected Output**:
    ```
    psycopg2-binary
    httpx
    structlog
    ```

### 4. Verify `backlog-setup-scripts` ConfigMap Recreation

*   **Objective**: Ensure the ConfigMap was successfully deleted and recreated with the updated script files.
*   **Method**: Check `kubectl` command output.
*   **Commands & Expected Output**:
    1.  **Delete Command**:
        ```bash
        kubectl delete configmap backlog-setup-scripts -n dsm || true
        ```
        *   **Expected Output**: `job.batch "setup-backlog" deleted` (if it existed) or no error if it didn't.
    2.  **Create Command**:
        ```bash
        kubectl -n dsm create configmap backlog-setup-scripts --from-file=setups/backlog-setup/src/app.py --from-file=setups/backlog-setup/src/utils.py --from-file=setups/backlog-setup/src/requirements.txt
        ```
        *   **Expected Output**: `configmap/backlog-setup-scripts created`

### 5. Verify `setups/backlog-setup/k8s/backlog-setup-job.yml` Update

*   **Objective**: Confirm environment variables `PROJECT_ID` and `SPRINT_ID` are added to the job manifest.
*   **Method**: Manual inspection of the file after modification.
*   **Expected Change**: The `env` section within the `setup-backlog` container spec should include:
    ```yaml
            - name: PROJECT_ID
              value: "TEST-001"
            - name: SPRINT_ID
              value: "SPRINT-001"
    ```

### 6. Verify Job Deployment and Logs

*   **Objective**: Confirm the job runs successfully, uses `structlog`, and correctly applies environment variables.
*   **Method**: Apply the job, check its status, and inspect its logs.
*   **Commands & Expected Output**:
    1.  **Delete (if exists) and Apply Job**:
        ```bash
        kubectl delete job setup-backlog -n dsm || true
        kubectl apply -f setups/backlog-setup/k8s/backlog-setup-job.yml
        ```
        *   **Expected Output**: `job.batch "setup-backlog" deleted` (if existed), `job.batch/setup-backlog created`
    2.  **Check Job Status**:
        ```bash
        kubectl get jobs -n dsm setup-backlog
        ```
        *   **Expected Output**: `NAME            STATUS     COMPLETIONS   DURATION   AGE` and `setup-backlog   Complete   1/1           <duration>   <age>`
    3.  **Stream Job Logs (for structlog output)**:
        ```bash
        kubectl logs -f -n dsm -l job-name=setup-backlog | grep '"event":'
        ```
        *   **Expected Output**: Structured log lines, including:
            ```json
            {"event": "Starting backlog setup job"}
            {"db_host": "backlog-db", "db_port": "5432", "db_name": "backlog_db", "event": "Connecting to backlog database"}
            {"event": "Backlog database connection successful."}
            {"event": "Required backlog database tables verified successfully"}
            {"project_id": "TEST-001", "event": "Project found via API"}
            {"count": 3, "project_id": "TEST-001", "event": "Retrieved team members for project"}
            {"tasks_count": 8, "stories_count": 4, "story_task_mappings_count": 8, "event": "Created backlog items"}
            {"items_created": 8, "project_id": "TEST-001", "event": "Backlog setup completed successfully"}
            {"event": "Backlog setup job completed successfully"}
            ```

### 7. Verify Data in Backlog Service

*   **Objective**: Confirm that tasks for `TEST-001` have been created in the Backlog Service.
*   **Method**: Query the Backlog Service via `testapp-pod`.
*   **Commands & Expected Output**:
    1.  **Get Backlog Summary**:
        ```bash
        kubectl exec -it testapp-pod -n dsm -- curl http://backlog-service.dsm.svc.cluster.local/backlogs/TEST-001/summary | jq
        ```
        *   **Expected Output**: JSON output similar to:
            ```json
            {
              "project_id": "TEST-001",
              "total_tasks": 18,
              "status_counts": {
                "NotStarted": 8,
                "assigned_to_sprint": 10
              }
            }
            ```
    2.  **Get All Backlog Tasks**:
        ```bash
        kubectl exec -it testapp-pod -n dsm -- curl http://backlog-service.dsm.svc.cluster.local/backlogs/TEST-001 | jq
        ```
        *   **Expected Output**: A JSON array of tasks, including the newly created `TSK-XXX` tasks for `TEST-001`.

## Implementation Log

| Date | Step | Change | Status |
|---|---|---|---|
| 2025-08-22 | Plan | Initial Draft of CR | In Progress |
| 2025-08-22 | Step 1.1 | Starting: Update `backlog-setup/src/app.py` to use `structlog` and environment variables. | Complete |
| 2025-08-22 | Step 1.2 | Starting: Update `backlog-setup/src/utils.py` to use `structlog`. | Complete |
| 2025-08-22 | Step 1.3 | Starting: Update `backlog-setup/src/requirements.txt` to add `structlog`. | Complete |
| 2025-08-22 | Step 2.1 | Starting: Recreate `backlog-setup-scripts` ConfigMap with updated scripts. | Complete |
| 2025-08-22 | Step 2.2 | Starting: Update `setups/backlog-setup/k8s/backlog-setup-job.yml` to add environment variables. | Complete |
| 2025-08-22 | Step 2.3 | Starting: Apply and verify job deployment. | Failed (Immutable field error) |
| 2025-08-22 | Step 2.3 (Revised) | Starting: Delete existing job, then apply and verify job deployment. | Complete |
| 2025-08-22 | Step 3.1 | Starting: Verify job completion and logs for `structlog` formatted output. | Complete |
| 2025-08-22 | Step 3.2 | Starting: Verify data in Backlog Service using `curl` via `testapp-pod`. | Complete |

## CR Status: Completed

## Risks & Side Effects

*   **Logging Format Change**: Existing log parsing tools or scripts might need updates to handle the new `structlog` JSON format.
*   **Environment Variable Misconfiguration**: Incorrectly set environment variables in the Kubernetes Job manifest could lead to the job failing or initializing data for the wrong project/sprint.
*   **Dependency on `structlog`**: Introduces a new dependency in `requirements.txt` for `backlog-setup`.

## Conclusion

By implementing `structlog` and externalizing `TEST_PROJECT_ID` and `TEST_SPRINT_ID` into environment variables, the `backlog-setup` job will become more robust, observable, and flexible. These changes align it with the architectural best practices established for other DSM microservices, improving overall system consistency and operational efficiency.

## CR Status: Completed
