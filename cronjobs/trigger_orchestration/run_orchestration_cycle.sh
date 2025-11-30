#!/bin/sh

# A POSIX-compliant script to run the full orchestration lifecycle for a given project.
#
# Usage: ./run_orchestration_cycle.sh <project_id>
# Example: ./run_orchestration_cycle.sh AEG003

# --- Configuration ---
# Namespace where the services are running (not directly used in curl, but kept for context)
NAMESPACE="dsm"
# Base URL for the orchestrator service
ORCHESTRATOR_URL="http://project-orchestrator.dsm.svc.cluster.local"
# Base URL for the backlog service
BACKLOG_URL="http://backlog-service.dsm.svc.cluster.local:80"

# --- Argument Validation ---
if [ -z "$1" ]; then
  echo "Error: No project ID provided."
  echo "Usage: $0 <project_id>"
  exit 1
fi

PROJECT_ID="$1"

# --- JSON Payload for Orchestration ---
# This payload is used for all orchestration calls.
CRON_SCHEDULE_FILE="/scripts/cronjob-schedule.json"
PROJECT_ID_LOWER=$(echo "$PROJECT_ID" | tr '[:upper:]' '[:lower:]')
PROJECT_SCHEDULE=$(jq -r "."$PROJECT_ID_LOWER"" "$CRON_SCHEDULE_FILE" 2>/dev/null)

if [ -z "$PROJECT_SCHEDULE" ] || [ "$PROJECT_SCHEDULE" = "null" ]; then
  echo "Warning: Schedule not found for project '$PROJECT_ID' in '$CRON_SCHEDULE_FILE'. Using default schedule '0 08 * * 1-5'."
  PROJECT_SCHEDULE="0 08 * * 1-5"
else
  echo "Info: Schedule for project '$PROJECT_ID' is '$PROJECT_SCHEDULE'."
fi

ORCHESTRATION_PAYLOAD='{
  "action": "analyze_and_orchestrate",
  "options": {
    "create_sprint_if_needed": true,
    "assign_tasks": true,
    "create_cronjob": true,
    "schedule": "'"$PROJECT_SCHEDULE"'",
    "sprint_duration_weeks": 2,
    "max_tasks_per_sprint": 10
  }
}'

# --- Helper Function for Running Commands ---
# This function executes a command and prints a header.
run_command() {
  echo "\n------------------------------------------------------------------"
  echo "$1"
  echo "------------------------------------------------------------------"
  # The 'eval' command is used here to correctly substitute the PROJECT_ID
  # into the command string before execution.
  eval "$2"
  # Add a brief pause to allow services to process and for readability
  sleep 2
}

# --- Main Execution Flow ---

# 1. First Orchestration Call (Initial State / Close Sprint)
DESC_1="STEP 1: Running initial orchestration for project '$PROJECT_ID' (may close existing sprint)..."
CMD_1="curl -s -X POST -H 'Content-Type: application/json' -d '$ORCHESTRATION_PAYLOAD' $ORCHESTRATOR_URL/orchestrate/project/$PROJECT_ID | jq"
run_command "$DESC_1" "$CMD_1"

# 2. Generate Backlog
DESC_2="STEP 2: Generating new backlog tasks for project '$PROJECT_ID'..."
CMD_2="curl -s -X POST $BACKLOG_URL/backlogs/$PROJECT_ID | jq"
run_command "$DESC_2" "$CMD_2"

# 3. Second Orchestration Call (Create New Sprint)
DESC_3="STEP 3: Running orchestration again to create a new sprint for project '$PROJECT_ID' மூன்றாம்"
CMD_3="curl -s -X POST -H 'Content-Type: application/json' -d '$ORCHESTRATION_PAYLOAD' $ORCHESTRATOR_URL/orchestrate/project/$PROJECT_ID | jq"
run_command "$DESC_3" "$CMD_3"

# 4. Third Orchestration Call (Verify Monitoring State)
DESC_4="STEP 4: Running final orchestration to verify the monitoring state for project '$PROJECT_ID' மூன்றாம்"
CMD_4="curl -s -X POST -H 'Content-Type: application/json' -d '$ORCHESTRATION_PAYLOAD' $ORCHESTRATOR_URL/orchestrate/project/$PROJECT_ID | jq"
run_command "$DESC_4" "$CMD_4"

echo "\n------------------------------------------------------------------"
echo "Orchestration cycle for project '$PROJECT_ID' complete."
echo "------------------------------------------------------------------"