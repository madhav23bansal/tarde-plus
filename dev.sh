#!/usr/bin/env bash
# Trade-Plus dev startup — runs Docker, API, and Web in order
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== Trade-Plus Dev ==="
echo ""

# 1. Docker services
echo "[1/3] Starting Docker services..."
docker compose up -d
echo "  Redis:       localhost:6380"
echo "  TimescaleDB: localhost:5434"
echo "  PostgreSQL:  localhost:5435"
echo ""

# Wait for healthy
echo "  Waiting for containers to be healthy..."
for i in $(seq 1 30); do
  ALL_HEALTHY=true
  for c in tradeplus-redis tradeplus-timescaledb tradeplus-postgres; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$c" 2>/dev/null || echo "missing")
    if [ "$STATUS" != "healthy" ]; then
      ALL_HEALTHY=false
    fi
  done
  if [ "$ALL_HEALTHY" = true ]; then
    echo "  All containers healthy."
    break
  fi
  sleep 1
done
echo ""

# 2. Check Python venv exists
if [ ! -f "$ROOT/apps/api/.venv/bin/python" ]; then
  echo "[!] Python venv not found. Running setup..."
  cd "$ROOT/apps/api"
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]"
  .venv/bin/pip install fastapi uvicorn yfinance feedparser vaderSentiment
  cd "$ROOT"
  echo ""
fi

# 3. Run database migrations
echo "[2/4] Running database migrations..."
cd "$ROOT/apps/api"
.venv/bin/alembic upgrade head
.venv/bin/alembic -c alembic_trades.ini upgrade head
cd "$ROOT"
echo "  Migrations applied."
echo ""

# 4. Start API + Web via turbo (parallel)
echo "[3/4] Starting API server (port 8000)..."
echo "[4/4] Starting Web dashboard (port 3000)..."
echo ""
echo "  API:  http://localhost:8000"
echo "  Web:  http://localhost:3000"
echo "  Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

npx turbo dev
