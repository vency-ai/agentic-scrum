#!/bin/sh

# Script to find failing Kubernetes jobs related to daily scrums and check their associated sprint status.
# If the sprint is completed, it will find and delete the corresponding CronJob.
# This version is designed to run INSIDE a Kubernetes pod with kubectl access.

NAMESPACE="dsm"
SPRINT_SERVICE_URL="http://sprint-service.dsm.svc.cluster.local"

log_info() {
    echo "ℹ️  $1"
}

log_success() {
    echo "✅ $1"
}

log_warning() {
    echo "⚠️  $1"
}

log_error() {
    echo "❌ $1"
}

echo "============================================================"
echo "🔍 Analyzing Failing Kubernetes Jobs and Sprint Statuses"
echo "============================================================"

# Get all failing jobs that match the 'run-dailyscrum-' pattern.
failing_jobs_names=$(kubectl get jobs -n "$NAMESPACE" -o wide 2>/dev/null | grep 'Failed' | awk '{print $1}' | grep '^run-dailyscrum-')

if [ -z "$failing_jobs_names" ]; then
    log_info "No failing 'run-dailyscrum-' jobs found in namespace '$NAMESPACE'."
    exit 0
fi

log_info "Found failing daily scrum jobs. Checking associated sprint statuses..."

for job_name in $failing_jobs_names; do
    # Use a robust regex to extract the SPRINT_ID from the job name.
    # The SPRINT_ID is assumed to be the part of the name that ends with '-s' followed by numbers (e.g., "gem-001-s04").
    # This extracts the full sprint ID from a job name like "run-dailyscrum-gem-001-gem-001-s04-29352360".
    # The regex is designed to handle the "run-dailyscrum-<project>-<project>-s<number>-<timestamp>" pattern,
    # capturing the project and sprint number to correctly form the sprint ID.
    SPRINT_ID_RAW=$(echo "$job_name" | sed -E 's/^run-dailyscrum-(.+)-\1(-s[0-9]+)-[0-9]+$/\1\2/')

    # If sed fails to match, it returns the original string. We check for that.
    if [ "$SPRINT_ID_RAW" = "$job_name" ]; then
        log_warning "Could not parse SPRINT_ID from job name: $job_name. Skipping."
        continue
    fi

    # The PROJECT_ID is derived by removing the sprint suffix (e.g., "-s04") from the SPRINT_ID.
    PROJECT_ID_RAW=$(echo "$SPRINT_ID_RAW" | sed -E 's/(-s[0-9]+)$//')

    if [ -z "$PROJECT_ID_RAW" ]; then
        log_warning "Failed to parse PROJECT_ID from job name: $job_name. Skipping."
        continue
    fi

    # Convert to uppercase for API calls and logging consistency.
    PROJECT_ID=$(echo "$PROJECT_ID_RAW" | tr '[:lower:]' '[:upper:]')
    SPRINT_ID=$(echo "$SPRINT_ID_RAW" | tr '[:lower:]' '[:upper:]')

    log_info "Job: $job_name, Project: $PROJECT_ID, Sprint: $SPRINT_ID"

    # Get sprint status from Sprint Service (direct curl from within the pod)
    sprint_status_json=""
    retries=3
    count=0
    while [ -z "$sprint_status_json" ] && [ "$count" -lt "$retries" ]; do
        sprint_status_json=$(curl -s "$SPRINT_SERVICE_URL/sprints/$SPRINT_ID" 2>/dev/null)
        if [ -z "$sprint_status_json" ]; then
            log_warning "Attempt $((count+1)) to retrieve sprint status for $SPRINT_ID failed. Retrying..."
            sleep 2
        fi
        count=$((count + 1))
    done
    
    if [ -z "$sprint_status_json" ]; then
        log_error "Failed to retrieve sprint status for $SPRINT_ID after $retries retries. Sprint Service might be unreachable or sprint does not exist."
        continue
    fi

    sprint_status=$(echo "$sprint_status_json" | jq -r '.sprint.status // "unknown"')

    if [ "$sprint_status" = "unknown" ]; then
        log_warning "Sprint status for $SPRINT_ID is 'unknown'. Full response: $sprint_status_json"
    else
        log_success "Job: $job_name -> Sprint: $SPRINT_ID is in status: $sprint_status"
        
        # If sprint is completed or closed, find and delete the associated CronJob
        if [ "$sprint_status" = "completed" ] || [ "$sprint_status" = "closed_with_pending_tasks" ]; then
            # Reconstruct the CronJob name from the raw (lowercase) IDs.
            CRONJOB_NAME="run-dailyscrum-${PROJECT_ID_RAW}-${SPRINT_ID_RAW}"
            log_info "Checking for CronJob: $CRONJOB_NAME"
            
            # Verify CronJob exists before attempting to delete
            if kubectl get cronjob "$CRONJOB_NAME" -n "$NAMESPACE" > /dev/null 2>&1; then
                log_info "CronJob $CRONJOB_NAME found. Deleting..."
                if kubectl delete cronjob "$CRONJOB_NAME" -n "$NAMESPACE"; then
                    log_success "Successfully deleted CronJob: $CRONJOB_NAME"
                else
                    log_error "Failed to delete CronJob: $CRONJOB_NAME"
                fi
            else
                log_warning "CronJob $CRONJOB_NAME not found. It might have been deleted already or name is incorrect."
            fi
        fi
    fi
done

echo "============================================================"
echo "Cleanup and Analysis complete."
