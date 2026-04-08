#!/bin/bash
set -e

echo "================================================"
echo "  📈 StockMarket AI Dashboard - Starting Up"
echo "================================================"

# Ensure DB directory exists
mkdir -p /app/db

# Start the Autonomous AI Worker in background
echo "🤖 Starting AI Trading Agent (background)..."
cd /app && python utils/ai_worker.py >> /app/db/worker.log 2>&1 &
WORKER_PID=$!
echo "   AI Worker PID: $WORKER_PID"

# Give the worker a moment to initialize DB tables
sleep 3

# Start Streamlit dashboard in foreground
echo "🌐 Starting Streamlit Dashboard on port 8501..."
exec streamlit run app.py \
  --server.port=8501 \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
