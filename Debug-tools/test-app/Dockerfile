# Enhanced testapp-pod with Python and memory system dependencies
FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Update and install base packages (from original testapp-pod)
RUN apt-get update -y && \
    apt-get install -y \
    nano \
    vim \
    jq \
    netcat \
    dnsutils \
    curl \
    wget \
    iputils-ping \
    tree \
    # Additional packages for Python development and memory system testing
    python3 \
    python3-pip \
    python3-venv \
    git \
    htop \
    postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages needed for memory system testing
RUN python3 -m pip install --no-cache-dir \
    # Core dependencies from CR_Agent_03
    asyncpg==0.29.0 \
    httpx \
    tenacity==8.2.3 \
    pydantic \
    # Additional useful packages for testing and development
    pytest \
    pytest-asyncio \
    requests \
    aiofiles \
    structlog \
    uvloop \
    # Database and networking
    psycopg2-binary \
    redis \
    # Development and debugging tools
    ipython \
    rich \
    typer

# Create working directories
RUN mkdir -p /tmp/memory /tmp/tests /app/memory

# Create verification script directory
RUN mkdir -p /app

# Add verification script
RUN cat > /app/verify_installation.py << 'EOF'
#!/usr/bin/env python3
"""
Verification script for testapp-pod enhanced image
Tests that all required packages are available
"""

import sys
import importlib

def check_package(package_name, description=""):
    try:
        importlib.import_module(package_name)
        print(f"✓ {package_name} - {description}")
        return True
    except ImportError as e:
        print(f"✗ {package_name} - {description} - ERROR: {e}")
        return False

def main():
    print("=== testapp-pod Enhanced Image Verification ===")
    print()
    
    packages = [
        ("asyncpg", "PostgreSQL async driver"),
        ("httpx", "HTTP client library"), 
        ("tenacity", "Retry library"),
        ("pydantic", "Data validation library"),
        ("pytest", "Testing framework"),
        ("requests", "HTTP library"),
        ("structlog", "Logging library"),
        ("psycopg2", "PostgreSQL driver"),
        ("redis", "Redis client"),
        ("rich", "Rich text library"),
        ("typer", "CLI library")
    ]
    
    success_count = 0
    for package, description in packages:
        if check_package(package, description):
            success_count += 1
    
    print()
    print(f"Verification Results: {success_count}/{len(packages)} packages available")
    
    if success_count == len(packages):
        print("✅ All packages installed successfully!")
        return 0
    else:
        print("❌ Some packages missing!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
EOF

# Make the verification script executable
RUN chmod +x /app/verify_installation.py

# Set working directory
WORKDIR /app

# Keep container running (same as original testapp-pod)
CMD ["tail", "-f", "/dev/null"]