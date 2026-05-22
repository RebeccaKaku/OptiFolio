#!/usr/bin/env python3
"""
OptiFolio Startup Script
This script bootstraps the local environment and starts the FastAPI server.
"""

import sys
import os
import subprocess

def check_python_version():
    """Verify that Python version is between 3.11 and 3.14 (exclusive)."""
    version = sys.version_info
    if not (version.major == 3 and 11 <= version.minor < 14):
        print(f"Error: Python {version.major}.{version.minor} is not supported.")
        print("Python >=3.11, <3.14 is required.")
        sys.exit(1)
    print(f"Python {version.major}.{version.minor} detected.")

def bootstrap():
    """Initialize local runtime files."""
    print("Bootstrapping local runtime state...")
    # Add project root to sys.path to allow importing src
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from src.runtime.bootstrap import bootstrap_local_state
    result = bootstrap_local_state()
    print(f"Local runtime is ready at {result['local_dir']}")

def start_server():
    """Start the FastAPI server using uvicorn."""
    port = 8011
    print(f"Starting FastAPI server on port {port}...")

    # Use subprocess to run uvicorn
    # This assumes uvicorn is installed in the environment
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "src.api.fastapi_app:app",
            "--host", "0.0.0.0",
            "--port", str(port)
        ], check=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_python_version()
    bootstrap()
    start_server()
