# Kubernetes Failing Jobs Cleanup CronJob

## Introduction

This project provides a robust solution for automatically managing and cleaning up stale Kubernetes Jobs and their associated CronJobs within the Digital Scrum Master (DSM) ecosystem. The core functionality involves identifying `Failed` Kubernetes Jobs that are related to daily scrum runs, checking the status of their corresponding sprints via the Sprint Service API, and then deleting the parent CronJob if the sprint has already reached a `completed` status.

This automation helps maintain a clean and efficient Kubernetes environment by preventing the accumulation of unnecessary and perpetually failing CronJobs for sprints that are no longer active. It ensures that our automated processes are self-healing and resource-optimized.

## Functionality

The system performs the following actions:
1.  **Identifies Failing Jobs**: Scans the `dsm` namespace for Kubernetes Jobs that are in a `Failed` state.
2.  **Parses Job Details**: Extracts the `PROJECT_ID` and `SPRINT_ID` from the names of identified failing jobs, specifically targeting `run-dailyscrum-<project_id>-<sprint_id>-<timestamp>` patterns.
3.  **Checks Sprint Status**: Queries the Sprint Service API (running within the cluster) to determine the current status of the associated sprint.
4.  **Deletes Stale CronJobs**: If a failing job's associated sprint is found to be in a `completed` status, the script proceeds to delete the parent CronJob responsible for creating that job. This prevents future runs of a CronJob for an already finished sprint.

## Project Structure

```
projects/cronjobs/clear-cronjobs
├── check_failing_jobs_sprint_status_remove_cronjob.sh
├── failing-jobs-checker-rbac.yml
├── failing-jobs-cleanup-cronjob.yml
├── failing-jobs-cleanup-manual-test-job.yml
└── README.md
```

## File Explanations

*   ### `check_failing_jobs_sprint_status_remove_cronjob.sh`
    This is the core shell script that performs the analysis and cleanup.
    *   It runs inside a Kubernetes pod with `kubectl` access.
    *   It lists all jobs, filters for `Failed` ones.
    *   It parses `PROJECT_ID` (e.g., `GEM-001`) and `SPRINT_ID` (e.g., `GEM-001-S04`) from job names.
    *   It queries the `sprint-service` (using its internal DNS name) to get the sprint's status.
    *   If the sprint status is `completed`, it reconstructs the CronJob name and deletes it using `kubectl delete cronjob`.
    *   Includes retry logic for API calls to handle eventual consistency.

*   ### `failing-jobs-checker-rbac.yml`
    This YAML file defines the Kubernetes Role-Based Access Control (RBAC) components:
    *   **`ServiceAccount` (`failing-jobs-checker-sa`)**: The identity for the pods running our script.
    *   **`Role` (`failing-jobs-checker-role`)**: Grants permissions to `get`, `list`, and `delete` `jobs` and `cronjobs`, and `get`, `list` `pods` within the `dsm` namespace. These permissions are essential for the script to perform its tasks.
    *   **`RoleBinding` (`failing-jobs-checker-rb`)**: Binds the `failing-jobs-checker-sa` ServiceAccount to the `failing-jobs-checker-role`, effectively granting the defined permissions to any pod using this ServiceAccount.

*   ### `failing-jobs-cleanup-cronjob.yml`
    This YAML file defines the Kubernetes `CronJob` resource:
    *   **`name: failing-jobs-cleanup`**: The name of our automated cleanup CronJob.
    *   **`schedule: "0 7 * * 6"`**: Configures the CronJob to run every Saturday morning at 7:00 AM CST.
    *   **`serviceAccountName: failing-jobs-checker-sa`**: Specifies that the pods created by this CronJob will use the ServiceAccount defined in `failing-jobs-checker-rbac.yml`, thus inheriting its permissions.
    *   **`image: bitnami/kubectl:latest`**: Uses a Docker image that includes `kubectl` and `curl`, allowing the script to interact with the Kubernetes API and other services.
    *   **`command` and `args`**: Executes our `check_failing_jobs_sprint_status_remove_cronjob.sh` script.
    *   **`volumeMounts` and `volumes`**: Mounts the script from a ConfigMap named `failing-jobs-checker-script` into the pod at `/scripts/`. The `defaultMode: 0755` ensures the script is executable.

*   ### `failing-jobs-cleanup-manual-test-job.yml`
    This YAML file defines a standard Kubernetes `Job` resource for manual testing:
    *   It has the same pod specification as the `CronJob`, allowing you to test the script's functionality on demand without waiting for the scheduled time.
    *   **`backoffLimit: 0`**: Configured to not retry on failure, which is suitable for manual debugging.

## Deployment Steps

Follow these steps to deploy the failing jobs cleanup solution to your Kubernetes cluster.

### Prerequisites
*   `kubectl` configured and authenticated to your Kubernetes cluster.
*   Access to the `dsm` namespace.
*   `jq` installed (for local testing of script output, though not strictly required for the pod execution).

### 1. Create or Recreate the ConfigMap

The script needs to be available inside the CronJob pod. We achieve this by storing it in a Kubernetes ConfigMap.

*   **Initial Creation**:
    ```bash
    kubectl create configmap failing-jobs-checker-script --from-file=check_failing_jobs_sprint_status_remove_cronjob.sh -n dsm
    ```
*   **Recreation (if the script changes)**:
    If you modify `check_failing_jobs_sprint_status_remove_cronjob.sh`, you must update the ConfigMap for the changes to take effect in new CronJob runs.
    ```bash
    kubectl create configmap failing-jobs-checker-script --from-file=check_failing_jobs_sprint_status_remove_cronjob.sh -n dsm -o yaml --dry-run=client | kubectl replace -f -
    ```

### 2. Deploy RBAC (ServiceAccount, Role, RoleBinding)

These resources grant the necessary permissions for the CronJob to interact with Kubernetes Jobs, CronJobs, and Pods.

```bash
kubectl apply -f failing-jobs-checker-rbac.yml -n dsm
```

### 3. Deploy the CronJob

This creates the scheduled task that will run your cleanup script.

```bash
kubectl apply -f failing-jobs-cleanup-cronjob.yml -n dsm
```

## Re-deployment / Updating the Solution

If you make changes to the `check_failing_jobs_sprint_status_remove_cronjob.sh` script:

1.  **Update the ConfigMap**: Follow the "Recreation" step in section 1 above.
    ```bash
    kubectl create configmap failing-jobs-checker-script --from-file=check_failing_jobs_sprint_status_remove_cronjob.sh -n dsm -o yaml --dry-run=client | kubectl replace -f -
    ```
2.  **Apply CronJob Changes (if any)**: If you modify `failing-jobs-cleanup-cronjob.yml` (e.g., schedule, image), apply those changes.
    ```bash
    kubectl apply -f failing-jobs-cleanup-cronjob.yml -n dsm
    ```
    *Note: Updating the ConfigMap will only affect new pods created by the CronJob. Existing running jobs or pods will not automatically pick up the new script version.*

## Testing the Deployment (Manual Test Job)

To immediately test if the script and its Kubernetes configuration are working correctly, you can run the provided manual test Job.

1.  **Create the Manual Test Job**:
    ```bash
    kubectl create -f failing-jobs-cleanup-manual-test-job.yml -n dsm
    ```
2.  **Monitor Status**:
    ```bash
    kubectl get job failing-jobs-cleanup-manual-test -n dsm
    ```
    **Sample Output**:
    ```
    NAME                                  COMPLETIONS   DURATION   AGE
    failing-jobs-cleanup-manual-test      0/1           1s         2s
    ```
3.  **View Logs**:
    ```bash
    kubectl logs -f job/failing-jobs-cleanup-manual-test -n dsm
    ```
    **Sample Output**:
    ```
    ============================================================
    🔍 Analyzing Failing Kubernetes Jobs and Sprint Statuses
    ============================================================
    ℹ️  Found failing jobs. Checking associated sprint statuses...
    ℹ️  Job: run-dailyscrum-gem-001-gem-001-s04-29352360, Project: GEM-001, Sprint: GEM-001-S04
    ✅ Job: run-dailyscrum-gem-001-gem-001-s04-29352360 -> Sprint: GEM-001-S04 is in status: completed
    ℹ️  Checking for CronJob: run-dailyscrum-gem-001-gem-001-s04
    ℹ️  CronJob run-dailyscrum-gem-001-gem-001-s04 found. Deleting...
    cronjob.batch "run-dailyscrum-gem-001-gem-001-s04" deleted
    ✅ Successfully deleted CronJob: run-dailyscrum-gem-001-gem-001-s04
    ℹ️  Job: run-dailyscrum-test-001-test-001-s19-29351940, Project: TEST-001, Sprint: TEST-001-S19
    ✅ Job: run-dailyscrum-test-001-test-001-s19-29351940 -> Sprint: TEST-001-S19 is in status: completed
    ℹ️  Checking for CronJob: run-dailyscrum-test-001-test-001-s19
    ⚠️  CronJob run-dailyscrum-test-001-test-001-s19 not found. It might have been deleted already or name is incorrect.
    ============================================================
    Cleanup and Analysis complete.
    ```
    *Expected Output*: You should see the script's output, including analysis of failing jobs and messages about CronJob deletion if applicable.

4.  **Clean Up Manual Test Job**:
    ```bash
    kubectl delete job failing-jobs-cleanup-manual-test -n dsm --ignore-not-found=true
    ```

## CronJob Schedule

The `failing-jobs-cleanup` CronJob is scheduled to run every **Saturday morning at 7:00 AM CST**.
The schedule is defined in `failing-jobs-cleanup-cronjob.yml` as `0 7 * * 6`.

---
