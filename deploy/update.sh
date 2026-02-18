#!/bin/bash
set -e

#===============================================================================
# Agent Memory MCP Server - Update Script
#===============================================================================

INSTALL_DIR="${INSTALL_DIR:-/opt/agent-memory}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

cd $INSTALL_DIR

log_info "Pulling latest changes..."
git pull origin main || log_info "No git repo, skipping pull"

log_info "Rebuilding containers..."
docker compose build --no-cache

log_info "Restarting services..."
docker compose down
docker compose up -d

log_info "Waiting for services..."
sleep 10

if curl -s http://localhost:8000/health | grep -q "ok"; then
    log_success "Update complete! Services are healthy."
else
    log_error "Services may not be healthy. Check logs: docker compose logs"
fi
