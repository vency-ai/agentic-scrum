#!/bin/sh

# A POSIX-compliant script to automate the orchestration of projects that have
# reached 100% sprint completion.
#
# This script reads '/tmp/project_status.csv', identifies completed projects,
# and then runs the '/scripts/run_orchestration_cycle.sh' for each of them.
#
# Usage: ./trigger_completed_orchestration.sh

# --- Configuration ---
CSV_FILE="/tmp/project_status.csv"
ORCHESTRATION_SCRIPT="/scripts/run_orchestration_cycle.sh"

# --- Pre-run Checks ---
# 1. Ensure the input CSV file exists.
if [ ! -f "$CSV_FILE" ]; then
  echo "Error: Input file '$CSV_FILE' not found."
  echo "Please run './generate_sprint_report.sh' first to create the report."
  exit 1
fi

# 2. Ensure the orchestration script exists and is executable.
if [ ! -x "$ORCHESTRATION_SCRIPT" ]; then
  echo "Error: Orchestration script '$ORCHESTRATION_SCRIPT' not found or is not executable."
  echo "Please ensure the script exists and you have run 'chmod +x $ORCHESTRATION_SCRIPT'."
  exit 1
fi

echo "Starting analysis of '$CSV_FILE' to find completed projects..."

# --- Main Execution Flow ---
# Read the CSV file, skipping the header row with 'tail -n +2'.
# Set the Internal Field Separator (IFS) to a comma to correctly parse columns.
tail -n +2 "$CSV_FILE" | while IFS=',' read -r project_id sprint_id total_tasks completed_tasks completion_percentage
do
  # Use printf to round the floating-point percentage to the nearest whole number
  # for safe comparison in POSIX sh.
  percentage_int=$(printf "%.0f" "$completion_percentage" 2>/dev/null)

  # Check if the rounded percentage is exactly 100.
  if [ "$percentage_int" -eq 100 ]; then
    echo "\n>>> Found completed project: '$project_id' (Status: ${completion_percentage}%)"
    echo ">>> Triggering orchestration cycle for '$project_id'..."
    
    # Execute the orchestration script for the completed project.
    sh "$ORCHESTRATION_SCRIPT" "$project_id"
    
    echo ">>> Orchestration cycle for '$project_id' finished."
  fi
done

echo "\n------------------------------------------------------------------"
echo "Completed project orchestration check finished."
echo "------------------------------------------------------------------"