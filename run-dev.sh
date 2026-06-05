#!/usr/bin/env bash
# Start the DeutschX local API, then launch the desktop app (Tauri dev).
# The API is stopped automatically when you quit.
set -e
cd "$(dirname "$0")"

# In development, keep data in the repo's ./data (a packaged install uses the per-OS
# app-data folder instead). Comment this out to test the app-data location.
export DEUTSCHX_DATA_DIR="$(pwd)/data"

source .venv/bin/activate
python -m deutschx.api &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

# Give the API a moment to come up.
sleep 1

cd desktop
pnpm tauri dev
