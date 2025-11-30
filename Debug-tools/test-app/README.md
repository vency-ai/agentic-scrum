# Enhanced testapp-pod

An upgraded version of the original testapp-pod that includes Python 3 and all dependencies needed for CR_Agent_03 memory system testing.

## Overview

This enhanced testapp-pod builds upon the original Ubuntu 22.04 base image and adds:

- **Python 3.10** with complete development environment
- **All CR_Agent_03 memory system dependencies** (asyncpg, httpx, tenacity, pydantic)
- **Testing frameworks** (pytest, pytest-asyncio)
- **Development tools** (ipython, rich, typer)
- **Database tools** (psycopg2-binary, postgresql-client)
- **Additional utilities** for testing and development

## Files

- `Dockerfile` - Enhanced Docker image with Python and memory system dependencies
- `pod-testapp-pod.yml` - Kubernetes pod manifest using private registry
- `build-enhanced-testapp.sh` - Build and push script following DSM patterns
- `deploy-enhanced-testapp.sh` - Deploy script with registry secret management
- `verify_installation.py` - Verification script to test all dependencies

## Quick Start

### 1. Build and Push Image

```bash
cd /home/sysadmin/sysadmin/k8s/prj-sdlc/projects/test-app/
./build-enhanced-testapp.sh
```

This will:
- Build the Docker image with all dependencies
- Tag it as `myreg.agile-corp.org:5000/testapp-enhanced:1.0.0`
- Push to the local registry
- Verify all packages are installed correctly

### 2. Deploy Enhanced Pod

```bash
./deploy-enhanced-testapp.sh
```

This will:
- Verify/create the registry secret (`agile-corp-reg-secret`)
- Delete the old testapp-pod if it exists
- Deploy the enhanced version
- Wait for pod to be ready
- Run verification tests

### 3. Use the Enhanced Pod

```bash
# Enter the pod
kubectl exec -it testapp-pod -n dsm -- bash

# Test Python environment
kubectl exec testapp-pod -n dsm -- python3 --version

# Test memory system packages
kubectl exec testapp-pod -n dsm -- python3 -c "import asyncpg, httpx, tenacity, pydantic; print('All CR_Agent_03 packages available!')"

# Run full verification
kubectl exec testapp-pod -n dsm -- python3 /app/verify_installation.py
```

## CR_Agent_03 Memory System Testing

The enhanced testapp-pod is specifically designed for testing the memory system components implemented in CR_Agent_03:

### Copy Memory System Code

```bash
# Copy memory system code to the pod
kubectl cp ./projects/project-orchestrator/src/memory/ dsm/testapp-pod:/tmp/memory/

# Test memory models
kubectl exec -it testapp-pod -n dsm -- python3 -c "
import sys
sys.path.append('/tmp/memory')
from models import Episode, Strategy, WorkingMemorySession
print('✅ Memory models loaded successfully!')
"
```

### Test Connectivity to Memory Services

```bash
# Test embedding service
kubectl exec testapp-pod -n dsm -- python3 -c "
import asyncio, httpx
async def test():
    async with httpx.AsyncClient() as client:
        response = await client.get('http://embedding-service.dsm.svc.cluster.local/health')
        print(f'Embedding service: {response.status_code}')
asyncio.run(test())
"

# Test database connectivity
kubectl exec testapp-pod -n dsm -- python3 -c "
import asyncio, asyncpg
async def test():
    conn = await asyncpg.connect('postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory')
    result = await conn.fetchval('SELECT 1')
    await conn.close()
    print(f'Database connection: {result}')
asyncio.run(test())
"
```

## Package List

### Core CR_Agent_03 Dependencies
- `asyncpg==0.29.0` - PostgreSQL async driver for agent_memory database
- `httpx` - HTTP client for embedding service communication  
- `tenacity==8.2.3` - Retry logic for network operations
- `pydantic` - Data validation for Episode, Strategy, and WorkingMemorySession models

### Testing & Development
- `pytest` & `pytest-asyncio` - Testing frameworks
- `ipython` - Enhanced Python shell
- `rich` - Rich text and formatting
- `typer` - CLI framework

### Database & Networking
- `psycopg2-binary` - PostgreSQL driver
- `postgresql-client` - Command-line PostgreSQL tools
- `redis` - Redis client

### Additional Utilities
- `requests` - HTTP library
- `structlog` - Structured logging
- `aiofiles` - Async file operations
- `uvloop` - Fast event loop

### System Tools (from original testapp-pod)
- `nano`, `vim` - Text editors
- `jq` - JSON processor
- `netcat`, `dnsutils` - Network tools
- `curl`, `wget` - HTTP tools
- `iputils-ping`, `tree` - System utilities
- `htop`, `git` - Development tools

## Verification

The image includes a comprehensive verification script at `/app/verify_installation.py` that:

- Tests all Python package imports
- Checks connectivity to memory system services (when in cluster)
- Validates memory system model creation
- Provides detailed success/failure reporting

## Comparison with Original testapp-pod

| Feature | Original testapp-pod | Enhanced testapp-pod |
|---------|---------------------|---------------------|
| Base Image | Ubuntu 22.04 | Ubuntu 22.04 |
| Python | ❌ Not installed | ✅ Python 3.10 |
| Memory System Deps | ❌ None | ✅ All CR_Agent_03 packages |
| Testing Tools | ❌ Basic shell only | ✅ pytest, ipython |
| Database Tools | ❌ None | ✅ psycopg2, postgresql-client |
| Registry | ❌ No registry support | ✅ Private registry with secrets |
| Health Checks | ❌ None | ✅ Readiness/liveness probes |
| Memory/CPU Limits | ❌ None | ✅ Resource limits configured |

## Integration with DSM System

The enhanced testapp-pod follows DSM deployment patterns:

- Uses the private registry `myreg.agile-corp.org:5000`
- Includes `imagePullSecrets` for registry authentication
- Follows semantic versioning (1.0.0)
- Includes proper resource limits and health checks
- Uses ConfigMap-based verification scripts

This makes it fully compatible with the existing DSM microservices architecture while providing a complete testing environment for the CR_Agent_03 memory system implementation.
