#!/usr/bin/env bash
# ===========================================================================
# deploy.sh — Deploy Interactive Presenter
#
# Builds and starts the app container (127.0.0.1:8000).
# Your existing nginx reverse-proxies to it — see deploy/nginx/snippet.conf.
#
# Usage:
#   ./deploy.sh          # Build and start
#   ./deploy.sh down     # Stop
#   ./deploy.sh logs     # Follow logs
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

info() { echo "==> $*"; }

case "${1:-}" in
    down)
        info "Stopping..."
        docker compose down
        ;;
    logs)
        docker compose logs -f
        ;;
    *)
        info "Building and starting Interactive Presenter..."
        docker compose up -d --build
        echo
        info "App listening on 127.0.0.1:8000"
        info "Point your nginx at it — see deploy/nginx/snippet.conf"
        echo
        info "Commands:"
        info "  ./deploy.sh logs   — follow logs"
        info "  ./deploy.sh down   — stop"
        ;;
esac
