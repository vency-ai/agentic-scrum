# Orchestration Workflow CronJob

## Introduction

This project provides a consolidated and automated solution for the entire project orchestration workflow within the Digital Scrum Master (DSM) ecosystem. It combines sprint report generation and the triggering of orchestration cycles for completed projects into a single, efficient Kubernetes CronJob.

This streamlined approach ensures that sprint reports are generated, and subsequently, orchestration actions are taken for projects that have reached 100% sprint completion, all within a single, atomic execution unit. This eliminates the need for shared persistent storage between separate jobs and simplifies deployment and management.

## Functionality

The system performs the following actions sequentially within a single pod:
1.  **Generates Sprint Report**: Identifies active sprints across all projects, queries the Sprint Service API for task summaries, calculates completion percentages, and generates a `/tmp/project_status.csv` file.
2.  **Triggers Orchestration for Completed Projects**: Reads the generated `/tmp/project_status.csv`, identifies projects with 100% sprint completion, and for each, triggers a full orchestration cycle via the `project-orchestrator` and `backlog-service` APIs.

## Project Structure

```
projects/cronjobs/trigger_orchestration
├── orchestration_workflow.sh
├── generate_sprint_report.sh
├── trigger_completed_orchestration.sh
├── run_orchestration_cycle.sh
├── cronjob-schedule.json
├── orchestration-workflow-rbac.yml
├── orchestration-workflow-cronjob.yml
├── orchestration-workflow-manual-test-job.yml
└── README.md
```

## File Explanations

*   ### `orchestration_workflow.sh`
    This is the main wrapper script that orchestrates the entire workflow. It sequentially calls `generate_sprint_report.sh` and `trigger_completed_orchestration.sh`.

*   ### `generate_sprint_report.sh`
    This script generates a sprint report.
    *   It runs inside the Kubernetes pod.
    *   It uses `curl` to directly interact with the `sprint-service`.
    *   It outputs the report to `/tmp/project_status.csv`.

*   ### `trigger_completed_orchestration.sh`
    This script reads the `/tmp/project_status.csv` file and triggers the `run_orchestration_cycle.sh` for projects with 100% sprint completion.

*   ### `run_orchestration_cycle.sh`
    This script executes the full orchestration lifecycle for a given project.
    *   It uses `curl` to directly interact with the `project-orchestrator` and `backlog-service`.
    *   It now dynamically retrieves the cron schedule for the project from `cronjob-schedule.json`.
    *   It no longer uses `kubectl exec` or depends on a `testapp-pod`.

*   ### `cronjob-schedule.json`
    This JSON file defines the specific cron schedules for individual projects. Project IDs are in lowercase.

*   ### `orchestration-workflow-rbac.yml`
    This YAML file defines the Kubernetes Role-Based Access Control (RBAC) components for the combined workflow:
    *   **`ServiceAccount` (`orchestration-workflow-sa`)**: The identity for the pods running our workflow.
    *   **`Role` (`orchestration-workflow-role`)**: Grants permissions to `get`, `list` `pods` and `configmaps` within the `dsm` namespace.
    *   **`RoleBinding` (`orchestration-workflow-rb`)**: Binds the `orchestration-workflow-sa` ServiceAccount to the `orchestration-workflow-role`.

*   ### `orchestration-workflow-cronjob.yml`
    This YAML file defines the Kubernetes `CronJob` resource for the combined workflow:
    *   **`name: orchestration-workflow`**: The name of our automated workflow CronJob.
    *   **`schedule: "30 8 * * *"`**: Configures the CronJob to run daily at 8:30 AM CST.
    *   **`serviceAccountName: orchestration-workflow-sa`**: Specifies the ServiceAccount to use.
    *   **`image: bitnami/kubectl:latest`**: Uses a Docker image that includes `kubectl` and `curl`.
    *   **`command` and `args`**: Executes our `orchestration_workflow.sh` script.
    *   **`volumeMounts` and `volumes`**: Mounts all workflow scripts from the `orchestration-workflow-scripts` ConfigMap into the pod at `/scripts/`.

*   ### `orchestration-workflow-manual-test-job.yml`
    This YAML file defines a standard Kubernetes `Job` resource for manual testing of the entire workflow.

## Deployment Steps

Follow these steps to deploy the consolidated orchestration workflow to your Kubernetes cluster.

### Prerequisites
*   `kubectl` configured and authenticated to your Kubernetes cluster.
*   Access to the `dsm` namespace.
*   `jq` installed (for local testing of script output, though not strictly required for the pod execution).

### 1. Create or Recreate the ConfigMap for all Workflow Scripts

All scripts (`orchestration_workflow.sh`, `generate_sprint_report.sh`, `trigger_completed_orchestration.sh`, `run_orchestration_cycle.sh`) need to be available inside the CronJob pod. We achieve this by storing them in a single Kubernetes ConfigMap.

*   **Initial Creation**:
    ```bash
    kubectl create configmap orchestration-workflow-scripts \
      --from-file=orchestration_workflow.sh \
      --from-file=generate_sprint_report.sh \
      --from-file=trigger_completed_orchestration.sh \
      --from-file=run_orchestration_cycle.sh \
      --from-file=cronjob-schedule.json \
      -n dsm
```

    ```
*   **Recreation (if any script changes)**:
    If you modify any of the scripts, you must update this ConfigMap for the changes to take effect in new CronJob runs.
    ```bash
    kubectl create configmap orchestration-workflow-scripts \
      --from-file=orchestration_workflow.sh \
      --from-file=generate_sprint_report.sh \
      --from-file=trigger_completed_orchestration.sh \
      --from-file=run_orchestration_cycle.sh \
      --from-file=cronjob-schedule.json \
      -n dsm -o yaml --dry-run=client | kubectl replace -f -
```
    ```

### 2. Deploy RBAC (ServiceAccount, Role, RoleBinding)

These resources grant the necessary permissions for the CronJob to interact with Kubernetes resources.

```bash
kubectl apply -f orchestration-workflow-rbac.yml -n dsm
```

### 3. Deploy the CronJob

This creates the scheduled task that will run your consolidated orchestration workflow.

```bash
kubectl apply -f orchestration-workflow-cronjob.yml -n dsm
```

## Re-deployment / Updating the Solution

If you make changes to any of the scripts or the `cronjob-schedule.json` file, or the CronJob YAML:

1.  **Update the ConfigMap**: Follow the "Recreation" step in section 1 above.
2.  **Apply CronJob Changes (if any)**: If you modify `orchestration-workflow-cronjob.yml` (e.g., schedule, image), apply those changes.
    ```bash
    kubectl apply -f orchestration-workflow-cronjob.yml -n dsm
    ```
    *Note: Updating the ConfigMap will only affect new pods created by the CronJob. Existing running jobs or pods will not automatically pick up the new script version.*

## Testing the Deployment (Manual Test Job)

To immediately test if the workflow and its Kubernetes configuration are working correctly, you can run the provided manual test Job.

1.  **Create the Manual Test Job**:
    ```bash
    kubectl create -f orchestration-workflow-manual-test-job.yml -n dsm
    ```
2.  **Monitor Status**:
    ```bash
    kubectl get job orchestration-workflow-manual-test -n dsm
    ```
3.  **View Logs**:
    ```bash
    kubectl logs -f job/orchestration-workflow-manual-test -n dsm
    ```
    **Sample Output**:
    ```
    # Placeholder for actual sample logs after running the manual test job.
    ```

4.  **Clean Up Manual Test Job**:
    ```bash
    kubectl delete job orchestration-workflow-manual-test -n dsm --ignore-not-found=true
    ```

## CronJob Schedule

The `orchestration-workflow` CronJob is scheduled to run **daily at 8:30 AM CST**.
The schedule is defined in `orchestration-workflow-cronjob.yml` as `30 8 * * *`.

## Cleanup of Old Resources

After successfully deploying the consolidated workflow, you should delete the old, separate Kubernetes resources:

```bash
kubectl delete configmap generate-sprint-report-script -n dsm --ignore-not-found=true
kubectl delete configmap run-orchestration-cycle-script -n dsm --ignore-not-found=true
kubectl delete configmap trigger-completed-orchestration-script -n dsm --ignore-not-found=true
kubectl delete serviceaccount sprint-report-generator-sa -n dsm --ignore-not-found=true
kubectl delete role sprint-report-generator-role -n dsm --ignore-not-found=true
kubectl delete rolebinding sprint-report-generator-rb -n dsm --ignore-not-found=true
kubectl delete cronjob generate-sprint-report -n dsm --ignore-not-found=true
kubectl delete job generate-sprint-report-manual-test -n dsm --ignore-not-found=true
kubectl delete serviceaccount completed-orchestration-trigger-sa -n dsm --ignore-not-found=true
kubectl delete role completed-orchestration-trigger-role -n dsm --ignore-not-found=true
kubectl delete rolebinding completed-orchestration-trigger-rb -n dsm --ignore-not-found=true
kubectl delete cronjob trigger-completed-orchestration -n dsm --ignore-not-found=true
kubectl delete job trigger-completed-orchestration-manual-test -n dsm --ignore-not-found=true
```
