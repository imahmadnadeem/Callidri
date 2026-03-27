#!/usr/bin/env bash
# start_livekit_dev.sh
# ---------------------
# Starts the locally installed LiveKit server (via `brew install livekit`) for
# local development. Reads credentials from environment / .env so the same
# codebase works seamlessly with LiveKit Cloud by only swapping env vars.
#
# Usage:
#   ./start_livekit_dev.sh           # uses defaults below if vars not set
#   LIVEKIT_PORT=7880 ./start_livekit_dev.sh
#
# Expected matching .env for local dev:
#   LIVEKIT_URL=ws://localhost:7880
#   LIVEKIT_API_KEY=devkey
#   LIVEKIT_API_SECRET=secret

set -euo pipefail

# ── Load .env if present ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  # Export only LIVEKIT_* vars from .env (skip comments and empty lines)
  set -o allexport
  # shellcheck disable=SC2046
  eval $(grep -E '^LIVEKIT_(API_KEY|API_SECRET|PORT)' "$ENV_FILE" | sed 's/#.*//')
  set +o allexport
fi

# ── Defaults ──────────────────────────────────────────────────────────────────
LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-devkey}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-secret}"
LIVEKIT_PORT="${LIVEKIT_PORT:-7880}"

# ── Check binary ──────────────────────────────────────────────────────────────
if ! command -v livekit-server &>/dev/null; then
  echo "ERROR: livekit-server not found. Install with:"
  echo "  brew install livekit"
  exit 1
fi

echo "[livekit-dev] Starting LiveKit $(livekit-server --version 2>&1 | head -1)"
echo "[livekit-dev]   URL    : ws://localhost:$LIVEKIT_PORT"
echo "[livekit-dev]   API Key: $LIVEKIT_API_KEY"
echo ""
echo "[livekit-dev] Press Ctrl-C to stop."
echo ""

exec livekit-server \
  --dev \
  --bind 0.0.0.0 \
  --port "$LIVEKIT_PORT" \
  --keys "${LIVEKIT_API_KEY}: ${LIVEKIT_API_SECRET}"
