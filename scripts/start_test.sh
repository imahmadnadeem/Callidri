#!/usr/bin/env bash
# start_test.sh
# ---------------------
# Starts the FastAPI server, waits for it to be ready, then triggers
# /join-room so the agent joins the LiveKit room automatically.
# Run the mic client separately in another terminal.
#
# Usage:
#   ./start_test.sh                  # defaults: room="test-room", port=8000
#   ROOM=my-room PORT=8080 ./start_test.sh

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
ROOM="${ROOM:-test-room}"
SERVER_URL="http://localhost:${PORT}"

# ── Step 1: Start the FastAPI server ──────────────────────────────────────────
echo ""
echo "=========================================="
echo "  🚀 STEP 1: Starting FastAPI server"
echo "=========================================="
echo "[start_test] Running: python server.py (port $PORT)"
echo ""

cd "$SCRIPT_DIR"
python server.py &
SERVER_PID=$!

# Make sure the server is killed when this script exits
trap 'echo "" && echo "[start_test] 🛑 Shutting down server (PID $SERVER_PID)..." && kill $SERVER_PID 2>/dev/null && wait $SERVER_PID 2>/dev/null && echo "[start_test] ✅ Server stopped."' EXIT

echo "[start_test] Server started with PID $SERVER_PID"

# ── Step 2: Wait for the server to be ready ───────────────────────────────────
echo ""
echo "=========================================="
echo "  ⏳ STEP 2: Waiting 3 seconds for server startup"
echo "=========================================="
sleep 3

# Quick health check
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "[start_test] ❌ ERROR: Server process died during startup. Check logs above."
  exit 1
fi
echo "[start_test] ✅ Server is running."

# ── Step 3: Call /join-room ───────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  📡 STEP 3: Calling POST /join-room"
echo "=========================================="
echo "[start_test] Room: $ROOM"
echo ""

RESPONSE=$(curl -s -X POST "${SERVER_URL}/join-room" \
  -H "Content-Type: application/json" \
  -d "{\"room\": \"${ROOM}\"}")

echo "[start_test] Response: $RESPONSE"
echo ""
echo "=========================================="
echo "  ✅ Agent is running! Connect your mic client now."
echo "  Press Ctrl-C to stop the server."
echo "=========================================="
echo ""

# Keep the script alive so the server keeps running
wait "$SERVER_PID"
