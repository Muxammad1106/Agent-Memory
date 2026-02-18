#!/bin/bash
set -e

#===============================================================================
# Agent Memory MCP Server - One-Command Installation Script
# 
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/deploy/install.sh | bash
#   
# Or with custom domain:
#   curl -fsSL ... | bash -s -- --domain mcp.example.com --email admin@example.com
#
# Requirements: Ubuntu 22.04+ / Debian 12+ with root access
#===============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
INSTALL_DIR="/opt/agent-memory"
DOMAIN=""
EMAIL=""
OLLAMA_MODELS="llama3.2:3b nomic-embed-text:latest"
ENABLE_SSL=false
EXPOSE_PORT=8000

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain)
            DOMAIN="$2"
            ENABLE_SSL=true
            shift 2
            ;;
        --email)
            EMAIL="$2"
            shift 2
            ;;
        --port)
            EXPOSE_PORT="$2"
            shift 2
            ;;
        --models)
            OLLAMA_MODELS="$2"
            shift 2
            ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --domain DOMAIN    Domain name for SSL (e.g., mcp.example.com)"
            echo "  --email EMAIL      Email for Let's Encrypt SSL certificate"
            echo "  --port PORT        Port to expose (default: 8000)"
            echo "  --models MODELS    Ollama models to install (default: llama3.2:3b nomic-embed-text:latest)"
            echo "  --dir DIR          Installation directory (default: /opt/agent-memory)"
            echo "  --help             Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

#===============================================================================
# Helper Functions
#===============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
    else
        log_error "Cannot detect OS. This script supports Ubuntu/Debian only."
        exit 1
    fi
    
    if [[ "$OS" != "ubuntu" && "$OS" != "debian" ]]; then
        log_error "This script supports Ubuntu/Debian only. Detected: $OS"
        exit 1
    fi
    
    log_info "Detected OS: $OS $VERSION"
}

#===============================================================================
# Installation Functions
#===============================================================================

install_dependencies() {
    log_info "Installing system dependencies..."
    
    apt-get update -qq
    apt-get install -y -qq \
        curl \
        wget \
        git \
        ca-certificates \
        gnupg \
        lsb-release \
        ufw \
        htop \
        jq \
        unzip
    
    log_success "System dependencies installed"
}

install_docker() {
    if command -v docker &> /dev/null; then
        log_info "Docker already installed: $(docker --version)"
        return
    fi
    
    log_info "Installing Docker..."
    
    # Remove old versions
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    
    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$OS/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add repository
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS \
        $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Start and enable Docker
    systemctl start docker
    systemctl enable docker
    
    log_success "Docker installed: $(docker --version)"
}

install_ollama() {
    if command -v ollama &> /dev/null; then
        log_info "Ollama already installed"
    else
        log_info "Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        log_success "Ollama installed"
    fi
    
    # Start Ollama service
    log_info "Starting Ollama service..."
    
    # Create systemd service if not exists
    if [[ ! -f /etc/systemd/system/ollama.service ]]; then
        cat > /etc/systemd/system/ollama.service << 'EOF'
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=root
Group=root
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=0.0.0.0"

[Install]
WantedBy=default.target
EOF
    fi
    
    systemctl daemon-reload
    systemctl enable ollama
    systemctl start ollama
    
    # Wait for Ollama to be ready
    log_info "Waiting for Ollama to start..."
    sleep 5
    
    for i in {1..30}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            break
        fi
        sleep 2
    done
    
    # Pull required models
    log_info "Downloading AI models (this may take a while)..."
    for model in $OLLAMA_MODELS; do
        log_info "Pulling model: $model"
        ollama pull $model || log_warn "Failed to pull $model, continuing..."
    done
    
    log_success "Ollama setup complete"
}

clone_repository() {
    log_info "Setting up Agent Memory..."
    
    mkdir -p $INSTALL_DIR
    cd $INSTALL_DIR
    
    # Clone or update repository
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log_info "Updating existing installation..."
        git pull origin main || true
    else
        log_info "Cloning repository..."
        # If repo doesn't exist yet, create from current files
        if [[ ! -f "$INSTALL_DIR/docker-compose.yml" ]]; then
            # Download from GitHub (replace with actual repo URL)
            git clone https://github.com/YOUR_USERNAME/Agent-Memory.git . 2>/dev/null || {
                log_warn "Repository not found, creating from template..."
                create_project_files
            }
        fi
    fi
    
    log_success "Project files ready"
}

create_project_files() {
    # Create docker-compose.yml for production
    cat > $INSTALL_DIR/docker-compose.yml << 'EOF'
version: "3.9"

services:
  app:
    build: .
    ports:
      - "${EXPOSE_PORT:-8000}:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://agent:${DB_PASSWORD:-agentpass}@postgres:5432/agent_brain
      - REDIS_URL=redis://redis:6379/0
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - LLM_PROVIDER=ollama
      - LLM_MODEL=llama3.2:3b
      - EMBEDDING_PROVIDER=ollama
      - EMBEDDING_MODEL=nomic-embed-text
      - PROJECT_PATH_MAPPINGS=/host-projects=/host-projects
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app/app
      - /:/host-projects:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${DB_PASSWORD:-agentpass}
      POSTGRES_DB: agent_brain
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent -d agent_brain"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
EOF

    log_info "Created docker-compose.yml"
}

create_env_file() {
    log_info "Creating environment configuration..."
    
    # Generate secure password
    DB_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 24)
    SECRET_KEY=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c 48)
    
    cat > $INSTALL_DIR/.env << EOF
# Agent Memory MCP Server Configuration
# Generated on $(date)

# Database
DB_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgresql+asyncpg://agent:$DB_PASSWORD@postgres:5432/agent_brain

# Redis
REDIS_URL=redis://redis:6379/0

# Ollama (AI Models)
OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2:3b
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text

# Security
SECRET_KEY=$SECRET_KEY

# Server
EXPOSE_PORT=$EXPOSE_PORT
HOST=0.0.0.0
PORT=8000

# Path mappings for Docker
PROJECT_PATH_MAPPINGS=/host-projects=/host-projects

# Domain (if SSL enabled)
DOMAIN=$DOMAIN
EOF

    chmod 600 $INSTALL_DIR/.env
    log_success "Environment file created"
}

setup_firewall() {
    log_info "Configuring firewall..."
    
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow $EXPOSE_PORT/tcp
    
    if [[ "$ENABLE_SSL" == "true" ]]; then
        ufw allow 80/tcp
        ufw allow 443/tcp
    fi
    
    ufw --force enable
    
    log_success "Firewall configured"
}

setup_ssl() {
    if [[ "$ENABLE_SSL" != "true" || -z "$DOMAIN" ]]; then
        log_info "SSL not configured (no domain specified)"
        return
    fi
    
    log_info "Setting up SSL with Let's Encrypt..."
    
    # Install Nginx and Certbot
    apt-get install -y -qq nginx certbot python3-certbot-nginx
    
    # Create Nginx config
    cat > /etc/nginx/sites-available/agent-memory << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    location / {
        proxy_pass http://127.0.0.1:$EXPOSE_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
        proxy_buffering off;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/agent-memory /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    
    nginx -t && systemctl restart nginx
    
    # Get SSL certificate
    if [[ -n "$EMAIL" ]]; then
        certbot --nginx -d $DOMAIN --email $EMAIL --agree-tos --non-interactive --redirect
    else
        certbot --nginx -d $DOMAIN --register-unsafely-without-email --agree-tos --non-interactive --redirect
    fi
    
    # Setup auto-renewal
    systemctl enable certbot.timer
    systemctl start certbot.timer
    
    log_success "SSL configured for $DOMAIN"
}

start_services() {
    log_info "Starting Agent Memory services..."
    
    cd $INSTALL_DIR
    
    # Build and start containers
    docker compose pull 2>/dev/null || true
    docker compose build --no-cache
    docker compose up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to start..."
    sleep 10
    
    for i in {1..30}; do
        if curl -s http://localhost:$EXPOSE_PORT/health | grep -q "ok"; then
            break
        fi
        sleep 2
    done
    
    log_success "Services started"
}

create_systemd_service() {
    log_info "Creating systemd service for auto-start..."
    
    cat > /etc/systemd/system/agent-memory.service << EOF
[Unit]
Description=Agent Memory MCP Server
Requires=docker.service
After=docker.service ollama.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable agent-memory
    
    log_success "Systemd service created"
}

print_summary() {
    echo ""
    echo "============================================================"
    echo -e "${GREEN}✅ Agent Memory MCP Server Installation Complete!${NC}"
    echo "============================================================"
    echo ""
    echo "📁 Installation directory: $INSTALL_DIR"
    echo ""
    
    if [[ "$ENABLE_SSL" == "true" && -n "$DOMAIN" ]]; then
        echo "🌐 MCP Server URL: https://$DOMAIN"
        echo "🔗 MCP SSE Endpoint: https://$DOMAIN/mcp/sse"
    else
        SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
        echo "🌐 MCP Server URL: http://$SERVER_IP:$EXPOSE_PORT"
        echo "🔗 MCP SSE Endpoint: http://$SERVER_IP:$EXPOSE_PORT/mcp/sse"
    fi
    
    echo ""
    echo "📋 Quick Commands:"
    echo "   View logs:     cd $INSTALL_DIR && docker compose logs -f"
    echo "   Restart:       cd $INSTALL_DIR && docker compose restart"
    echo "   Stop:          cd $INSTALL_DIR && docker compose down"
    echo "   Update:        cd $INSTALL_DIR && git pull && docker compose up -d --build"
    echo ""
    echo "🤖 AI Models installed:"
    for model in $OLLAMA_MODELS; do
        echo "   - $model"
    done
    echo ""
    echo "🔧 MCP Config for Windsurf/Cursor:"
    echo ""
    cat << MCPCONFIG
{
  "mcpServers": {
    "agent-brain": {
      "serverType": "sse",
      "url": "http://$SERVER_IP:$EXPOSE_PORT/mcp/sse"
    }
  }
}
MCPCONFIG
    echo ""
    echo "============================================================"
}

#===============================================================================
# Main Installation Flow
#===============================================================================

main() {
    echo ""
    echo "============================================================"
    echo "   Agent Memory MCP Server - Installation Script"
    echo "============================================================"
    echo ""
    
    check_root
    check_os
    
    log_info "Starting installation..."
    
    install_dependencies
    install_docker
    install_ollama
    clone_repository
    create_env_file
    setup_firewall
    setup_ssl
    start_services
    create_systemd_service
    
    print_summary
}

# Run main function
main "$@"
