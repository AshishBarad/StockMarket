#!/bin/bash
# =============================================================
#  StockMarket AI Dashboard — One-Command Server Install
#  Repo: https://github.com/AshishBarad/StockMarket
#  Tested on: Ubuntu 20.04 / 22.04 LTS (i3 / any Linux server)
# =============================================================
set -e

echo ""
echo "================================================"
echo "  📈 StockMarket AI Dashboard Installer"
echo "================================================"
echo ""

# ── Step 1: Install Docker ─────────────────────────────────
echo "➤ Installing Docker..."
sudo apt-get update -qq
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -qq
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

sudo usermod -aG docker "$USER"
echo "   ✅ Docker installed."

# ── Step 2: Clone the repository ───────────────────────────
echo ""
echo "➤ Cloning StockMarket AI Dashboard from GitHub..."
git clone https://github.com/AshishBarad/StockMarket.git stockmarket
cd stockmarket

# ── Step 3: Set up .env credentials ────────────────────────
echo ""
echo "➤ Setting up credentials..."
cp .env.example .env
echo ""
echo "⚠️  IMPORTANT: Fill in your Dhan API credentials in .env:"
echo "     nano .env"
echo "     → Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN"
echo ""
read -p "Press ENTER once you have saved your credentials in .env..."

# ── Step 4: Build and launch ───────────────────────────────
echo ""
echo "➤ Building Docker image (2–3 minutes on first run)..."
docker compose build

echo ""
echo "➤ Starting services..."
docker compose up -d

echo ""
echo "================================================"
echo "  ✅ Installation Complete!"
echo "================================================"
echo ""
echo "  📊 Dashboard   : http://$(hostname -I | awk '{print $1}'):8501"
echo "  📋 Live logs   : docker compose logs -f"
echo "  🔄 Restart     : docker compose restart"
echo "  🛑 Stop        : docker compose down"
echo ""
echo "  The AI agent sweeps markets every 15 min inside the container."
echo "  Signals are saved in the Docker volume and survive restarts."
echo ""