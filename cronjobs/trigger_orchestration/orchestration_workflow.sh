#!/bin/sh

# Wrapper script to run the full sprint report generation and orchestration triggering workflow.
#
# This script first generates the sprint report and then triggers orchestration
# for completed projects based on that report.

# --- Configuration ---
# Path to the sprint report generation script
GENERATE_REPORT_SCRIPT="/scripts/generate_sprint_report.sh"
# Path to the completed orchestration trigger script
TRIGGER_ORCHESTRATION_SCRIPT="/scripts/trigger_completed_orchestration.sh"

echo "============================================================"
echo "🚀 Starting full orchestration workflow"
echo "============================================================"

# 1. Run the sprint report generation script
echo "\n--- Running Sprint Report Generation ---"
sh "$GENERATE_REPORT_SCRIPT"

if [ $? -ne 0 ]; then
  echo "❌ Error: Sprint report generation failed. Aborting workflow."
  exit 1
fi

echo "✅ Sprint Report Generation Complete."

# 2. Run the completed orchestration trigger script
echo "\n--- Running Completed Orchestration Trigger ---"
sh "$TRIGGER_ORCHESTRATION_SCRIPT"

if [ $? -ne 0 ]; then
  echo "❌ Error: Completed orchestration trigger failed. Workflow may be incomplete."
  # Do not exit 1 here, as report generation might have been successful
  # and we want to see the full output even if orchestration fails for some projects.
fi

echo "✅ Completed Orchestration Trigger Complete."

echo "\n============================================================"
echo "🎉 Full orchestration workflow finished."
echo "============================================================"
