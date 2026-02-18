# 🚀 Agent Memory MCP Server - Deployment Guide

## One-Command Installation

### Quick Install (Ubuntu/Debian)

```bash
# Download and run installation script
curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/deploy/install.sh | sudo bash
```

### With Custom Domain & SSL

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/deploy/install.sh | sudo bash -s -- \
  --domain mcp.yourdomain.com \
  --email admin@yourdomain.com
```

### All Options

```bash
sudo bash install.sh \
  --domain mcp.example.com \    # Domain for SSL (optional)
  --email admin@example.com \   # Email for Let's Encrypt (optional)
  --port 8000 \                 # Port to expose (default: 8000)
  --models "llama3.2:3b nomic-embed-text:latest" \  # AI models
  --dir /opt/agent-memory       # Installation directory
```

## What Gets Installed

| Component | Description |
|-----------|-------------|
| **Docker** | Container runtime |
| **PostgreSQL 16** | Database with pgvector extension |
| **Redis 7** | Cache and session storage |
| **Ollama** | Local AI model server |
| **llama3.2:3b** | LLM for agent reasoning |
| **nomic-embed-text** | Embedding model for semantic search |
| **Nginx** | Reverse proxy (if SSL enabled) |
| **Certbot** | SSL certificate management |

## Server Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| **RAM** | 4 GB | 8-16 GB |
| **CPU** | 2 cores | 4+ cores |
| **Disk** | 20 GB SSD | 50+ GB SSD |
| **OS** | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 |

## After Installation

### Check Status

```bash
# View service status
cd /opt/agent-memory
docker compose ps

# View logs
docker compose logs -f

# Check health
curl http://localhost:8000/health
```

### Configure IDE (Windsurf/Cursor)

Add to your MCP config (`~/.codeium/windsurf/mcp_config.json`):

```json
{
  "mcpServers": {
    "agent-brain": {
      "serverType": "sse",
      "url": "http://YOUR_SERVER_IP:8000/mcp/sse"
    }
  }
}
```

### Management Commands

```bash
# Restart services
cd /opt/agent-memory && docker compose restart

# Stop services
cd /opt/agent-memory && docker compose down

# Update to latest version
cd /opt/agent-memory && ./deploy/update.sh

# View database
docker compose exec postgres psql -U agent -d agent_brain

# Pull new AI models
ollama pull llama3.1:8b
```

## Firewall Ports

| Port | Service | Required |
|------|---------|----------|
| 22 | SSH | Yes |
| 80 | HTTP (SSL redirect) | If using SSL |
| 443 | HTTPS | If using SSL |
| 8000 | MCP Server | Yes (or custom) |

## Troubleshooting

### Services not starting

```bash
# Check Docker logs
docker compose logs app

# Check Ollama
systemctl status ollama
ollama list
```

### Database connection issues

```bash
# Check PostgreSQL
docker compose logs postgres

# Reset database (WARNING: deletes data)
docker compose down -v
docker compose up -d
```

### Ollama models not loading

```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Re-pull models
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

## Security Notes

1. **Change default passwords** in `.env` file
2. **Use SSL** for production deployments
3. **Restrict firewall** to only necessary ports
4. **Regular updates**: `./deploy/update.sh`

## Backup

```bash
# Backup database
docker compose exec postgres pg_dump -U agent agent_brain > backup.sql

# Backup volumes
docker run --rm -v agent-memory_pgdata:/data -v $(pwd):/backup alpine tar czf /backup/pgdata.tar.gz /data
```

## Uninstall

```bash
cd /opt/agent-memory
docker compose down -v
rm -rf /opt/agent-memory
systemctl disable agent-memory ollama
```
