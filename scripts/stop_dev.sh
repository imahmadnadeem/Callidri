#!/bin/bash

# A script to kill all background dev processes related to VoxAgent
# Updated with safety checks to avoid killing unrelated processes on the machine.

echo "Cleaning up VoxAgent development processes..."

# Get the absolute path of the project directory (where this script resides)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Targeted cleanup for Python and Uvicorn.
# We match specifically if the command line contains the project path to
# avoid killing unrelated Python processes.
echo "Stopping project-specific python/uvicorn processes..."
SAFE_PATTERNS=("python3" "python" "uvicorn")

for pattern in "${SAFE_PATTERNS[@]}"; do
    # Match both the process name and the project directory in the command line
    # This covers both 'python /path/to/script' and '/path/to/venv/bin/python'
    pkill -f "${pattern}.*${PROJECT_DIR}" 2>/dev/null
    pkill -f "${PROJECT_DIR}.*${pattern}" 2>/dev/null
done

# For infrastructure servers, we try to stop them by name, but the port-based 
# check below is the primary safeguard for these.
INFRA_PROCESSES=("redis-server" "livekit-server")
for proc in "${INFRA_PROCESSES[@]}"; do
    pkill -f "$proc" 2>/dev/null
done

# Specifically check and kill processes occupying project ports.
# This is the most reliable way to ensure the local ports are freed.
# 8000: FastAPI, 7880-7881: LiveKit, 6379: Redis
PORTS=(8000 7880 7881 6379)
for port in "${PORTS[@]}"; do
    PID=$(lsof -ti :$port)
    if [ ! -z "$PID" ]; then
        echo "Killing process on port $port (PID: $PID)..."
        kill -9 $PID 2>/dev/null
    fi
done

echo "Cleanup complete."

