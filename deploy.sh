#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# SafeDeal — Production Server Setup Script
# Run on a fresh Ubuntu 22.04 VPS (Hetzner/DigitalOcean/etc.)
# Usage: chmod +x deploy.sh && ./deploy.sh
# ═══════════════════════════════════════════════════════════════

set -e

echo "🚀 SafeDeal Production Setup Starting..."

# ── 1. System Update ──────────────────────────────────────────
apt-get update && apt-get upgrade -y
apt-get install -y curl git nano ufw

# ── 2. Docker ─────────────────────────────────────────────────
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

echo "✅ Docker installed: $(docker --version)"

# ── 3. Firewall ───────────────────────────────────────────────
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw --force enable
echo "✅ Firewall configured"

# ── 4. Create project directory ───────────────────────────────
mkdir -p /opt/safedeal
cd /opt/safedeal

echo ""
echo "═══════════════════════════════════════════"
echo "📋 NEXT STEPS (do these manually):"
echo "═══════════════════════════════════════════"
echo ""
echo "1. Upload your project files to /opt/safedeal/"
echo "   scp -r D:\\safedeal\\* user@YOUR_SERVER:/opt/safedeal/"
echo ""
echo "2. Create .env file:"
echo "   cp .env.example .env && nano .env"
echo ""
echo "3. Set your domain DNS A record → server IP"
echo ""
echo "4. Start everything:"
echo "   cd /opt/safedeal && docker-compose up -d"
echo ""
echo "5. Get SSL certificate:"
echo "   docker-compose run certbot"
echo ""
echo "6. Check logs:"
echo "   docker-compose logs -f bot"
echo "   docker-compose logs -f api"
echo ""
