#!/bin/sh

# An enhanced POSIX-compliant script to find the current (active) sprint and its
# completion status for all projects, or for a specific project.
#
# This script prints a report to the console AND generates a project_status.csv file.
#
# Usage: ./generate_sprint_report.sh [project_id]

# --- Configuration ---
SPRINT_SERVICE_URL="http://sprint-service.dsm.svc.cluster.local"
NAMESPACE="dsm"
CSV_FILE="/tmp/project_status.csv" # Changed to write to /tmp

# --- CSV Initialization ---
# Create the CSV file and write the header row. This will overwrite any existing file.
echo "project_id,sprint_id,total_tasks,completed_tasks,completion_percentage" > "$CSV_FILE"

# --- Main Logic ---

# Check for optional PROJECT_ID argument
if [ -n "$1" ]; then
    TARGET_PROJECT_ID="$1"
    echo "Fetching current sprint status for project: $TARGET_PROJECT_ID"
    PROJECT_IDS="$TARGET_PROJECT_ID"
else
    echo "Fetching current sprint status for all projects..."
    # 1. Get all unique project IDs that have associated sprints
    ALL_PROJECT_IDS_JSON=$(curl -s -X GET -H "Content-Type: application/json" "$SPRINT_SERVICE_URL/sprints/list_projects")

    # Check if curl command was successful and returned valid JSON
    if [ $? -ne 0 ] || [ -z "$ALL_PROJECT_IDS_JSON" ]; then
        echo "Error: Failed to retrieve project IDs. Check connectivity or service status."
        exit 1
    fi

    # Parse project IDs
    PROJECT_IDS=$(echo "$ALL_PROJECT_IDS_JSON" | jq -r '.[].project_id')
fi

echo "--------------------------------------------------"

for PROJECT_ID in $PROJECT_IDS; do
    echo "Processing Project: $PROJECT_ID"
    echo "--------------------------------------------------"

    # 3. Get active sprints for the current project
    ACTIVE_SPRINTS_JSON=$(curl -s -X GET -H "Content-Type: application/json" "$SPRINT_SERVICE_URL/sprints/by-project/$PROJECT_ID?status=in_progress")

    if [ $? -ne 0 ] || [ -z "$ACTIVE_SPRINTS_JSON" ]; then
        echo "  Error: Failed to retrieve active sprints for project $PROJECT_ID. Skipping."
        echo "$PROJECT_ID,ERROR,0,0,0.00" >> "$CSV_FILE"
        echo "--------------------------------------------------"
        continue
    fi

    # Check if an active sprint was found
    ACTIVE_SPRINT_ID=$(echo "$ACTIVE_SPRINTS_JSON" | jq -r '.[0].sprint_id // empty')

    if [ -z "$ACTIVE_SPRINT_ID" ]; then
        echo "  No active sprint found for project $PROJECT_ID."
        # Write placeholder data to the CSV for projects with no active sprint
        echo "$PROJECT_ID,N/A,0,0,0.00" >> "$CSV_FILE"
        echo "--------------------------------------------------"
        continue
    fi

    echo "  Current Sprint: $ACTIVE_SPRINT_ID"

    # 4. Get task summary for the active sprint
    TASK_SUMMARY_JSON=$(curl -s -X GET -H "Content-Type: application/json" "$SPRINT_SERVICE_URL/sprints/$ACTIVE_SPRINT_ID/task-summary")

    if [ $? -ne 0 ] || [ -z "$TASK_SUMMARY_JSON" ]; then
        echo "    Error: Failed to retrieve task summary for sprint $ACTIVE_SPRINT_ID."
        echo "$PROJECT_ID,$ACTIVE_SPRINT_ID,ERROR,ERROR,ERROR" >> "$CSV_FILE"
        echo "--------------------------------------------------"
        continue
    fi

    TOTAL_TASKS=$(echo "$TASK_SUMMARY_JSON" | jq -r '.total_tasks')
    COMPLETED_TASKS=$(echo "$TASK_SUMMARY_JSON" | jq -r '.completed_tasks')

    # 5. Calculate the percentage using awk for POSIX-compliant float arithmetic
    if [ "$TOTAL_TASKS" -eq 0 ]; then
        COMPLETION_PERCENTAGE="0.00"
    else
        COMPLETION_PERCENTAGE=$(awk "BEGIN { printf \"%.2f\", ($COMPLETED_TASKS / $TOTAL_TASKS) * 100 }")
    fi

    # 6. Print results to console
    echo "    Total Tasks: $TOTAL_TASKS"
    echo "    Completed Tasks: $COMPLETED_TASKS"
    echo "    Completion Percentage: $COMPLETION_PERCENTAGE%"

    # 7. Append the results to the CSV file
    echo "$PROJECT_ID,$ACTIVE_SPRINT_ID,$TOTAL_TASKS,$COMPLETED_TASKS,$COMPLETION_PERCENTAGE" >> "$CSV_FILE"

    echo "--------------------------------------------------"
done

echo "Script finished."
echo "Report saved to: $CSV_FILE"
