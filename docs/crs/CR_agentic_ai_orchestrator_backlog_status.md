# CR: Project Orchestration - Backlog Status Consumption

## Overview

This Change Request outlines the necessary updates to the `project-orchestrator` service to correctly consume and display the `unassigned_for_sprint_count` provided by the `backlog-service`. Currently, the orchestrator's `/orchestrate/project/{project_id}/status` endpoint reports `"unassigned": 0` and `"total_tasks": 0` in its `backlog_status` field, even when the `backlog-service` accurately reports unassigned tasks. This discrepancy prevents the `project-orchestrator` from making informed decisions based on the true availability of tasks for sprint planning.

This CR is a direct follow-up to the `CR_backlog-service_reporting_fix.md`, which successfully implemented the accurate reporting of unassigned tasks in the `backlog-service`.

## Goals

*   **Accurate Backlog Status in Orchestrator**: Ensure the `project-orchestrator` accurately reflects the `unassigned_for_sprint_count` from the `backlog-service` in its `/orchestrate/project/{project_id}/status` endpoint.
*   **Improved Orchestration Decisions**: Enable the `project-orchestrator` to make intelligent decisions about sprint planning and task assignment based on correct and up-to-date backlog information.
*   **Maintain API Contracts**: Implement changes within the `project-orchestrator` without altering its existing API endpoints, only correcting the data returned.
*   **Seamless Integration**: Ensure the `project-orchestrator` seamlessly integrates with the updated `backlog-service` API.

## Current State Analysis

*   **Current Behavior**: The `project-orchestrator` calls the `backlog-service`'s `/backlogs/{project_id}/summary` endpoint. However, it does not correctly parse or utilize the `unassigned_for_sprint_count` field, leading to an inaccurate `backlog_status` in its own `/orchestrate/project/{project_id}/status` response.
*   **Dependencies**: The `project-orchestrator` is dependent on the `backlog-service` for accurate backlog information. The `backlog-service` has already been updated to provide the `unassigned_for_sprint_count` (as per `CR_backlog-service_reporting_fix.md`).
*   **Gaps/Issues**:
    - The `Project Analyzer` component within the `project-orchestrator` needs to be updated to correctly extract and process the `unassigned_for_sprint_count` from the `backlog-service`'s response.
    - The `backlog_status` object in the `orchestrator`'s `/status` endpoint needs to be populated with this new, accurate data.

## Current Implementation Status

The `project-orchestrator` service is largely implemented and deployed, but with the identified bug in consuming backlog status from the `backlog-service`.

### Completed Components
*   **Service Structure**: Complete directory structure with `src/`, `k8s/`, `tests/`
*   **FastAPI Application**: Implemented with health check endpoints (`/health`, `/health/ready`) and structured logging
*   **Service Clients**: Async HTTP communication with Project, Backlog, Sprint, and Chronicle services
*   **Project Analyzer**: Gathers and analyzes project state information from dependent services (needs update)
*   **Decision Engine**: Intelligent business logic for orchestration decisions
*   **CronJob Templates**: Jinja2 templates for dynamic CronJob generation
*   **Kubernetes Client**: Interacts with Kubernetes API for managing CronJobs
*   **CronJob Generator**: Generates and deploys unique CronJob manifests

### Deployed Infrastructure
*   **Docker Image**: Built and pushed to private registry (`myreg.agile-corp.org:5000/project-orchestrator:1.0.0`)
*   **Kubernetes Deployment**: Service successfully deployed with proper RBAC permissions
*   **Health Checks**: Validated endpoints reporting `ok` status with `ready` dependencies
*   **Unit Tests**: All 11 tests pass successfully (new tests will be added for this CR)

### Testing Status
*   **Health Check Endpoints**: Validated and operational
*   **Core Orchestration Workflow**: Functional but requires specific preconditions (no active sprint)
*   **Integration Tests**: In progress with preconditions being established

## Proposed Solution

### Architecture Alignment

The proposed solution will align with established DSM patterns:
- **FastAPI Framework**: Consistent with all existing services.
- **Service Communication**: The `project-orchestrator` will continue to use its existing `ServiceClient` to communicate with the `backlog-service`.
- **Containerization Strategy**: The fix will be deployed as an update to the existing Docker image.

### Key Components

*   **Project Analyzer**: This component within the `project-orchestrator` will be modified to correctly parse the response from the `backlog-service`'s `/backlogs/{project_id}/summary` endpoint and extract the `unassigned_for_sprint_count`.
*   **Orchestration Status Endpoint**: The logic for generating the response of the `/orchestrate/project/{project_id}/status` endpoint will be updated to include the accurate `unassigned_for_sprint_count` in the `backlog_status` field.

### Integration Points

1.  **Backlog Service**: The `project-orchestrator` will consume the `unassigned_for_sprint_count` from the `backlog-service`'s `/backlogs/{project_id}/summary` endpoint.
2.  **Internal State**: The `Project Analyzer` will update the internal representation of the project's backlog status to include this new metric.
3.  **API Response**: The `/orchestrate/project/{project_id}/status` endpoint will reflect the updated backlog status.

## API Changes

No new API endpoints or changes to existing API contracts are proposed. The fix will only correct the data returned by the existing `/orchestrate/project/{project_id}/status` endpoint:

*   **`GET /orchestrate/project/{project_id}/status`**
    *   **Purpose**: Will now accurately report `unassigned` and `total_tasks` in `backlog_status`, incorporating the `unassigned_for_sprint_count` from the `backlog-service`.
    *   **Updated Response Structure (Example)**:
        ```json
        {
            "project_id": "TEST-001",
            "last_analysis": "2025-01-20T10:30:00Z",
            "current_sprint": null,
            "sprint_status": "no active sprint",
            "backlog_status": {
                "total_tasks": 10,  // Example: reflects actual total tasks
                "unassigned": 10,   // Example: reflects unassigned_for_sprint_count
                "in_progress": 0,
                "completed": 0
            },
            "cronjobs": []
        }
        ```

## Implementation Plan

### Phase 1: Code Review
*   **Step 1.1: Review Project Orchestration Codebase**
    *   **Action**: Examine the `project-orchestrator`'s `src/` directory, focusing on the `Project Analyzer` component and the implementation of the `/orchestrate/project/{project_id}/status` endpoint.
    *   **Status**: Not Started

*   **Step 1.2: Understand Backlog Service Client Usage**
    *   **Action**: Identify where the `project-orchestrator` calls the `backlog-service`'s `/backlogs/{project_id}/summary` endpoint and how its response is currently processed.
    *   **Status**: Not Started

### Phase 2: Code Modification
*   **Step 2.1: Update Project Analyzer to Consume `unassigned_for_sprint_count`**
    *   **Action**: Modify the `Project Analyzer` to correctly extract the `unassigned_for_sprint_count` from the `backlog-service`'s `/backlogs/{project_id}/summary` response.
    *   **Status**: Not Started

*   **Step 2.2: Integrate `unassigned_for_sprint_count` into Orchestrator's Internal State**
    *   **Action**: Update the internal data structure that holds project backlog status within the `project-orchestrator` to store the `unassigned_for_sprint_count`.
    *   **Status**: Not Started

*   **Step 2.3: Modify `/orchestrate/project/{project_id}/status` Endpoint Response**
    *   **Action**: Adjust the logic that constructs the `backlog_status` portion of the `/orchestrate/project/{project_id}/status` endpoint's response to use the newly consumed `unassigned_for_sprint_count` for the `unassigned` field and potentially `total_tasks` if applicable.
    *   **Status**: Not Started

### Phase 3: Testing and Validation
*   **Step 3.1: Unit Testing**
    *   **Action**: Create or update unit tests for the `Project Analyzer` to ensure it correctly parses the `backlog-service` response and extracts the `unassigned_for_sprint_count`.
    *   **Status**: Not Started

*   **Step 3.2: Integration Testing**
    *   **Action**: Deploy the updated `project-orchestrator` to a test environment.
    *   **Verification**:
        ```bash
        kubectl exec -it testapp-pod -n dsm -- curl http://project-orchestrator.dsm.svc.cluster.local/orchestrate/project/TEST-001/status | jq
        ```
        *   Expected: The `backlog_status.unassigned` field in the response should now accurately reflect the `unassigned_for_sprint_count` from the `backlog-service`.
    *   **Status**: Not Started

*   **Step 3.3: End-to-End Validation (Orchestration Decisions)**
    *   **Action**: If applicable, run a full orchestration workflow (e.g., `POST /orchestrate/project/{project_id}`) to ensure that the `Decision Engine` correctly utilizes the updated backlog status for making sprint planning and task assignment decisions.
    *   **Status**: Not Started

### Phase 4: Deployment
*   **Step 4.1: Build and Push New Docker Image**
    *   **Action**: Build a new Docker image for the `project-orchestrator` with the implemented fixes and push it to the private registry with an incremented version tag (e.g., `1.0.1`).
    *   **Status**: Not Started

*   **Step 4.2: Apply Updated Kubernetes Deployment**
    *   **Action**: Apply the updated `project-orchestrator` deployment manifest, referencing the new Docker image tag.
    *   **Status**: Not Started

## Testing and Validation Plan

### Test Cases

| Test | Command | Expected Result |
|------|---------|-----------------|
| Orchestrator Status - Backlog | `curl http://project-orchestrator/orchestrate/project/TEST-001/status` | `backlog_status.unassigned` accurately reflects `unassigned_for_sprint_count` |
| Orchestration Decision Logic | `curl -X POST http://project-orchestrator/orchestrate/project/TEST-001` | Orchestration decisions (e.g., `create_new_sprint`) are based on accurate unassigned task counts |

### Testing Details

*   Focus on verifying that the `project-orchestrator` correctly parses and uses the `unassigned_for_sprint_count` from the `backlog-service`.
*   Ensure that the `backlog_status` in the orchestrator's `/status` endpoint is consistent with the `backlog-service`'s reporting.

## Implementation Log

| Date       | Step       | Change                                                                 | Status                                 |
|------------|------------|------------------------------------------------------------------------|----------------------------------------|
| 2025-08-25 | Plan       | Initial Draft of CR for Project Orchestration - Backlog Status Consumption | In Progress                            |

## Risks & Side Effects

*   **Parsing Errors**: Incorrectly parsing the `backlog-service` response could lead to new errors or misinterpretations.
*   **Decision Logic Impact**: Changes to how backlog status is consumed could unintentionally alter orchestration decisions.

## Success Criteria

*   ✅ `project-orchestrator`'s `/orchestrate/project/{project_id}/status` endpoint accurately reports `unassigned` tasks based on `unassigned_for_sprint_count`.
*   ✅ Orchestration decisions made by the `project-orchestrator` are based on correct backlog task availability.
*   ✅ New Docker image builds and deploys successfully.

## Final System State

*   **Accurate Orchestrator Backlog View**: The `project-orchestrator` provides a true representation of unassigned tasks.
*   **Intelligent Decision-Making**: Orchestration workflows are driven by accurate and up-to-date backlog information.

## Related Documentation

*   [DSM Architecture Overview](DSM_Architecture_Overview.md)
*   [DSM Architecture Decision Records](DSM_Architecture_Decision_Records.md)
*   [DSM Service Specifications](DSM_Service_Specifications.md)
*   [DSM Deployment & Operations Guide](DSM_Deployment_Operations.md)
*   [DSM Kubernetes Jobs Documentation](DSM_Kubernetes_Jobs.md)
*   [CR: Backlog Service Reporting Fix](CR_backlog-service_reporting_fix.md)

## CR Status: Implemented - Awaiting Final Review

### Implementation Log

| Date       | Step       | Change                                                                 | Status                                 |
|------------|------------|------------------------------------------------------------------------|----------------------------------------|
| 2025-08-25 | Plan       | Initial Draft of CR for Project Orchestration - Backlog Status Consumption | Complete                               |
| 2025-08-25 | Step 2.1   | Modified `project_analyzer.py` to consume `unassigned_for_sprint_count`. | Complete                               |
| 2025-08-25 | Step 2.3   | Modified `app.py` to update `backlog_status` in `/orchestrate/project/{project_id}/status` endpoint. | Complete                               |
| 2025-08-25 | Step 4.1   | Built and pushed Docker image `myreg.agile-corp.org:5000/project-orchestrator:1.0.4`. | Complete                               |
| 2025-08-25 | Step 4.2   | Applied updated Kubernetes deployment for `project-orchestrator` (image `1.0.4`). | Complete                               |

### Testing Details

*   **Date**: 2025-08-25
*   **Test**: `kubectl exec -it testapp-pod -n dsm -- curl http://project-orchestrator.dsm.svc.cluster.local/orchestrate/project/test-001/status | jq`
*   **Result**: The `project-orchestrator`'s status endpoint now correctly reports:
    ```json
    {
      "project_id": "test-001",
      "last_analysis": "2025-08-25T17:46:54.910396Z",
      "current_sprint": null,
      "sprint_status": "no active sprint",
      "backlog_status": {
        "total_tasks": 10,
        "unassigned": 10,
        "in_progress": "N/A",
        "completed": "N/A"
      },
      "cronjobs": []
    }
    ```
    This confirms that `backlog_status.unassigned` and `backlog_status.total_tasks` now accurately reflect the `unassigned_for_sprint_count` from the `backlog-service`.

### Detailed Impediments and Resolutions

#### Resolved Impediments

*   **Date**: 2025-08-25
*   **Description**: The `project-orchestrator` pod entered `CrashLoopBackOff` with an `AttributeError: 'BoundLoggerFilteringAtNotset' object has no attribute 'setLevel'` in `app.py` at line 25.
*   **Resolution**: The issue was a re-emergence of a `structlog` configuration conflict. The line `logger.setLevel(logging.DEBUG)` was present in `app.py` when the Docker image was built, despite being removed locally. This was resolved by performing a Docker build with `--no-cache` to ensure a fresh build, then pushing the new image, and re-applying the Kubernetes deployment.
*   **Status**: Resolved

*   **Date**: 2025-08-25
*   **Description**: The `project-orchestrator`'s logs showed that the `backlog_summary` received from the `backlog-service` for `project_id=test-001` contained `"total_tasks": 0` and `"unassigned_for_sprint_count": 0`, even though direct queries to `backlog-service` showed correct counts.
*   **Resolution**: The discrepancy was due to a case sensitivity issue when the `project-orchestrator` called the `backlog-service`. The `project-orchestrator` was passing `project_id=test-001` (lowercase), but the `backlog-service` was expecting `TEST-001` (uppercase). The `project_analyzer.py` was modified to convert the `project_id` to uppercase before calling `backlog_client.get_backlog_summary`. After rebuilding and redeploying the `project-orchestrator`, the status endpoint now correctly reflects the `unassigned_for_sprint_count`.
*   **Status**: Resolved
