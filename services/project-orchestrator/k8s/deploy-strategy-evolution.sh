#!/bin/bash
# Deploy Strategy Evolution CronJob
# This script deploys the Strategy Evolution CronJob to the DSM namespace

set -e

NAMESPACE="dsm"
CRONJOB_NAME="strategy-evolution-job"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
YAML_FILE="${SCRIPT_DIR}/strategy-evolution-cronjob.yaml"

echo "Deploying Strategy Evolution CronJob..."
echo "Namespace: ${NAMESPACE}"
echo "CronJob: ${CRONJOB_NAME}"
echo "YAML file: ${YAML_FILE}"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl is not installed or not in PATH"
    exit 1
fi

# Check if the YAML file exists
if [ ! -f "${YAML_FILE}" ]; then
    echo "Error: YAML file not found: ${YAML_FILE}"
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
    echo "Error: Namespace '${NAMESPACE}' does not exist"
    echo "Please create the namespace first: kubectl create namespace ${NAMESPACE}"
    exit 1
fi

# Apply the CronJob
echo "Applying CronJob configuration..."
kubectl apply -f "${YAML_FILE}"

if [ $? -eq 0 ]; then
    echo "✅ Strategy Evolution CronJob deployed successfully"
    
    # Show status
    echo ""
    echo "CronJob status:"
    kubectl get cronjob "${CRONJOB_NAME}" -n "${NAMESPACE}"
    
    echo ""
    echo "To view CronJob details:"
    echo "  kubectl describe cronjob ${CRONJOB_NAME} -n ${NAMESPACE}"
    
    echo ""
    echo "To manually trigger the job:"
    echo "  kubectl create job --from=cronjob/${CRONJOB_NAME} manual-strategy-evolution-$(date +%Y%m%d%H%M%S) -n ${NAMESPACE}"
    
    echo ""
    echo "To suspend/resume the CronJob:"
    echo "  kubectl patch cronjob ${CRONJOB_NAME} -n ${NAMESPACE} -p '{\"spec\":{\"suspend\":true}}'"
    echo "  kubectl patch cronjob ${CRONJOB_NAME} -n ${NAMESPACE} -p '{\"spec\":{\"suspend\":false}}'"
    
    echo ""
    echo "To view job execution logs:"
    echo "  kubectl logs -l app=strategy-evolution -n ${NAMESPACE} --follow"
    
else
    echo "❌ Failed to deploy Strategy Evolution CronJob"
    exit 1
fi