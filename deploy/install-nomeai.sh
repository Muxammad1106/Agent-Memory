#!/bin/bash
set -e

#===============================================================================
# Agent Memory MCP Server - Installation for mcp.nomeai.space
# 
# Usage on server:
#   curl -fsSL https://raw.githubusercontent.com/davranaff/Agent-Memory/main/deploy/install-nomeai.sh | sudo bash
#===============================================================================

DOMAIN="mcp.nomeai.space"
EMAIL="admin@nomeai.space"
INSTALL_DIR="/opt/agent-memory"
OLLAMA_MODELS="llama3.2:3b nomic-embed-text:latest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check root
if [[ $EUID -ne 0 ]]; then
    log_error "Run as root: sudo bash install-nomeai.sh"
    exit 1
fi

# Detect OS
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS=$ID
else
    log_error "Cannot detect OS"
    exit 1
fi

log_info "Installing Agent Memory MCP Server for $DOMAIN"

#===============================================================================
# Install Dependencies
#===============================================================================

log_info "Installing system packages..."
apt-get update -qq
apt-get install -y -qq curl wget git ca-certificates gnupg lsb-release ufw htop jq unzip

#===============================================================================
# Install Docker
#===============================================================================

if ! command -v docker &> /dev/null; then
    log_info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi
log_success "Docker: $(docker --version)"

#===============================================================================
# Install Ollama
#===============================================================================

if ! command -v ollama &> /dev/null; then
    log_info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Configure Ollama service
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

systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

log_info "Waiting for Ollama..."
sleep 5
for i in {1..30}; do
    curl -s http://localhost:11434/api/tags > /dev/null 2>&1 && break
    sleep 2
done

# Download AI models
log_info "Downloading AI models (this takes a while)..."
for model in $OLLAMA_MODELS; do
    log_info "Pulling $model..."
    ollama pull $model || log_warn "Failed to pull $model"
done
log_success "Ollama ready"

#===============================================================================
# Clone Repository
#===============================================================================

log_info "Setting up project..."
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

if [[ -d ".git" ]]; then
    git pull origin main || true
else
    git clone https://github.com/davranaff/Agent-Memory.git . || {
        log_error "Failed to clone repository"
        exit 1
    }
fi

#===============================================================================
# Create Environment File
#===============================================================================

DB_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 24)
SECRET_KEY=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c 48)

cat > $INSTALL_DIR/.env << EOF
# Agent Memory MCP Server - mcp.nomeai.space
# Generated: $(date)

DATABASE_URL=postgresql+asyncpg://agent:$DB_PASSWORD@postgres:5432/agent_brain
REDIS_URL=redis://redis:6379/0
OLLAMA_BASE_URL=http://host.docker.internal:11434

LLM_PROVIDER=ollama
LLM_MODEL=llama3.2:3b
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text

DB_PASSWORD=$DB_PASSWORD
SECRET_KEY=$SECRET_KEY
PROJECT_PATH_MAPPINGS=/host-projects=/host-projects

DOMAIN=$DOMAIN
EOF

chmod 600 $INSTALL_DIR/.env
log_success "Environment configured"

#===============================================================================
# Configure Firewall
#===============================================================================

log_info "Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
log_success "Firewall configured"

#===============================================================================
# Setup Nginx + SSL
#===============================================================================

log_info "Installing Nginx and Certbot..."
apt-get install -y -qq nginx certbot python3-certbot-nginx

cat > /etc/nginx/sites-available/agent-memory << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
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

log_info "Getting SSL certificate..."
certbot --nginx -d $DOMAIN --email $EMAIL --agree-tos --non-interactive --redirect || {
    log_warn "SSL failed - will work on HTTP only"
}

systemctl enable certbot.timer
systemctl start certbot.timer
log_success "Nginx + SSL configured"

#===============================================================================
# Start Services
#===============================================================================

log_info "Starting Docker services..."
cd $INSTALL_DIR
docker compose build --no-cache
docker compose up -d

log_info "Waiting for services..."
sleep 15

for i in {1..30}; do
    if curl -s http://localhost:8000/health | grep -q "ok"; then
        break
    fi
    sleep 2
done

#===============================================================================
# Create Systemd Service
#===============================================================================

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

#===============================================================================
# Done!
#===============================================================================

echo ""
echo "============================================================"
echo -e "${GREEN}✅ Agent Memory MCP Server Installed!${NC}"
echo "============================================================"
echo ""
echo "🌐 URL: https://$DOMAIN"
echo "🔗 MCP Endpoint: https://$DOMAIN/mcp/sse"
echo ""
echo "📋 MCP Config for Windsurf/Cursor:"
echo ""
cat << 'MCPCONFIG'
{
  "mcpServers": {
    "agent-brain": {
      "serverType": "sse",
      "url": "https://mcp.nomeai.space/mcp/sse"
    }
  }
}
MCPCONFIG
echo ""
echo "📁 Install dir: $INSTALL_DIR"
echo ""
echo "Commands:"
echo "  Logs:    cd $INSTALL_DIR && docker compose logs -f"
echo "  Restart: cd $INSTALL_DIR && docker compose restart"
echo "  Update:  cd $INSTALL_DIR && git pull && docker compose up -d --build"
echo ""
echo "============================================================"
