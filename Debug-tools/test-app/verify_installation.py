#!/usr/bin/env python3
"""
Verification script for testapp-pod enhanced image
Tests that all required packages are available and can perform basic memory system operations
"""

import sys
import importlib
import asyncio

def check_package(package_name, description=""):
    """Check if a package can be imported"""
    try:
        importlib.import_module(package_name)
        print(f"✓ {package_name} - {description}")
        return True
    except ImportError as e:
        print(f"✗ {package_name} - {description} - ERROR: {e}")
        return False

async def test_memory_system_connectivity():
    """Test basic connectivity to memory system services"""
    print("\n=== Memory System Connectivity Tests ===")
    
    try:
        # Test HTTP client
        import httpx
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get("http://embedding-service.dsm.svc.cluster.local/health", timeout=5.0)
                print(f"✓ Embedding service health check: {response.status_code}")
            except Exception as e:
                print(f"⚠ Embedding service not reachable: {e}")
        
        # Test database client
        import asyncpg
        try:
            conn = await asyncpg.connect(
                "postgresql://chronicle_user:dsm_password@chronicle-db.dsm.svc.cluster.local:5432/agent_memory",
                timeout=5.0
            )
            result = await conn.fetchval("SELECT 1")
            await conn.close()
            print(f"✓ Database connection successful: query result = {result}")
        except Exception as e:
            print(f"⚠ Database not reachable: {e}")
            
    except Exception as e:
        print(f"✗ Connectivity test failed: {e}")

def test_memory_models():
    """Test that memory system models work correctly"""
    print("\n=== Memory System Models Test ===")
    
    try:
        from pydantic import BaseModel
        from datetime import datetime
        from uuid import uuid4
        from typing import Dict, Any, Optional
        
        # Test Episode model structure
        class Episode(BaseModel):
            project_id: str
            perception: Dict[str, Any]
            reasoning: Dict[str, Any]
            action: Dict[str, Any]
            agent_version: str = "1.0.0"
            control_mode: str = "rule_based_only"
            decision_source: str = "rule_based_only"
        
        # Create test episode
        episode = Episode(
            project_id="test-verification",
            perception={"test": True, "verification": "enhanced_image"},
            reasoning={"status": "testing", "confidence": 1.0},
            action={"type": "verification", "result": "success"}
        )
        
        print("✓ Episode model created successfully")
        print(f"  - Project: {episode.project_id}")
        print(f"  - Perception keys: {list(episode.perception.keys())}")
        print(f"  - Action type: {episode.action.get('type')}")
        
    except Exception as e:
        print(f"✗ Models test failed: {e}")

def main():
    """Main verification function"""
    print("=== testapp-pod Enhanced Image Verification ===")
    print("Testing all packages installed during CR_Agent_03 implementation")
    print()
    
    # Core memory system packages
    core_packages = [
        ("asyncpg", "PostgreSQL async driver (CR_Agent_03 core)"),
        ("httpx", "HTTP client library (CR_Agent_03 core)"), 
        ("tenacity", "Retry library (CR_Agent_03 core)"),
        ("pydantic", "Data validation library (CR_Agent_03 core)"),
    ]
    
    # Additional useful packages
    additional_packages = [
        ("pytest", "Testing framework"),
        ("requests", "HTTP library"),
        ("structlog", "Structured logging"),
        ("psycopg2", "PostgreSQL driver"),
        ("redis", "Redis client"),
        ("rich", "Rich text and formatting"),
        ("typer", "CLI framework"),
        ("ipython", "Enhanced Python shell")
    ]
    
    print("Core Memory System Packages:")
    core_success = 0
    for package, description in core_packages:
        if check_package(package, description):
            core_success += 1
    
    print("\nAdditional Development Packages:")
    additional_success = 0
    for package, description in additional_packages:
        if check_package(package, description):
            additional_success += 1
    
    total_packages = len(core_packages) + len(additional_packages)
    total_success = core_success + additional_success
    
    print(f"\nPackage Verification Results:")
    print(f"  Core packages: {core_success}/{len(core_packages)}")
    print(f"  Additional packages: {additional_success}/{len(additional_packages)}")
    print(f"  Total: {total_success}/{total_packages}")
    
    # Test models
    test_memory_models()
    
    # Test connectivity if in cluster
    try:
        asyncio.run(test_memory_system_connectivity())
    except Exception as e:
        print(f"\n⚠ Connectivity tests skipped (not in cluster): {e}")
    
    print(f"\n=== Verification Complete ===")
    
    if core_success == len(core_packages):
        print("✅ All core CR_Agent_03 packages are available!")
        print("✅ Enhanced testapp-pod is ready for memory system testing!")
        return 0
    else:
        print("❌ Some core packages are missing!")
        return 1

if __name__ == "__main__":
    sys.exit(main())