#!/bin/bash
# Build and push enhanced testapp-pod image to local registry
# Following DSM_Deployment_Operations.md patterns

set -e

# Configuration following DSM patterns
REGISTRY="myreg.agile-corp.org:5000"
IMAGE_NAME="testapp-enhanced"
IMAGE_TAG="1.0.0"
FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "=== Building Enhanced testapp-pod Image ==="
echo "Registry: ${REGISTRY}"
echo "Image: ${FULL_IMAGE_NAME}"
echo

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -t ${FULL_IMAGE_NAME} .

echo "✅ Docker image built successfully!"

# Verify the image
echo "🔍 Verifying image contents..."
docker run --rm ${FULL_IMAGE_NAME} python3 --version
docker run --rm ${FULL_IMAGE_NAME} python3 -c "import asyncpg, httpx, tenacity, pydantic; print('✅ Core CR_Agent_03 packages available')"

echo

# Push to local registry
echo "🚀 Pushing to local registry..."
docker push ${FULL_IMAGE_NAME}

echo "✅ Image built, verified, and pushed successfully!"
echo
echo "📦 Final image: ${FULL_IMAGE_NAME}"
echo
echo "🔗 Next steps:"
echo "  1. Update pod manifest to use image: ${FULL_IMAGE_NAME}"
echo "  2. Deploy using: ./deploy-enhanced-testapp.sh"
echo "  3. Verify deployment with enhanced Python environment"