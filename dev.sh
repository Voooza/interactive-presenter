#!/usr/bin/env bash
#
# dev.sh — Start the Interactive Presenter backend and frontend for local development.
#
# Usage:
#   ./dev.sh          Start both servers (backend :8000, frontend :5173)
#   ./dev.sh stop     Stop both servers
#
# Requirements:
#   - Python 3.11+ with pip
#   - Node.js 18+ with npm
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDFILE_BACKEND="$PROJECT_ROOT/.dev-backend.pid"
PIDFILE_FRONTEND="$PROJECT_ROOT/.dev-frontend.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[dev]${NC} $*"; }
warn() { echo -e "${YELLOW}[dev]${NC} $*"; }
err()  { echo -e "${RED}[dev]${NC} $*" >&2; }

stop_servers() {
    local stopped=0
    for pidfile in "$PIDFILE_BACKEND" "$PIDFILE_FRONTEND"; do
        if [[ -f "$pidfile" ]]; then
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                log "Stopped PID $pid"
                stopped=1
            fi
            rm -f "$pidfile"
        fi
    done
    if [[ $stopped -eq 0 ]]; then
        warn "No running dev servers found."
    fi
}

if [[ "${1:-}" == "stop" ]]; then
    stop_servers
    exit 0
fi

# Stop any existing servers first
stop_servers 2>/dev/null || true

# --- Check prerequisites ---

if ! command -v python3 &>/dev/null; then
    err "python3 not found. Please install Python 3.11+."
    exit 1
fi

if ! command -v npm &>/dev/null; then
    err "npm not found. Please install Node.js 18+."
    exit 1
fi

# --- Install dependencies if needed ---

log "Checking Python dependencies..."
if ! python3 -c "import fastapi; import uvicorn" 2>/dev/null; then
    log "Installing Python dependencies..."
    pip install -e "$PROJECT_ROOT" --quiet
fi

log "Checking frontend dependencies..."
if [[ ! -d "$PROJECT_ROOT/frontend/node_modules" ]]; then
    log "Installing frontend dependencies..."
    (cd "$PROJECT_ROOT/frontend" && npm install)
fi

# --- Start servers ---

log "Starting backend on http://localhost:8000 ..."
(cd "$PROJECT_ROOT" && python3 -m backend.main) &
echo $! > "$PIDFILE_BACKEND"

log "Starting frontend on http://localhost:5173 ..."
(cd "$PROJECT_ROOT/frontend" && npm run dev -- --host) &
echo $! > "$PIDFILE_FRONTEND"

echo ""
log "Both servers running."
log "  Backend API:    http://localhost:8000"
log "  Frontend:       http://localhost:5173"
log "  Presenter view: http://localhost:5173/presentations/demo"
log "  Audience view:  http://localhost:5173/presentations/demo/audience"
echo ""
log "Press Ctrl+C to stop both, or run: ./dev.sh stop"

# Trap Ctrl+C to clean up both processes
cleanup() {
    echo ""
    log "Shutting down..."
    stop_servers
}
trap cleanup INT TERM

# Wait for both background processes
wait
