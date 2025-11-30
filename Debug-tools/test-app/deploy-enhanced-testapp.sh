#!/bin/bash
# Deploy enhanced testapp-pod following DSM patterns

set -e

echo "=== Enhanced testapp-pod Deployment ==="

# Configuration following DSM patterns
REGISTRY="myreg.agile-corp.org:5000"
IMAGE_NAME="testapp-enhanced"
IMAGE_TAG="1.0.0"
FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

# Verify registry secret exists (following DSM patterns)
echo "🔐 Verifying registry secret..."
if ! kubectl get secret agile-corp-reg-secret -n dsm >/dev/null 2>&1; then
    echo "❌ Registry secret not found! Creating..."
    kubectl create secret docker-registry agile-corp-reg-secret \
      --namespace=dsm \
      --docker-server=myreg.agile-corp.org:5000 \
      --docker-username="reg-user" \
      --docker-password="reg@user123" \
      --docker-email=test@test.com
    echo "✅ Registry secret created"
else
    echo "✅ Registry secret exists"
fi

# Check if old testapp-pod exists
if kubectl get pod testapp-pod -n dsm >/dev/null 2>&1; then
    echo "🔄 Existing testapp-pod found, deleting..."
    kubectl delete pod testapp-pod -n dsm --ignore-not-found=true
    echo "⏳ Waiting for old pod to terminate..."
    kubectl wait --for=delete pod/testapp-pod -n dsm --timeout=60s || true
fi

# Deploy enhanced version
echo "🚀 Deploying enhanced testapp-pod..."
kubectl apply -f pod-testapp-pod.yml

# Wait for pod to be ready
echo "⏳ Waiting for pod to be ready..."
kubectl wait --for=condition=Ready pod/testapp-pod -n dsm --timeout=120s

# Verify deployment
echo "🔍 Verifying enhanced testapp-pod deployment..."
kubectl get pod testapp-pod -n dsm -o wide

echo "🧪 Running verification script..."
kubectl exec testapp-pod -n dsm -- python3 /app/verify_installation.py

echo
echo "✅ Enhanced testapp-pod deployment complete!"
echo
echo "📋 Pod Information:"
kubectl describe pod testapp-pod -n dsm

echo
echo "📦 Enhanced testapp-pod includes:"
echo "  🐍 Python 3.10 with complete development environment"
echo "  🔧 All CR_Agent_03 memory system dependencies:"
echo "    - asyncpg (PostgreSQL async driver)"
echo "    - httpx (HTTP client for embedding service)"  
echo "    - tenacity (retry logic)"
echo "    - pydantic (data validation)"
echo "  🧪 Testing frameworks: pytest, pytest-asyncio"
echo "  🛠️  Development tools: ipython, rich, typer"
echo "  💾 Database tools: psycopg2-binary, postgresql-client"
echo "  🎯 Additional utilities: requests, structlog, redis, uvloop"

echo
echo "🔗 Usage examples:"
echo "  # Enter the enhanced pod:"
echo "  kubectl exec -it testapp-pod -n dsm -- bash"
echo
echo "  # Test memory system connectivity:"
echo "  kubectl exec testapp-pod -n dsm -- python3 /app/verify_installation.py"
echo
echo "  # Copy and test memory system code:"
echo "  kubectl cp ./projects/project-orchestrator/src/memory/ dsm/testapp-pod:/tmp/memory/"
echo "  kubectl exec -it testapp-pod -n dsm -- python3 -c 'import sys; sys.path.append(\"/tmp/memory\"); from models import Episode; print(\"Memory models loaded successfully!\")"
echo
echo "  # Test embedding service integration:"
echo "  kubectl exec testapp-pod -n dsm -- python3 -c '"
echo "    import asyncio, httpx"
echo "    async def test():"
echo "      async with httpx.AsyncClient() as client:"
echo "        response = await client.get(\"http://embedding-service.dsm.svc.cluster.local/health\")"
echo "        print(f\"Embedding service: {response.status_code}\")"
echo "    asyncio.run(test())'"
echo
echo "🎯 This enhanced testapp-pod is now ready for CR_Agent_03 memory system testing!"
