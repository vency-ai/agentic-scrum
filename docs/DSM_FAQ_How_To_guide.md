# DSM FAQ: How-To Guide

This guide provides answers to frequently asked questions and demonstrates how to achieve specific operational goals within the Digital Scrum Master (DSM) system using `kubectl` and `curl` commands.

---

## 1. How can I find a project with an active sprint where all tasks are completed?

### Question
I need to identify if there's any project currently running an active sprint where all assigned tasks have been marked as completed.

### Answer and Workflow Explanation

To find a project with an active sprint that has all tasks completed, you need to perform a two-step process:

1.  **List all projects and their sprints**: First, retrieve a comprehensive list of all projects and their associated sprints from the Sprint Service. This initial step provides an overview of all sprints, their current statuses (e.g., `in_progress`, `completed`, `closed_with_pending_tasks`), and the project IDs they belong to.
2.  **Check task summary for active sprints**: Iterate through the identified active sprints (those with `status: "in_progress"`). For each active sprint, query the Sprint Service's `/sprints/{sprint_id}/task-summary` endpoint. This endpoint provides a summary of tasks within that sprint, including the total number of tasks and the count of completed tasks.

A sprint is considered to have "all tasks completed" if:
*   The `total_tasks` count is greater than 0, AND the `completed_tasks` count is equal to `total_tasks`.
*   Alternatively, if `total_tasks` is 0, it vacuously means all tasks are completed (as there are no tasks to be incomplete).

### How it was achieved

We used the `kubectl exec` command to run `curl` requests from within a `testapp-pod` in the `dsm` namespace. This simulates how an internal service or an administrator would interact with the Sprint Service.

First, we fetched a list of all projects and their sprints. Then, we manually reviewed the output to identify sprints with `status: "in_progress"`. For each active sprint, we made a subsequent `curl` call to its `/task-summary` endpoint to check the completion status.

During our investigation, we found several active sprints with `total_tasks: 0` and `completed_tasks: 0`. While technically all tasks are completed in such sprints, we did not find any active sprints that had a positive number of tasks where all of them were completed.

### Commands and Expected Output

#### Step 1: List all projects and their sprints

This command retrieves a list of all projects and their associated sprints, including their statuses.

```bash
kubectl exec -it testapp-pod -n dsm -- curl -s http://sprint-service.dsm.svc.cluster.local/sprints/list_projects | jq
```

**Expected Output (Truncated for brevity, showing relevant active sprints):**

```json
[
  {
    "project_id": "AEG003",
    "sprints": [
      {
        "sprint_id": "AEG003-S05",
        "project_id": "AEG003",
        "sprint_name": "New Sprint for AEG003",
        "start_date": "2025-09-03",
        "end_date": "2025-09-17",
        "duration_weeks": 2,
        "status": "in_progress"
      }
    ]
  },
  {
    "project_id": "APO009",
    "sprints": [
      {
        "sprint_id": "APO009-S02",
        "project_id": "APO009",
        "sprint_name": "Sprint for Smart Inventory Management",
        "start_date": "2025-09-02",
        "end_date": "2025-09-16",
        "duration_weeks": 2,
        "status": "in_progress"
      }
    ]
  },
  {
    "project_id": "GEM-001",
    "sprints": [
      {
        "sprint_id": "GEM-001-S01",
        "project_id": "GEM-001",
        "sprint_name": "Test Sprint",
        "start_date": "2025-08-15",
        "end_date": "2025-08-29",
        "duration_weeks": 2,
        "status": "in_progress"
      }
    ]
  }
  // ... more projects and sprints ...
]
```

#### Step 2: Check task summary for identified active sprints

For each `sprint_id` with `status: "in_progress"` from the previous step, execute the following command.

**Example 1: Checking `AEG003-S05` (an active sprint with pending tasks)**

```bash
kubectl exec -it testapp-pod -n dsm -- curl -s http://sprint-service.dsm.svc.cluster.local/sprints/AEG003-S05/task-summary | jq
```

**Expected Output:**

```json
{
  "total_tasks": 10,
  "completed_tasks": 0,
  "pending_tasks": 10
}
```
*Explanation*: This sprint is active but has 10 pending tasks, so it does not meet the criteria.

**Example 2: Checking `APO009-S02` (an active sprint with zero tasks)**

```bash
kubectl exec -it testapp-pod -n dsm -- curl -s http://sprint-service.dsm.svc.cluster.local/sprints/APO009-S02/task-summary | jq
```

**Expected Output:**

```json
{
  "total_tasks": 0,
  "completed_tasks": 0,
  "pending_tasks": 0
}
```
*Explanation*: This sprint is active and has 0 total tasks. Therefore, all tasks are technically completed. This sprint meets the criteria.

**Conclusion**: Based on the current data, `APO009-S02` (and other similar sprints with 0 total tasks) is an example of an active sprint where all tasks are completed. If you were looking for an active sprint that *had* tasks and now all are completed, none were found in the current "in_progress" list.

---

## 2. How to assign tasks from the backlog to an active sprint when they are not showing up?

### Question
I have tasks in the Backlog Service for project `APO009` that are incorrectly assigned to a completed sprint (`APO009-S01`). Meanwhile, my active sprint (`APO009-S02`) for the same project has no tasks. How can I get these tasks into the active sprint?

### Answer and Workflow Explanation

This scenario indicates a data inconsistency where the Backlog Service still links tasks to an old, completed sprint, and the Sprint Service's active sprint has an empty task list. The DSM system's design dictates that tasks are primarily assigned to a sprint during the sprint creation process. Therefore, the solution involves making the tasks `unassigned` in the backlog and then creating a *new* sprint to pick them up.

Here's the step-by-step workflow:

1.  **Identify Tasks**: Confirm which tasks are incorrectly assigned in the Backlog Service.
2.  **Unassign Tasks in Backlog**: For each identified task, update its `status` to `unassigned` and set `sprint_id` to `null` in the Backlog Service. This makes them available for assignment.
3.  **Close Active Sprint**: Close the currently active sprint (`APO009-S02`). This is crucial because the Sprint Service only allows one active sprint per project, and we need to create a *new* one to trigger the task assignment logic. Closing an active sprint will also move any tasks *it internally manages* back to the backlog as `unassigned` (though in this specific case, `APO009-S02` has no tasks, so this step primarily clears the "active sprint" state).
4.  **Create New Sprint**: Create a brand new sprint for project `APO009`. The Sprint Service will automatically detect and assign the `unassigned` tasks from the Backlog Service to this newly created sprint.
5.  **Verify**: Confirm that the tasks are now correctly assigned to the new active sprint in both the Backlog and Sprint Services.

### Commands and Expected Output

We will use `kubectl exec` to run `curl` commands from within a `testapp-pod` in the `dsm` namespace.

#### Step 1: Verify current state (as provided in the problem)

**Tasks in Backlog for `APO009` (incorrectly assigned to `APO009-S01`):**
```bash
kubectl exec -it testapp-pod -n dsm -- curl http://backlog-service.dsm.svc.cluster.local/backlogs/APO009 | jq
```
**Expected Output (showing tasks assigned to `APO009-S01`):**
```json
[
  {
    "task_id": "APO009-TASK001",
    "project_id": "APO009",
    "title": "Setup development environment",
    "description": "Configure IDEs and necessary tools.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK002",
    "project_id": "APO009",
    "title": "Design database schema",
    "description": "Create ERD and define tables.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK003",
    "project_id": "APO009",
    "title": "Implement user authentication",
    "description": "Develop login/logout and registration features.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK004",
    "project_id": "APO009",
    "title": "Build UI for dashboard",
    "description": "Create the main dashboard interface.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK005",
    "project_id": "APO009",
    "title": "Develop API for task management",
    "description": "Implement CRUD operations for tasks.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK006",
    "project_id": "APO009",
    "title": "Write unit tests for backend",
    "description": "Ensure code quality with comprehensive tests.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK007",
    "project_id": "APO009",
    "title": "Deploy to staging environment",
    "description": "Set up CI/CD for automated deployments.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK008",
    "project_id": "APO009",
    "title": "Conduct user acceptance testing",
    "description": "Gather feedback from end-users.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK009",
    "project_id": "APO009",
    "title": "Prepare documentation",
    "description": "Write API docs and user guides.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  },
  {
    "task_id": "APO009-TASK010",
    "project_id": "APO009",
    "title": "Refactor legacy code",
    "description": "Improve existing code for maintainability.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S01",
    "progress_percentage": 0
  }
]
```

**Active Sprint for `APO009` (identified as `APO009-S02`):**
```bash
kubectl exec -it testapp-pod -n dsm -- curl -s http://sprint-service.dsm.svc.cluster.local/sprints/active/APO009 | jq
```
**Expected Output:**
```json
{
  "sprint_id": "APO009-S02"
}
```

**Tasks in Active Sprint `APO009-S02` (empty):**
```bash
kubectl exec -it testapp-pod -n dsm -- curl http://sprint-service.dsm.svc.cluster.local/sprints/APO009-S02/tasks | jq
```
**Expected Output:**
```json
[]
```

#### Step 2: Manually unassign tasks in Backlog Service

We will update each task to `status: "unassigned"` and `sprint_id: null`.

```bash
TASK_IDS=("APO009-TASK001" "APO009-TASK002" "APO009-TASK003" "APO009-TASK004" "APO009-TASK005" "APO009-TASK006" "APO009-TASK007" "APO009-TASK008" "APO009-TASK009" "APO009-TASK010")
for TASK_ID in "${TASK_IDS[@]}"; do
  kubectl exec -it testapp-pod -n dsm -- curl -X PUT -H "Content-Type: application/json" -d '{
    "status": "unassigned",
    "sprint_id": null,
    "assigned_to": null
  }' http://backlog-service.dsm.svc.cluster.local/tasks/${TASK_ID} | jq
done
```
**Expected Output (for each task):**
```json
{
  "message": "Task APO009-TASK001 updated successfully"
}
```

**Verification of tasks in Backlog Service (after unassigning):**
```bash
kubectl exec -it testapp-pod -n dsm -- curl http://backlog-service.dsm.svc.cluster.local/backlogs/APO009 | jq
```
**Expected Output (showing all tasks as `unassigned` and `sprint_id: null`):**
```json
[
  {
    "task_id": "APO009-TASK001",
    "project_id": "APO009",
    "title": "Setup development environment",
    "description": "Configure IDEs and necessary tools.",
    "status": "unassigned",
    "assigned_to": null,
    "sprint_id": null,
    "progress_percentage": 0
  },
  # ... (other tasks similar)
]
```

#### Step 3: Close the active sprint `APO009-S02`

```bash
kubectl exec -it testapp-pod -n dsm -- curl -X POST http://sprint-service.dsm.svc.cluster.local/sprints/APO009-S02/close | jq
```
**Expected Output:**
```json
{
  "message": "Sprint closure processed for APO009-S02.",
  "sprint_id": "APO009-S02",
  "status_updated_to": "completed",
  "completed_tasks_count": 0,
  "uncompleted_tasks_moved_to_backlog_count": 0,
  "retrospective_report_id": "..."
}
```
*Explanation*: Even though `APO009-S02` had no tasks, closing it ensures the project no longer has an `in_progress` sprint, allowing a new one to be created.

#### Step 4: Create a new sprint for `APO009`

This will be a new sprint, which will automatically pick up the `unassigned` tasks.

```bash
kubectl exec -it testapp-pod -n dsm -- curl -X POST -H "Content-Type: application/json" -d '{
    "sprint_name": "New Sprint for APO009",
    "duration_weeks": 2
}' http://sprint-service.dsm.svc.cluster.local/sprints/APO009 | jq
```
**Expected Output (note the new `sprint_id` and `assigned_tasks_count`):**
```json
{
  "message": "Sprint 'New Sprint for APO009' started successfully for project APO009",
  "sprint_id": "APO009-S03", # Or similar new sprint ID
  "assigned_tasks_count": 10
}
```

#### Step 5: Final Verification

**Verify tasks in the new active sprint (e.g., `APO009-S03`):**
```bash
kubectl exec -it testapp-pod -n dsm -- curl http://sprint-service.dsm.svc.cluster.local/sprints/APO009-S03/tasks | jq
```
**Expected Output (showing all 10 tasks assigned to the new sprint):**
```json
[
  {
    "task_id": "APO009-TASK001",
    "title": "Setup development environment",
    "status": "assigned_to_sprint",
    "sprint_id": "APO009-S03",
    "progress_percentage": 0
  },
  # ... (all 10 tasks are listed here with sprint_id APO009-S03)
]
```

**Verify tasks in Backlog Service for `APO009` (should now show tasks assigned to the new sprint):**
```bash
kubectl exec -it testapp-pod -n dsm -- curl http://backlog-service.dsm.svc.cluster.local/backlogs/APO009 | jq
```
**Expected Output (showing all tasks with `sprint_id` of the new sprint, e.g., `APO009-S03`):**
```json
[
  {
    "task_id": "APO009-TASK001",
    "project_id": "APO009",
    "title": "Setup development environment",
    "description": "Configure IDEs and necessary tools.",
    "status": "assigned_to_sprint",
    "assigned_to": null,
    "sprint_id": "APO009-S03",
    "progress_percentage": 0
  },
  # ... (all 10 tasks are listed here with sprint_id APO009-S03)
]
```

---

## 3. How to Delete a Project and All Associated Data

### Question
I need to permanently delete a project and all of its associated data from the system. What is the correct procedure to do this safely?

### Answer and Workflow Explanation

Deleting a project is a permanent and irreversible operation that requires direct interaction with the PostgreSQL databases of each microservice (Chronicle, Sprint, Backlog, and Project). This process is manual and must be performed with extreme caution.

**⚠️ WARNING: This operation is irreversible and will permanently delete all data associated with the specified project. Please ensure you have backups if needed and double-check the `PROJECT_ID` before executing any commands.**

The workflow involves deleting records from each service's database in a specific order to respect foreign key constraints. The general steps are:

1.  **Identify Database Pod Names**: First, you need to get the current pod names for each service's database, as these can change.
2.  **Delete Chronicle Data**: Remove all historical records from the `chronicle_db`, including retrospectives, action items, and daily scrum reports.
3.  **Delete Sprint Data**: Remove all sprint-related data from the `sprint_db`, including tasks within sprints and the sprints themselves.
4.  **Delete Backlog Data**: Remove all backlog items from the `backlog_db`, including tasks and stories.
5.  **Delete Project Data**: Finally, remove the project-team mappings and the core project record from the `project_db`.

**Prerequisites:**
*   Access to the Kubernetes cluster via `kubectl`.
*   `kubectl` command-line tool configured to connect to your cluster.
*   Knowledge of the PostgreSQL superuser password (e.g., `dsm_password`).

### Commands and Expected Output

The following commands should be executed in order. Replace `"TEST-999"` with the actual `PROJECT_ID` you intend to delete.

#### Step 1: Set Project ID and Identify Database Pods

```bash
# Set the Project ID to be deleted
export PROJECT_ID="TEST-999" # <--- REPLACE WITH THE ACTUAL PROJECT ID

# Identify the database pods
export CHRONICLE_DB_POD=$(kubectl get pods -n dsm -l app=chronicle-db -o jsonpath='{.items[0].metadata.name}')
export SPRINT_DB_POD=$(kubectl get pods -n dsm -l app=sprint-db -o jsonpath='{.items[0].metadata.name}')
export BACKLOG_DB_POD=$(kubectl get pods -n dsm -l app=backlog-db -o jsonpath='{.items[0].metadata.name}')
export PROJECT_DB_POD=$(kubectl get pods -n dsm -l app=project-db -o jsonpath='{.items[0].metadata.name}')

echo "Using Project ID: $PROJECT_ID"
echo "Chronicle DB Pod: $CHRONICLE_DB_POD"
echo "Sprint DB Pod: $SPRINT_DB_POD"
echo "Backlog DB Pod: $BACKLOG_DB_POD"
echo "Project DB Pod: $PROJECT_DB_POD"
```
**Expected Output:**
The script will print the names of the pods it has identified, which will be used in the subsequent commands.
```
Using Project ID: TEST-999
Chronicle DB Pod: chronicle-db-bb74b7fdc-fwnzs
Sprint DB Pod: sprint-db-7b9c9fb5d-fx8rp
Backlog DB Pod: backlog-db-6b54857885-xkw8z
Project DB Pod: project-db-67dc47cf5d-hsqgl
```

#### Step 2: Delete Data from Chronicle Service Database (`chronicle_db`)

```bash
# Delete retrospective action items
kubectl exec -it $CHRONICLE_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h chronicle-db -U chronicle_user -d chronicle_db -c "DELETE FROM retrospective_action_items WHERE retrospective_id IN (SELECT id FROM sprint_retrospectives WHERE project_id = '$PROJECT_ID');"

# Delete retrospective attendees
kubectl exec -it $CHRONICLE_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h chronicle-db -U chronicle_user -d chronicle_db -c "DELETE FROM retrospective_attendees WHERE retrospective_id IN (SELECT id FROM sprint_retrospectives WHERE project_id = '$PROJECT_ID');"

# Delete sprint retrospectives
kubectl exec -it $CHRONICLE_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h chronicle-db -U chronicle_user -d chronicle_db -c "DELETE FROM sprint_retrospectives WHERE project_id = '$PROJECT_ID';"

# Delete daily scrum reports and other general notes
kubectl exec -it $CHRONICLE_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h chronicle-db -U chronicle_user -d chronicle_db -c "DELETE FROM chronicle_notes WHERE project_id = '$PROJECT_ID';"
```
**Expected Output:** For each command, `psql` will output a `DELETE <count>` message indicating how many rows were deleted.

#### Step 3: Delete Data from Sprint Service Database (`sprint_db`)

```bash
# Delete tasks associated with sprints for the project
kubectl exec -it $SPRINT_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h sprint-db -U dsm_user -d sprint_db -c "DELETE FROM tasks WHERE sprint_id LIKE '$PROJECT_ID-S%';"

# Delete sprints for the project
kubectl exec -it $SPRINT_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h sprint-db -U dsm_user -d sprint_db -c "DELETE FROM sprints WHERE project_id = '$PROJECT_ID';"
```
**Expected Output:** `DELETE <count>` for each command.

#### Step 4: Delete Data from Backlog Service Database (`backlog_db`)

```bash
# Delete story-task mappings
kubectl exec -it $BACKLOG_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h backlog-db -U dsm_user -d backlog_db -c "DELETE FROM story_tasks WHERE task_id IN (SELECT task_id FROM tasks WHERE project_id = '$PROJECT_ID');"

# Delete tasks
kubectl exec -it $BACKLOG_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h backlog-db -U dsm_user -d backlog_db -c "DELETE FROM tasks WHERE project_id = '$PROJECT_ID';"

# Delete backlog entries
kubectl exec -it $BACKLOG_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h backlog-db -U dsm_user -d backlog_db -c "DELETE FROM backlog WHERE project_id = '$PROJECT_ID';"
```
**Expected Output:** `DELETE <count>` for each command.

#### Step 5: Delete Data from Project Service Database (`project_db`)

```bash
# Delete project-team mappings
kubectl exec -it $PROJECT_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h project-db -U dsm_user -d project_db -c "DELETE FROM project_team_mapping WHERE project_id = '$PROJECT_ID';"

# Delete the project itself
kubectl exec -it $PROJECT_DB_POD -n dsm -- env PGPASSWORD=dsm_password psql -h project-db -U dsm_user -d project_db -c "DELETE FROM projects WHERE prjid = '$PROJECT_ID';"
```
**Expected Output:** `DELETE <count>` for each command.

**Important Notes**:
*   **Order of Deletion**: The commands are ordered to respect foreign key constraints. Deleting child records before parent records prevents errors.
*   **`PROJECT_ID`**: Always replace `"TEST-999"` with the actual ID of the project you intend to delete. A typo here can lead to unintended data loss.
*   **Verification**: After running these commands, you can optionally run `SELECT COUNT(*)` queries on the respective tables with `WHERE project_id = 'YOUR_PROJECT_ID'` to confirm that the records have been deleted.

---

## 4. How to Perform Sprint Planning for a Project with Completed Sprints?

### Question
I need to start a new sprint for a project where the previous sprint has just been completed. What is the correct workflow to initiate sprint planning and document it?

### Answer and Workflow Explanation

To perform sprint planning for a project with a completed sprint, you need to follow a clear sequence of steps to ensure the new sprint is created correctly and the planning is formally recorded. The process involves:

1.  **Verify Previous Sprint is Complete**: First, confirm that there are no active sprints for the project. Attempting to close the last known sprint is a reliable way to check this; if it's already completed, the system will return an error confirming its status.
2.  **Initiate a New Sprint**: Create a new sprint via the Sprint Service. The service will automatically pull unassigned tasks from the project's backlog and assign them to this new sprint.
3.  **Retrieve New Sprint Task Details**: Fetch the list of tasks that were just assigned to the new sprint. This information is required for the formal planning report.
4.  **Generate Sprint Planning Report**: Send the new sprint's details (sprint ID, name, goal, dates, and the list of planned tasks) to the Chronicle Service. This creates an auditable, historical record of the sprint planning event.

### Commands and Expected Output

The following steps use `kubectl exec` to run `curl` commands from a debug pod within the `dsm` namespace. We will use `TIT007` as the example `project_id`.

#### Step 1: Verify Previous Sprint is Complete

This command attempts to close the last known sprint (`TIT007-S12`). The expected error confirms that the sprint is not active, allowing a new one to be created.

```bash
kubectl exec -it debug-curl-pod -n dsm -- curl -X POST -H "Content-Type: application/json" http://sprint-service.dsm.svc.cluster.local/sprints/TIT007-S12/close | jq
```

**Expected Output:**

```json
{
  "detail": "Database error during sprint validation: 409: Sprint TIT007-S12 is not in 'in_progress' status. Current status: completed"
}
```

#### Step 2: Initiate a New Sprint

This command creates a new sprint for project `TIT007`.

```bash
kubectl exec -it debug-curl-pod -n dsm -- curl -X POST -H "Content-Type: application/json" -d '{"sprint_name": "New Sprint for TIT007", "duration_weeks": 2}' http://sprint-service.dsm.svc.cluster.local/sprints/TIT007 | jq
```

**Expected Output (The service returns the new sprint_id, e.g., `TIT007-S14`):**

```json
{
  "message": "Sprint 'New Sprint for TIT007' started successfully for project TIT007",
  "sprint_id": "TIT007-S14",
  "assigned_tasks_count": 10
}
```

#### Step 3: Retrieve New Sprint Task Details

Use the new `sprint_id` from the previous step to fetch the details of the assigned tasks.

```bash
kubectl exec -it debug-curl-pod -n dsm -- curl -s http://sprint-service.dsm.svc.cluster.local/sprints/TIT007-S14/tasks | jq
```

**Expected Output (A JSON array of task details):**

```json
[
  {
    "task_id": "TIT007-TASK008",
    "title": "Conduct user acceptance testing",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E015"
  },
  {
    "task_id": "TIT007-TASK009",
    "title": "Prepare documentation",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E016"
  },
  {
    "task_id": "TIT007-TASK010",
    "title": "Refactor legacy code",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E017"
  },
  {
    "task_id": "TIT007-TASK007",
    "title": "Deploy to staging environment",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E014"
  },
  {
    "task_id": "TIT007-TASK001",
    "title": "Setup development environment",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E018"
  },
  {
    "task_id": "TIT007-TASK006",
    "title": "Write unit tests for backend",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E018"
  },
  {
    "task_id": "TIT007-TASK002",
    "title": "Design database schema",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E014"
  },
  {
    "task_id": "TIT007-TASK003",
    "title": "Implement user authentication",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E015"
  },
  {
    "task_id": "TIT007-TASK004",
    "title": "Build UI for dashboard",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E016"
  },
  {
    "task_id": "TIT007-TASK005",
    "title": "Develop API for task management",
    "status": "assigned_to_sprint",
    "sprint_id": "TIT007-S14",
    "progress_percentage": 0,
    "assigned_to": "E017"
  }
]
```

#### Step 4: Generate the Sprint Planning Report

Finally, post the sprint details and task list to the Chronicle Service to create a formal record.

```bash
JSON_PAYLOAD='{
  "sprint_id": "TIT007-S14",
  "project_id": "TIT007",
  "sprint_name": "New Sprint for TIT007",
  "sprint_goal": "Complete all assigned tasks for the TIT007 project.",
  "start_date": "2025-09-17",
  "end_date": "2025-10-01",
  "duration_weeks": 2,
  "planned_tasks": [
    "TIT007-TASK008",
    "TIT007-TASK009",
    "TIT007-TASK010",
    "TIT007-TASK007",
    "TIT007-TASK001",
    "TIT007-TASK006",
    "TIT007-TASK002",
    "TIT007-TASK003",
    "TIT007-TASK004",
    "TIT007-TASK005"
  ]
}'

kubectl exec -i -t debug-curl-pod -n dsm -- curl -X POST \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD" \
  http://chronicle-service.dsm.svc.cluster.local/v1/notes/sprint_planning | jq
```

**Expected Output:**

```json
{
  "message": "Sprint planning note recorded successfully",
  "note_id": "df00534b-3780-49e1-928f-080ff05f63ef"
}
```