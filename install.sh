#!/bin/bash
# =============================================================
#  StockMarket AI Dashboard — Deploy Script
#  Repo: https://github.com/AshishBarad/StockMarket
#  Prerequisites: Docker already installed
# =============================================================
set -e

echo ""
echo "================================================"
echo "  📈 StockMarket AI Dashboard — Deploy"
echo "================================================"
echo ""

# ── Clone or update repo ───────────────────────────────────
if [ -d "StockMarket" ]; then
  echo "➤ Repo already exists, pulling latest changes..."
  cd StockMarket
  git pull origin main
else
  echo "➤ Cloning from GitHub..."
  git clone https://github.com/AshishBarad/StockMarket.git
  cd StockMarket
fi

# ── Set up .env ────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Fill in your Dhan credentials in .env:"
  echo "     nano .env"
  echo ""
  read -p "Press ENTER after saving .env to continue..."
fi

# ── Create docker_internal network if it doesn't exist ─────
if ! docker network inspect docker_internal &>/dev/null; then
  echo "➤ Creating docker_internal network..."
  docker network create docker_internal
else
  echo "➤ docker_internal network already exists."
fi

# ── Build and launch ───────────────────────────────────────
echo ""
echo "➤ Building image and starting container..."
docker compose up -d --build

echo ""
echo "================================================"
echo "  ✅ Deployed!"
echo "================================================"
echo ""
echo "  📊 Dashboard   : http://$(hostname -I | awk '{print $1}'):8501"
echo "  📋 Live logs   : docker compose logs -f"
echo "  🔄 Restart     : docker compose restart"
echo "  🛑 Stop        : docker compose down"
echo ""