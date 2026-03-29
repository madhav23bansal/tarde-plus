# Trade-Plus

Real-time algorithmic trading analysis platform for the Indian stock market. Collects market data from 15+ global sources, generates directional predictions for NSE-listed ETFs, and displays everything on a live WebSocket-powered dashboard.

> **Status**: Active development. Signal collection and prediction pipeline running. Zerodha order execution coming next.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12+-green)
![Next.js](https://img.shields.io/badge/next.js-16-black)

---

## What It Does

Trade-Plus runs a continuous analysis pipeline during Indian market hours (9:15 AM – 3:30 PM IST) that:

1. **Collects 49 global data points** — US markets, Asian markets, commodities, forex, bond yields
2. **Computes technical indicators** per instrument — RSI, MACD, Bollinger Bands, EMA, ATR, volume analysis
3. **Scores news sentiment** from 4+ RSS feeds per sector using VADER
4. **Pulls NSE-specific data** — FII/DII flows, India VIX, put-call ratio, advance/decline
5. **Generates directional predictions** — LONG, SHORT, or FLAT with confidence scores
6. **Persists everything** to TimescaleDB for backtesting and ML training
7. **Streams results** to a live dashboard via WebSocket (5s heartbeat)

### Tracked Instruments

| Ticker | Name | Sector | Drivers |
|--------|------|--------|---------|
| **NIFTYBEES** | Nippon Nifty 50 ETF | Index | FII flows, US markets, VIX, crude oil |
| **GOLDBEES** | Nippon Gold ETF | Gold | COMEX gold, USD/DXY (inverse), US yields |
| **SILVERBEES** | Nippon Silver ETF | Silver | COMEX silver, gold-silver ratio, copper |
| **BANKBEES** | Nippon Bank Nifty ETF | Banking | RBI policy, credit growth, FII flows |

All are NSE-listed, liquid, and shortable intraday on Zerodha (MIS).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SIGNAL COLLECTION (every 2min)               │
│                                                                   │
│  Layer 1: Global        Layer 2: Sector        Layer 3: Instrument│
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐   │
│  │ US Markets   │      │ Gold → DXY   │      │ Price/Volume │   │
│  │ Asia Markets │ ───> │ Index → FII  │ ───> │ RSI/MACD/BB  │   │
│  │ Commodities  │      │ Silver → G/S │      │ News Sent.   │   │
│  │ Forex/Bonds  │      │ Bank → Rates │      │ NSE Data     │   │
│  └──────────────┘      └──────────────┘      └──────────────┘   │
│         49 signals            8-19 signals         33-67 features │
│                                                                   │
│                         ┌──────────────┐                          │
│                         │  Prediction  │                          │
│                         │   Engine     │                          │
│                         │  (weighted   │                          │
│                         │   factors)   │                          │
│                         └──────┬───────┘                          │
│                                │                                  │
│                    LONG / SHORT / FLAT                             │
│                    + confidence score                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         ┌────────┐ ┌────────┐ ┌────────────┐
         │ Redis  │ │Timescale│ │ WebSocket  │
         │ Cache  │ │   DB   │ │ → Frontend │
         └────────┘ └────────┘ └────────────┘
```

### Prediction Factors (Weighted)

| Factor | Weight | Signal |
|--------|:------:|--------|
| FII/DII institutional flows | 3.0x | Net > ₹1000Cr → bullish |
| India VIX regime | 2.5x | VIX > 25 → contrarian bullish |
| Global markets (S&P 500) | 2.0x | S&P down > 0.5% → bearish |
| Put-Call Ratio | 2.0x | PCR > 1.3 → bullish |
| RSI extremes | 2.0x | RSI < 30 → oversold (buy) |
| Sector-specific driver | 2.0x | Gold: DXY down → bullish |
| Trend (EMA + MACD) | 1.5x | EMA9 > EMA21 + MACD > 0 → bullish |
| Momentum (5d/10d returns) | 1.5x | 5d return > 3% → bullish |
| Bollinger Band position | 1.0x | BB < 0.15 → near lower band |
| Volume ratio | 1.0x | Volume > 1.5x avg → confirms |
| News sentiment | 1.0x | VADER score > 0.15 → bullish |
| Market breadth (A/D ratio) | 1.0x | A/D > 2 → broad rally |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Monorepo** | Turborepo + npm workspaces | Orchestration |
| **API** | Python 3.12+, FastAPI, asyncio | Signal collection, prediction, WebSocket |
| **Frontend** | Next.js 16, React 19, Tailwind CSS | Live dashboard |
| **Time-series DB** | TimescaleDB (PostgreSQL) | Signals, predictions, pipeline runs |
| **Trades DB** | PostgreSQL 16 | Orders, trades, positions, P&L |
| **Hot Cache** | Redis 7 | Latest prices, predictions, rate limiting |
| **Migrations** | Alembic (2 databases) | Schema versioning |
| **Market Data** | Yahoo Finance (yfinance), NSE India APIs | Prices, history, FII/DII, option chain |
| **Sentiment** | VADER, RSS feeds (MoneyControl, ET, LiveMint, Google News) | News scoring |
| **Real-time** | WebSocket (FastAPI native) | Dashboard updates every 5s |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### Setup

```bash
# Clone
git clone https://github.com/madhav23bansal/tarde-plus.git
cd tarde-plus

# Install root dependencies (turborepo)
npm install

# Setup Python environment
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pip install fastapi uvicorn yfinance feedparser vaderSentiment alembic psycopg2-binary
cp .env.example .env
cd ../..

# Start everything (Docker → Migrations → API + Web)
./dev.sh
```

This starts:
- **Docker**: Redis (6380), TimescaleDB (5434), PostgreSQL (5435)
- **API**: http://localhost:8000 (with /docs for Swagger UI)
- **Dashboard**: http://localhost:3000

### Individual Commands

```bash
# Docker only
npm run docker:up
npm run docker:down

# API only
cd apps/api && .venv/bin/python -m trade_plus.api --port 8000

# Frontend only
cd apps/web && npm run dev

# Run migrations
cd apps/api
.venv/bin/alembic upgrade head                        # TimescaleDB
.venv/bin/alembic -c alembic_trades.ini upgrade head   # PostgreSQL

# Run tests
cd apps/api && .venv/bin/python -m pytest tests/ -v
```

---

## Project Structure

```
trade-plus/
├── package.json              # Root workspaces + turborepo
├── turbo.json                # Task orchestration
├── dev.sh                    # Single startup script
├── docker-compose.yml        # Redis, TimescaleDB, PostgreSQL
│
├── apps/
│   ├── api/                  # Python backend
│   │   ├── pyproject.toml
│   │   ├── alembic.ini       # TimescaleDB migrations config
│   │   ├── alembic_trades.ini # PostgreSQL migrations config
│   │   ├── migrations/       # TimescaleDB schema versions
│   │   ├── migrations_trades/ # PostgreSQL schema versions
│   │   ├── src/trade_plus/
│   │   │   ├── api.py            # FastAPI + WebSocket server
│   │   │   ├── prediction.py     # Weighted factor prediction engine
│   │   │   ├── instruments.py    # 4 ETF definitions + sector drivers
│   │   │   ├── core/
│   │   │   │   ├── config.py     # Pydantic settings (env-driven)
│   │   │   │   ├── events.py     # TickEvent, SignalEvent, OrderEvent
│   │   │   │   ├── message_bus.py # In-process pub/sub (31μs latency)
│   │   │   │   └── engine.py     # Trading engine (hot path)
│   │   │   ├── market_data/
│   │   │   │   ├── signal_collector.py # 3-layer signal collection
│   │   │   │   ├── market_hours.py     # IST sessions, holidays
│   │   │   │   ├── yahoo.py           # yfinance provider
│   │   │   │   ├── nse.py             # NSE India APIs
│   │   │   │   └── aggregator.py      # Yahoo → NSE failover
│   │   │   ├── data/
│   │   │   │   ├── redis_store.py      # Hot cache
│   │   │   │   └── timescale_store.py  # Signal + prediction persistence
│   │   │   ├── brokers/
│   │   │   │   ├── base.py            # Broker adapter interface
│   │   │   │   └── mock.py            # Simulated broker
│   │   │   ├── strategies/
│   │   │   │   ├── base.py            # Strategy ABC
│   │   │   │   └── vwap_supertrend.py # VWAP + SuperTrend strategy
│   │   │   └── risk/
│   │   │       └── manager.py         # Risk checks, kill switch
│   │   └── tests/
│   │       └── test_core.py           # 13 unit tests
│   │
│   └── web/                  # Next.js frontend
│       ├── app/
│       │   ├── page.tsx          # Main dashboard
│       │   ├── run/[id]/page.tsx # Pipeline run detail (tabbed)
│       │   ├── layout.tsx        # Root layout + providers
│       │   └── globals.css       # Dark theme tokens
│       ├── lib/
│       │   ├── ws.ts             # WebSocket store (zustand)
│       │   ├── api.ts            # REST API client
│       │   └── cn.ts             # Tailwind class merging
│       └── components/
│           ├── tip.tsx           # Radix tooltip wrapper
│           └── skeleton.tsx      # Loading skeletons
```

---

## Dashboard

### Main Dashboard
- **Header**: Live IST clock, session badge (PRE-MARKET/LIVE/CLOSED), countdown to market open, WebSocket status
- **Global Markets**: S&P 500, Nasdaq, Dow, Nikkei, Hang Seng, Crude Oil, USD/INR, Gold, DXY
- **NSE Data**: India VIX, FII/DII flows, Put-Call Ratio, Advance/Decline
- **4 Instrument Cards**: Price, change%, score bar, confidence, top reasons, RSI/MACD/BB/Volume/EMA/Sentiment
- **Pipeline Activity**: Run log with duration, per-instrument scores, live countdown to next run
- **Signal History**: Score evolution over time
- **System Status**: Trading flags, DB health, connections

### Run Detail Page
- **Verdict strip**: SUCCESS/FAIL, timestamp, session, duration
- **Tabbed instruments**: Click to switch between Nifty/Gold/Silver/Banking
- **Score visualization**: Bipolar gradient bar + confidence bar
- **Prediction reasoning**: Weighted contribution bars per factor
- **Contextual indicators**: RSI→"Oversold", MACD→"Momentum↑", etc.
- **Collapsible raw data**: Global signals, sector signals, all ML features

---

## Data Flow

### Collection Cycle (every 2 minutes during market hours)

```
1. Collect global data (yfinance)              → 49 data points
2. Collect per-instrument technicals (yfinance) → RSI, MACD, BB, EMA, ATR
3. Collect news sentiment (RSS + VADER)         → 45+ headlines scored
4. Collect NSE data (FII/DII, VIX, PCR, A/D)   → 6 signals
5. Generate predictions (weighted factors)       → LONG/SHORT/FLAT + score
6. Persist to TimescaleDB                        → signals + predictions
7. Cache in Redis                                → latest prices + predictions
8. Broadcast via WebSocket                       → dashboard updates
```

### Market Hours Awareness

```
 8:00 AM  ─── Signal collection starts (US closed, data available)
 9:00 AM  ─── Pre-open session
 9:15 AM  ─── Market opens → 2-minute collection cycle
 2:45 PM  ─── Stop opening new positions
 3:15 PM  ─── Square-off zone (Zerodha MIS at 3:20)
 3:30 PM  ─── Market closes → EOD summary
 Weekends ─── Closed
 Holidays ─── Closed (2026 NSE calendar loaded)
```

---

## Database Schema

### TimescaleDB (port 5434) — Market Data

| Table | Purpose | Type |
|-------|---------|------|
| `ticks` | Raw tick data (future live feed) | Hypertable |
| `ohlcv_1m` | 1-minute candles | Continuous aggregate |
| `ohlcv_5m` | 5-minute candles | Continuous aggregate |
| `signal_snapshots` | All features per instrument per run | Hypertable |
| `predictions` | Direction, score, confidence per run | Hypertable |
| `pipeline_runs` | Run metadata (duration, status) | Hypertable |

### PostgreSQL (port 5435) — Trades

| Table | Purpose |
|-------|---------|
| `orders` | Order lifecycle (PENDING → FILLED) |
| `trades` | Executed fills |
| `positions` | Open/closed positions with P&L |
| `strategy_configs` | Strategy parameters |
| `daily_pnl` | Daily profit/loss summary |

### Redis (port 6380) — Hot Cache

| Key Pattern | TTL | Purpose |
|------------|-----|---------|
| `price:{instrument}` | 120s | Latest price + change |
| `pred:{instrument}` | 700s | Latest prediction |
| `pipeline:status` | 700s | Last run metadata |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Market session + server health |
| GET | `/api/predictions` | Latest predictions for all instruments |
| GET | `/api/instruments` | List tracked instruments |
| GET | `/api/history` | Signal history (last 100 snapshots) |
| GET | `/api/activity` | Pipeline run log |
| GET | `/api/run/{uuid}` | Full detail for a specific run |
| WS | `/ws` | Real-time updates (init + heartbeat + update) |

---

## Roadmap

- [x] Market data pipeline (Yahoo Finance + NSE India)
- [x] 3-layer signal collection (global → sector → instrument)
- [x] Weighted factor prediction engine
- [x] TimescaleDB persistence with Alembic migrations
- [x] WebSocket real-time dashboard
- [x] Pipeline run detail page with tabbed instruments
- [ ] Zerodha Kite Connect broker adapter
- [ ] LightGBM ML model trained on historical signals
- [ ] Paper trading mode (live signals, simulated orders)
- [ ] Backtesting engine (replay historical data)
- [ ] Telegram/email alerts on high-confidence signals
- [ ] Portfolio P&L tracking dashboard
- [ ] Multi-strategy support

---

## Contributing

This project is under active development. Contributions welcome — open an issue first to discuss.

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit with conventional commits (`feat:`, `fix:`, `docs:`, etc.)
4. Push and open a PR

---

## Disclaimer

This software is for educational and research purposes only. It does not constitute financial advice. Trading in financial markets involves substantial risk of loss. Past performance does not guarantee future results. Always do your own research before making investment decisions.

---

## License

MIT
