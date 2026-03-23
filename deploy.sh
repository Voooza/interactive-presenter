#!/usr/bin/env bash
# ===========================================================================
# deploy.sh — Initial deployment script for Interactive Presenter
#
# This script handles the chicken-and-egg problem of Let's Encrypt:
#   1. Build the Docker image
#   2. Start nginx with HTTP-only config (for ACME challenge)
#   3. Obtain the TLS certificate via certbot
#   4. Restart with the full HTTPS nginx config
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - DNS A record pointing DOMAIN to this server's IP
#   - .env file with DOMAIN and CERTBOT_EMAIL set
#
# Usage:
#   ./deploy.sh          # First-time setup (obtain certs + start)
#   ./deploy.sh renew    # Force certificate renewal
#   ./deploy.sh down     # Stop all services
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
if [ ! -f .env ]; then
    echo "ERROR: .env file not found."
    echo "Copy .env.example to .env and configure DOMAIN and CERTBOT_EMAIL."
    exit 1
fi

# shellcheck source=/dev/null
source .env

if [ -z "${DOMAIN:-}" ]; then
    echo "ERROR: DOMAIN is not set in .env"
    exit 1
fi

if [ -z "${CERTBOT_EMAIL:-}" ]; then
    echo "ERROR: CERTBOT_EMAIL is not set in .env"
    exit 1
fi

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
info() { echo "==> $*"; }

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_down() {
    info "Stopping all services..."
    docker compose down
}

cmd_renew() {
    info "Forcing certificate renewal..."
    docker compose run --rm certbot certbot renew --webroot -w /var/www/certbot --force-renewal
    docker compose exec nginx nginx -s reload
    info "Certificate renewed and nginx reloaded."
}

cmd_deploy() {
    info "Interactive Presenter — Production Deployment"
    info "Domain: $DOMAIN"
    echo

    # Step 1: Build the application image
    info "Building Docker image..."
    docker compose build backend

    # Step 2: Check if certificates already exist
    CERT_PATH="certbot-certs"
    CERT_EXISTS=false

    # Check if the cert volume already has valid certs by looking at the
    # docker volume or the live cert path inside the volume.
    if docker compose run --rm --entrypoint "" certbot \
        test -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" 2>/dev/null; then
        CERT_EXISTS=true
    fi

    if [ "$CERT_EXISTS" = true ]; then
        info "TLS certificates already exist for $DOMAIN."
    else
        info "No TLS certificates found. Obtaining from Let's Encrypt..."

        # Step 2a: Start nginx with HTTP-only bootstrap config for ACME challenge
        info "Starting nginx with HTTP-only config for ACME challenge..."
        docker compose run -d --rm \
            --name ip-nginx-init \
            -p 80:80 \
            -v "$SCRIPT_DIR/deploy/nginx/init.conf.template:/etc/nginx/templates/default.conf.template:ro" \
            -e "DOMAIN=$DOMAIN" \
            nginx

        # Give nginx a moment to start
        sleep 3

        # Step 2b: Request certificate
        info "Requesting certificate from Let's Encrypt..."
        docker compose run --rm certbot certbot certonly \
            --webroot \
            -w /var/www/certbot \
            -d "$DOMAIN" \
            --email "$CERTBOT_EMAIL" \
            --agree-tos \
            --no-eff-email \
            --non-interactive

        # Stop the bootstrap nginx
        docker stop ip-nginx-init 2>/dev/null || true

        info "TLS certificate obtained successfully!"
    fi

    # Step 3: Start all services with full HTTPS config
    info "Starting all services..."
    docker compose up -d

    echo
    info "Deployment complete!"
    info "Your site is available at: https://$DOMAIN"
    echo
    info "Useful commands:"
    info "  docker compose logs -f        # Follow logs"
    info "  docker compose ps             # Check service status"
    info "  ./deploy.sh renew             # Force cert renewal"
    info "  ./deploy.sh down              # Stop all services"
}

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
case "${1:-}" in
    down)   cmd_down ;;
    renew)  cmd_renew ;;
    *)      cmd_deploy ;;
esac
