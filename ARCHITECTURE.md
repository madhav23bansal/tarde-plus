# Trade-Plus: Low-Latency Algorithmic Trading System Architecture

## Production-Ready Blueprint for Indian Markets (NSE/BSE)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Component Design](#4-component-design)
5. [Low Latency Techniques](#5-low-latency-techniques)
6. [Data Architecture](#6-data-architecture)
7. [Deployment & Infrastructure](#7-deployment--infrastructure)
8. [Monitoring & Observability](#8-monitoring--observability)
9. [SEBI Regulatory Compliance](#9-sebi-regulatory-compliance)
10. [Open Source Frameworks & References](#10-open-source-frameworks--references)
11. [Project Structure](#11-project-structure)
12. [Implementation Roadmap](#12-implementation-roadmap)

---

## 1. Executive Summary

This document defines a production-grade algorithmic trading system targeting Indian equity markets (NSE/BSE). The architecture prioritizes:

- **Tick-to-signal latency**: Target < 5ms for strategy evaluation
- **Signal-to-order latency**: Target < 10ms end-to-end (retail API constraint)
- **Zero data loss**: Guaranteed tick ingestion with no drops under load
- **Deterministic execution**: Same strategy code for backtest and live trading
- **SEBI compliance**: Full adherence to April 2026 retail algo trading regulations

### Latency Tier Classification

| Tier | Latency Target | Use Case | Architecture |
|------|---------------|----------|--------------|
| Ultra-Low (HFT) | < 10 us | Co-located, FPGA | C++/Rust, kernel bypass |
| Low | < 1 ms | Prop trading | Rust core, dedicated servers |
| **Medium (Our Target)** | **< 10 ms** | **Retail algo via broker APIs** | **Python + Rust hot paths** |
| Standard | < 100 ms | Swing/positional | Pure Python |

> **Reality check**: Retail traders in India are constrained by broker API latency (20-80ms round-trip for order placement). The goal is to minimize *our* processing overhead so the broker API is the only bottleneck.

---

## 2. System Architecture

### 2.1 Architecture Pattern: Modular Monolith with Event-Driven Core

**Why NOT microservices**: For a trading system, network hops between services add latency. A microservices architecture introduces 1-5ms per inter-service call. For trading, this is unacceptable on the hot path.

**Why NOT a pure monolith**: We need independent scaling of components like data ingestion (I/O bound) vs strategy computation (CPU bound), and independent deployment of non-critical services (logging, dashboards).

**The hybrid approach**:
- **Hot path** (monolith): Market data -> Strategy -> Risk -> OMS runs in a single process with in-memory message passing (zero network overhead)
- **Cold path** (separate services): Persistence, monitoring, alerting, dashboards run as independent services communicating via Redis Streams

```
                         HOT PATH (Single Process, < 5ms)
 ┌─────────────────────────────────────────────────────────────────┐
 │                                                                 │
 │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   │
 │  │ Market   │──>│ Strategy │──>│  Risk    │──>│  Order   │   │
 │  │ Data     │   │ Engine   │   │ Manager  │   │ Manager  │   │
 │  │ Handler  │   │          │   │          │   │ (OMS)    │   │
 │  └──────────┘   └──────────┘   └──────────┘   └──────────┘   │
 │       │              │              │              │            │
 │       └──────────────┴──────────────┴──────────────┘            │
 │                         │                                       │
 │                    MessageBus                                   │
 │                   (in-process)                                  │
 │                         │                                       │
 └─────────────────────────┼───────────────────────────────────────┘
                           │
                     Redis Streams
                     (async publish)
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     ┌────┴────┐    ┌─────┴─────┐   ┌─────┴──────┐
     │ Tick DB │    │ Trade DB  │   │ Monitoring │
     │ Writer  │    │ Writer    │   │ & Alerting │
     │(Timescale)   │(Postgres) │   │(Prometheus)│
     └─────────┘    └───────────┘   └────────────┘
```

### 2.2 Event-Driven Message Flow

Every component communicates via events. The in-process MessageBus uses a publish/subscribe pattern with zero serialization overhead (direct Python object passing).

```
Event Types:
  TickEvent        -> Market data update (LTP, bid/ask, volume)
  BarEvent         -> Aggregated OHLCV candle
  SignalEvent      -> Strategy generates buy/sell signal
  OrderEvent       -> Order created, sent to broker
  FillEvent        -> Order filled (partial or complete)
  PositionEvent    -> Position opened/modified/closed
  RiskEvent        -> Risk limit breached
  ErrorEvent       -> System error requiring attention

Flow:
  Broker WS -> TickEvent -> [Strategy subscribes] -> SignalEvent
            -> [Risk subscribes] -> OrderEvent (if approved)
            -> [OMS subscribes] -> HTTP to Broker API
            -> FillEvent -> [Position Tracker subscribes]
            -> PositionEvent -> [PnL Calculator subscribes]
```

### 2.3 Why This Design

| Decision | Rationale |
|----------|-----------|
| In-process MessageBus for hot path | Zero serialization, zero network hop, < 0.01ms |
| Redis Streams for cold path | Persistence, replay capability, decoupled consumers |
| Single-threaded event loop (asyncio) | Deterministic ordering, no lock contention |
| Rust extensions for compute | 10-100x speedup on indicator calculations |
| Separate I/O threads for WebSocket | Network I/O does not block strategy evaluation |

---

## 3. Technology Stack

### 3.1 Core Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| **Main Engine** | Python 3.12+ with asyncio | Rapid strategy development, rich ecosystem |
| **Hot Path Extensions** | Rust via PyO3/maturin | Memory-safe, zero-cost abstractions, no GC pauses |
| **In-Memory Cache** | Redis 7.x | Sub-ms latency, Streams, TimeSeries, Pub/Sub |
| **Time-Series DB** | TimescaleDB (PostgreSQL ext) | SQL compatibility, hypertables, continuous aggregates |
| **Trade/Order DB** | PostgreSQL 16 | ACID compliance, JSONB for flexible order metadata |
| **Message Broker** | Redis Streams | Lightweight, persistent, consumer groups, no Kafka overhead |
| **WebSocket Client** | websockets (Python) | Native asyncio, auto-reconnect, RFC 6455 compliant |
| **HTTP Client** | httpx (async) | Connection pooling, HTTP/2, async-native |
| **Task Scheduling** | APScheduler / asyncio tasks | Lightweight, in-process scheduling |

### 3.2 Why NOT Kafka

Kafka is overkill for a single-user retail trading system:
- Adds 2-5ms latency for produce/consume
- Requires ZooKeeper/KRaft, JVM, significant memory
- Redis Streams provides 90% of Kafka's features (persistence, consumer groups, replay) at a fraction of the operational cost
- Redis is already in the stack for caching

**When to upgrade to Kafka**: If you scale to multiple independent strategy processes across machines, or need guaranteed exactly-once semantics for multi-venue arbitrage.

### 3.3 Why ZeroMQ Is Not Primary

ZeroMQ offers the lowest latency (~33us) but lacks:
- Built-in persistence (messages lost if no subscriber)
- Consumer groups
- Stream replay for debugging

**Where to use ZeroMQ**: If you later need ultra-low-latency IPC between a Rust order gateway and the Python strategy engine on the same machine, ZeroMQ PUB/SUB or PUSH/PULL over IPC (Unix sockets) is the right choice.

### 3.4 Rust Extensions (PyO3)

Compile latency-critical computations to native code, callable from Python:

```
Rust Extensions (compiled via maturin):
  trade_plus_core/
    src/
      indicators.rs    -> RSI, MACD, Bollinger, VWAP (10-50x faster)
      orderbook.rs     -> L2 order book maintenance
      risk_calc.rs     -> Position sizing, margin calculations
      bar_builder.rs   -> Tick-to-OHLCV aggregation
      signal.rs        -> Signal scoring and ranking
```

**Performance impact**: Python RSI on 1000 bars ~ 0.5ms. Rust RSI on 1000 bars ~ 0.005ms. For a strategy evaluating 20 indicators on 200 instruments per tick, this is the difference between 200ms and 2ms.

---

## 4. Component Design

### 4.1 Market Data Handler

Responsible for WebSocket connection lifecycle, tick normalization, and distribution.

```
MarketDataHandler
  ├── WebSocketManager
  │     ├── connect() / reconnect() with exponential backoff + jitter
  │     ├── heartbeat monitoring (detect stale connections)
  │     ├── subscription management (re-subscribe on reconnect)
  │     └── binary frame parsing (broker-specific)
  │
  ├── TickNormalizer
  │     ├── Unified tick format across brokers
  │     ├── Timestamp normalization (exchange time vs local time)
  │     ├── Instrument token -> Symbol mapping
  │     └── Data validation (filter bad ticks, zero prices)
  │
  ├── BarAggregator
  │     ├── Time-based bars (1s, 5s, 1m, 5m, 15m, 1h)
  │     ├── Tick-based bars (every N ticks)
  │     ├── Volume-based bars (every N volume)
  │     └── OHLCV construction with __slots__ optimization
  │
  └── DataPublisher
        ├── Publish TickEvent to in-process MessageBus
        ├── Publish BarEvent on bar close
        └── Async publish to Redis Stream (for persistence)
```

**WebSocket Reconnection Strategy**:
```python
# Exponential backoff with jitter
# Attempt 1: wait 1s +/- 0.5s
# Attempt 2: wait 2s +/- 1.0s
# Attempt 3: wait 4s +/- 2.0s
# ...capped at 30s max wait
# On reconnect: re-subscribe to all instruments
# On persistent failure (>5min): alert via Telegram/email
```

**Key Design Decisions**:
- WebSocket runs in a dedicated thread (not on the main asyncio loop) to prevent network jitter from blocking strategy evaluation
- Tick normalization uses Rust extension for binary parsing of broker-specific formats
- Bar aggregator uses `__slots__` classes for ~40% memory reduction

### 4.2 Strategy Engine

```
StrategyEngine
  ├── StrategyRegistry
  │     ├── Register/deregister strategies at runtime
  │     ├── Strategy lifecycle (init -> warmup -> active -> paused -> stopped)
  │     └── Strategy isolation (one strategy crash does not affect others)
  │
  ├── IndicatorManager
  │     ├── Shared indicator cache (avoid recomputing RSI for multiple strategies)
  │     ├── Indicator dependency graph
  │     └── Rust-compiled indicator library
  │
  ├── SignalGenerator
  │     ├── Strategy.on_tick(tick) -> Optional[Signal]
  │     ├── Strategy.on_bar(bar) -> Optional[Signal]
  │     ├── Signal scoring and confidence weighting
  │     └── Signal deduplication (prevent duplicate orders)
  │
  └── BacktestAdapter
        ├── Same strategy code for backtest and live
        ├── Simulated fill model (slippage, partial fills)
        └── Deterministic event replay from TimescaleDB
```

**Strategy Interface**:
```python
class Strategy(ABC):
    def on_start(self) -> None: ...
    def on_tick(self, tick: TickEvent) -> None: ...
    def on_bar(self, bar: BarEvent) -> None: ...
    def on_fill(self, fill: FillEvent) -> None: ...
    def on_position(self, position: PositionEvent) -> None: ...
    def on_stop(self) -> None: ...

    # Helper methods
    def buy(self, instrument, qty, order_type, price=None) -> OrderId: ...
    def sell(self, instrument, qty, order_type, price=None) -> OrderId: ...
    def cancel(self, order_id) -> None: ...
    def get_position(self, instrument) -> Position: ...
    def get_indicator(self, name, instrument, params) -> Indicator: ...
```

### 4.3 Risk Management Module

Pre-trade and real-time risk checks that CANNOT be bypassed.

```
RiskManager
  ├── PreTradeChecks (synchronous, on every order)
  │     ├── Position size limit (max qty per instrument)
  │     ├── Order value limit (max notional per order)
  │     ├── Daily loss limit (stop trading if daily PnL < -X)
  │     ├── Max open positions (across all instruments)
  │     ├── Max orders per second (SEBI: < 10 OPS without registration)
  │     ├── Instrument-level exposure limit
  │     ├── Duplicate order detection (same instrument, same side, within Nms)
  │     └── Market hours validation
  │
  ├── RealTimeMonitoring
  │     ├── Portfolio margin utilization
  │     ├── Drawdown tracking (peak-to-trough)
  │     ├── Strategy-level PnL monitoring
  │     ├── Unusual activity detection (sudden spike in order rate)
  │     └── Circuit breaker (auto-halt if anomalous behavior)
  │
  └── KillSwitch
        ├── Manual emergency stop (cancel all orders, flatten positions)
        ├── Automatic trigger on risk breach
        ├── Telegram/SMS notification on activation
        └── Requires manual re-enable (no auto-restart after kill)
```

**Non-negotiable**: The RiskManager sits in the hot path between SignalEvent and OrderEvent. Every signal MUST pass through risk checks. There is no bypass mechanism.

### 4.4 Order Management System (OMS)

```
OrderManager
  ├── OrderFactory
  │     ├── Create order objects with unique IDs
  │     ├── Order types: MARKET, LIMIT, SL, SL-M, GTT
  │     ├── Pre-computed order templates (for speed)
  │     └── Instrument-specific lot size/tick size validation
  │
  ├── OrderRouter
  │     ├── Broker adapter interface (Zerodha, Fyers, AngelOne, Dhan)
  │     ├── Connection pool management (httpx persistent sessions)
  │     ├── Rate limiting (respect broker API limits)
  │     ├── Retry logic with idempotency keys
  │     └── Failover between primary/secondary broker
  │
  ├── OrderTracker
  │     ├── In-memory order state machine:
  │     │   PENDING -> SUBMITTED -> OPEN -> PARTIAL -> FILLED
  │     │                                -> CANCELLED
  │     │                                -> REJECTED
  │     ├── Reconciliation with broker order book (periodic)
  │     └── Stale order detection and alerting
  │
  └── FillProcessor
        ├── Match fills to orders
        ├── Handle partial fills
        ├── Update position tracker
        └── Emit FillEvent
```

**Connection Pooling** (critical for latency):
```python
# Without pooling: 250-300ms per order (TCP+TLS handshake each time)
# With pooling:     75-90ms per order (reuse existing connection)
# Improvement:      ~70% latency reduction

# Implementation:
broker_client = httpx.AsyncClient(
    base_url="https://api.broker.com",
    limits=httpx.Limits(
        max_keepalive_connections=5,
        max_connections=20
    ),
    timeout=httpx.Timeout(10.0, connect=5.0),
    http2=True  # multiplexing reduces head-of-line blocking
)
```

### 4.5 Position Tracker

```
PositionTracker
  ├── Real-time position state per instrument
  │     ├── quantity (long positive, short negative)
  │     ├── average_price
  │     ├── unrealized_pnl (updated on every tick)
  │     ├── realized_pnl (updated on fills)
  │     └── margin_used
  │
  ├── Position reconciliation
  │     ├── Compare local state with broker positions (every 60s)
  │     ├── Alert on mismatch
  │     └── Auto-correct from broker as source of truth
  │
  └── EOD Processing
        ├── Flatten all intraday positions before market close
        ├── Generate daily position report
        └── Archive to PostgreSQL
```

### 4.6 PnL Calculator

```
PnLCalculator
  ├── Real-time PnL (per tick update)
  │     ├── Unrealized PnL = (current_price - avg_price) * quantity
  │     ├── Realized PnL = sum of closed trade profits
  │     ├── Total PnL = Realized + Unrealized
  │     ├── Per-strategy PnL attribution
  │     └── Account-level PnL with charges (brokerage, STT, GST, etc.)
  │
  ├── Performance Metrics
  │     ├── Sharpe ratio (rolling)
  │     ├── Max drawdown (current session)
  │     ├── Win rate
  │     ├── Average win/loss ratio
  │     └── Profit factor
  │
  └── Charge Calculator (India-specific)
        ├── Brokerage (flat or percentage based on broker)
        ├── STT (Securities Transaction Tax)
        ├── Exchange transaction charges
        ├── GST (18% on brokerage + transaction charges)
        ├── SEBI turnover fees
        └── Stamp duty
```

### 4.7 Logging & Alerting

```
LoggingSystem
  ├── Structured logging (JSON format)
  │     ├── Every tick processed (debug level)
  │     ├── Every signal generated (info level)
  │     ├── Every order placed/filled (info level)
  │     ├── Every risk check result (debug/warn level)
  │     └── All errors with full context (error level)
  │
  ├── Performance logging
  │     ├── Tick-to-signal latency per event
  │     ├── Signal-to-order latency per event
  │     ├── Order-to-fill latency per event
  │     └── Component processing time histograms
  │
  └── Alert channels
        ├── Telegram bot (primary - real-time alerts)
        ├── Email (daily summary, critical errors)
        ├── Grafana alerts (metric-based thresholds)
        └── Sound alert on local machine (for monitored sessions)

Alert Triggers:
  - CRITICAL: Kill switch activated
  - CRITICAL: WebSocket disconnected > 30s during market hours
  - HIGH: Daily loss limit > 80% utilized
  - HIGH: Order rejected by broker
  - MEDIUM: Position reconciliation mismatch
  - LOW: Strategy warmup complete
```

---

## 5. Low Latency Techniques

### 5.1 Application-Level Optimizations

| Technique | Impact | Implementation |
|-----------|--------|----------------|
| **Connection pooling** | 70% reduction in order latency | httpx.AsyncClient with persistent connections |
| **Order pre-computation** | Eliminate serialization on hot path | Pre-build order payloads, fill in price at signal time |
| **`__slots__` on data classes** | 40% memory reduction, faster attribute access | All tick, bar, order, position objects |
| **Rust indicator extensions** | 10-100x speedup on computations | PyO3 bindings for RSI, MACD, VWAP, etc. |
| **NumPy pre-allocated arrays** | Eliminate runtime allocation | Ring buffers for price history |
| **Redis pipelining** | 1 round-trip instead of N | Batch all Redis writes per tick cycle |
| **Avoid Python GIL contention** | Predictable latency | Single-threaded asyncio, offload to Rust |
| **Local indicator cache** | Avoid redundant Redis queries | In-memory dict with TTL |

### 5.2 Network-Level Optimizations

| Technique | Impact | When to Use |
|-----------|--------|-------------|
| **TCP_NODELAY** | Disable Nagle's algorithm, send immediately | Always for trading connections |
| **HTTP/2 multiplexing** | Multiple requests over single connection | Broker API calls |
| **WebSocket binary frames** | Smaller payloads than JSON text | If broker supports it |
| **DNS caching** | Avoid DNS lookup on every request | Cache broker API DNS resolution |
| **Keep-alive tuning** | Prevent connection drops during idle periods | Set aggressive keep-alive intervals |

### 5.3 OS-Level Optimizations (Advanced)

| Technique | Impact | Complexity |
|-----------|--------|------------|
| **CPU pinning (taskset)** | Dedicate cores to trading process | Low |
| **Process priority (nice -20)** | OS scheduler priority | Low |
| **Huge pages** | Reduce TLB misses | Medium |
| **IRQ affinity** | Steer network interrupts to specific cores | Medium |
| **Kernel bypass (DPDK/AF_XDP)** | Eliminate kernel networking overhead (20-50us) | High - only for co-located setups |

> **Practical note**: For retail API trading, application and network optimizations give 90% of the benefit. OS and kernel-level optimizations matter only for co-located direct market access (DMA) setups, which are not available to retail traders in India.

### 5.4 Co-location for Indian Markets (NSE)

**NSE Co-location Facility** (Airoli, Navi Mumbai):
- Available rack types: Full 42U (6KVA), Half 21U (3.5KVA), Quarter 9U (1.75KVA)
- Network latency to matching engine: < 50 microseconds
- Only available to registered members/brokers, NOT retail traders
- Cost: Significant (lakhs per month)

**Practical alternatives for retail**:
1. **Dedicated server in Mumbai** (CtrlS, Netmagic, Tata Communications): ~2-5ms to broker API servers
2. **AWS Mumbai (ap-south-1)**: ~5-15ms to broker APIs
3. **VPS near broker data center**: Research where your broker's servers are hosted
4. **Home setup with low-latency ISP**: Acceptable for strategies with > 100ms holding period

**Recommendation**: Start with AWS Mumbai (ap-south-1) or a Mumbai-based VPS. Only invest in co-location if your strategy's edge is time-sensitive at the sub-millisecond level AND you have direct market access through a broker.

---

## 6. Data Architecture

### 6.1 Data Flow and Storage Tiers

```
Tier 1: HOT (In-Memory, < 1ms access)
  ├── Redis
  │     ├── Latest tick per instrument (STRING/JSON)
  │     ├── Current OHLCV bars (TimeSeries)
  │     ├── Order book snapshots (HASH)
  │     ├── Active orders (HASH)
  │     ├── Current positions (HASH)
  │     └── Strategy state (JSON)
  │
  └── Python process memory
        ├── Indicator buffers (NumPy arrays)
        ├── Recent tick history (ring buffer, last 1000 ticks)
        └── Order templates (pre-computed)

Tier 2: WARM (Disk-backed, < 50ms access)
  ├── TimescaleDB
  │     ├── Tick data (hypertable, compressed, partitioned by day)
  │     ├── OHLCV bars (continuous aggregates)
  │     └── Order book snapshots (sampled)
  │
  └── PostgreSQL
        ├── Orders (full lifecycle)
        ├── Trades (fills)
        ├── Positions (historical)
        └── Strategy configurations

Tier 3: COLD (Archive, seconds-minutes access)
  └── Object storage (S3/MinIO)
        ├── Historical tick data (Parquet format)
        ├── Backtest results
        └── Audit logs (SEBI: 5-year retention)
```

### 6.2 TimescaleDB Schema (Tick Data)

```sql
-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Tick data hypertable
CREATE TABLE ticks (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,
    ltp         DECIMAL(12,2) NOT NULL,
    bid         DECIMAL(12,2),
    ask         DECIMAL(12,2),
    volume      BIGINT,
    oi          BIGINT,        -- open interest (for F&O)
    exchange    TEXT NOT NULL DEFAULT 'NSE'
);

SELECT create_hypertable('ticks', 'time',
    chunk_time_interval => INTERVAL '1 day'
);

-- Compression policy (compress after 3 days)
ALTER TABLE ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('ticks', INTERVAL '3 days');

-- Continuous aggregate for 1-minute OHLCV
CREATE MATERIALIZED VIEW ohlcv_1m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    instrument,
    FIRST(ltp, time) AS open,
    MAX(ltp) AS high,
    MIN(ltp) AS low,
    LAST(ltp, time) AS close,
    SUM(volume) AS volume
FROM ticks
GROUP BY bucket, instrument;

-- Refresh policy
SELECT add_continuous_aggregate_policy('ohlcv_1m',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute'
);

-- Retention policy (keep raw ticks for 30 days)
SELECT add_retention_policy('ticks', INTERVAL '30 days');
```

### 6.3 PostgreSQL Schema (Orders & Trades)

```sql
-- Orders table
CREATE TABLE orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id     TEXT NOT NULL,
    instrument      TEXT NOT NULL,
    exchange        TEXT NOT NULL DEFAULT 'NSE',
    side            TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type      TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT', 'SL', 'SL-M')),
    quantity        INTEGER NOT NULL,
    price           DECIMAL(12,2),
    trigger_price   DECIMAL(12,2),
    status          TEXT NOT NULL DEFAULT 'PENDING',
    broker_order_id TEXT,
    algo_id         TEXT,          -- SEBI-mandated unique algo identifier
    placed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filled_at       TIMESTAMPTZ,
    avg_fill_price  DECIMAL(12,2),
    filled_qty      INTEGER DEFAULT 0,
    rejection_reason TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_strategy ON orders(strategy_id, placed_at DESC);
CREATE INDEX idx_orders_instrument ON orders(instrument, placed_at DESC);
CREATE INDEX idx_orders_status ON orders(status) WHERE status IN ('PENDING', 'OPEN', 'PARTIAL');

-- Trades table (filled orders)
CREATE TABLE trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID REFERENCES orders(id),
    strategy_id     TEXT NOT NULL,
    instrument      TEXT NOT NULL,
    side            TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    price           DECIMAL(12,2) NOT NULL,
    charges         JSONB DEFAULT '{}',  -- brokerage, STT, GST breakdown
    pnl             DECIMAL(12,2),
    traded_at       TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Daily PnL summary
CREATE TABLE daily_pnl (
    date            DATE NOT NULL,
    strategy_id     TEXT NOT NULL,
    realized_pnl    DECIMAL(12,2) NOT NULL DEFAULT 0,
    unrealized_pnl  DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_charges   DECIMAL(12,2) NOT NULL DEFAULT 0,
    net_pnl         DECIMAL(12,2) NOT NULL DEFAULT 0,
    num_trades      INTEGER NOT NULL DEFAULT 0,
    win_trades      INTEGER NOT NULL DEFAULT 0,
    loss_trades     INTEGER NOT NULL DEFAULT 0,
    max_drawdown    DECIMAL(12,2) DEFAULT 0,
    PRIMARY KEY (date, strategy_id)
);
```

### 6.4 Redis Key Structure

```
# Latest tick data
tick:{instrument}              -> JSON {ltp, bid, ask, vol, ts}

# Current positions
position:{instrument}          -> HASH {qty, avg_price, pnl, ...}

# Active orders
order:{order_id}               -> HASH {status, instrument, qty, ...}
orders:active                  -> SET of active order IDs

# Strategy state
strategy:{strategy_id}:state   -> JSON {status, last_signal, ...}

# Bar data (Redis TimeSeries)
bar:{instrument}:1m:open       -> TimeSeries
bar:{instrument}:1m:high       -> TimeSeries
bar:{instrument}:1m:low        -> TimeSeries
bar:{instrument}:1m:close      -> TimeSeries
bar:{instrument}:1m:volume     -> TimeSeries

# Event streams (Redis Streams)
stream:ticks                   -> Stream of all ticks
stream:signals                 -> Stream of strategy signals
stream:orders                  -> Stream of order events
stream:fills                   -> Stream of fill events

# System metrics
metrics:latency:tick_to_signal -> TimeSeries (for monitoring)
metrics:latency:order_rtt      -> TimeSeries
```

---

## 7. Deployment & Infrastructure

### 7.1 Infrastructure Recommendations

**For development and testing**:
```
Local machine or any cloud VM
  - Docker Compose for all services
  - Paper trading with broker sandbox APIs
```

**For production (retail algo trading)**:
```
Option A: AWS Mumbai (ap-south-1) - RECOMMENDED for starting
  - EC2 c6i.xlarge (4 vCPU, 8GB RAM) for trading engine
  - ElastiCache Redis (cache.r6g.large)
  - RDS PostgreSQL + TimescaleDB (db.r6g.large)
  - Estimated cost: ~15,000-25,000 INR/month

Option B: Dedicated Server in Mumbai
  - Bare metal from CtrlS/Netmagic/Web Werks
  - Lower, more consistent latency than cloud
  - Better for latency-sensitive strategies
  - Estimated cost: ~20,000-50,000 INR/month

Option C: Mumbai VPS (Budget)
  - DigitalOcean/Hetzner Mumbai
  - 4 vCPU, 8GB RAM, SSD
  - Run all services on single machine
  - Estimated cost: ~5,000-10,000 INR/month
```

### 7.2 Docker Compose (Development & Small Production)

```yaml
# docker-compose.yml
version: '3.8'

services:
  # --- Core Trading Engine ---
  trading-engine:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URL=postgresql://trade:secret@postgres:5432/tradeplus
      - TIMESCALE_URL=postgresql://trade:secret@timescaledb:5432/marketdata
      - BROKER=zerodha  # or fyers, angelone, dhan
      - TRADING_MODE=paper  # paper or live
      - LOG_LEVEL=INFO
    volumes:
      - ./strategies:/app/strategies
      - ./config:/app/config
      - ./logs:/app/logs
    depends_on:
      - redis
      - postgres
      - timescaledb
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G

  # --- Redis (Cache + Streams + TimeSeries) ---
  redis:
    image: redis/redis-stack:latest
    ports:
      - "6379:6379"
      - "8001:8001"  # RedisInsight UI
    volumes:
      - redis-data:/data
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
    deploy:
      resources:
        limits:
          memory: 2G

  # --- TimescaleDB (Tick Data) ---
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    environment:
      - POSTGRES_USER=trade
      - POSTGRES_PASSWORD=secret
      - POSTGRES_DB=marketdata
    ports:
      - "5433:5432"
    volumes:
      - timescale-data:/var/lib/postgresql/data
      - ./sql/timescale-init.sql:/docker-entrypoint-initdb.d/init.sql
    deploy:
      resources:
        limits:
          memory: 2G

  # --- PostgreSQL (Orders & Trades) ---
  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=trade
      - POSTGRES_PASSWORD=secret
      - POSTGRES_DB=tradeplus
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./sql/postgres-init.sql:/docker-entrypoint-initdb.d/init.sql
    deploy:
      resources:
        limits:
          memory: 1G

  # --- Monitoring: Prometheus ---
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus

  # --- Monitoring: Grafana ---
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    depends_on:
      - prometheus

volumes:
  redis-data:
  timescale-data:
  postgres-data:
  prometheus-data:
  grafana-data:
```

### 7.3 Grafana Dashboards

Design the following dashboards:

**1. Trading Dashboard**:
- Real-time PnL (per strategy and total)
- Open positions with unrealized PnL
- Order fill rate and rejection rate
- Win/loss ratio (rolling)

**2. System Performance Dashboard**:
- Tick-to-signal latency (P50, P95, P99)
- Signal-to-order latency
- Order-to-fill latency
- Ticks processed per second
- WebSocket connection status
- Redis memory usage and command latency

**3. Risk Dashboard**:
- Daily loss limit utilization (%)
- Max drawdown (intraday)
- Position exposure by instrument
- Order rate (orders/second)
- Kill switch status

**Prometheus Metrics to Export**:
```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
ticks_processed = Counter('ticks_processed_total', 'Total ticks processed', ['instrument'])
orders_placed = Counter('orders_placed_total', 'Total orders placed', ['strategy', 'side'])
orders_filled = Counter('orders_filled_total', 'Total orders filled', ['strategy'])
orders_rejected = Counter('orders_rejected_total', 'Total orders rejected', ['reason'])

# Histograms (latency)
tick_to_signal_latency = Histogram('tick_to_signal_seconds', 'Tick to signal latency',
    buckets=[0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1])
order_placement_latency = Histogram('order_placement_seconds', 'Order API call latency',
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0])

# Gauges
active_positions = Gauge('active_positions', 'Number of open positions')
daily_pnl = Gauge('daily_pnl_inr', 'Daily PnL in INR', ['strategy'])
websocket_connected = Gauge('websocket_connected', 'WebSocket connection status')
```

---

## 8. Monitoring & Observability

### 8.1 Three Pillars

```
1. METRICS (Prometheus + Grafana)
   - Latency histograms at every stage
   - Throughput counters
   - Resource utilization gauges
   - Business metrics (PnL, trades, positions)

2. LOGS (Structured JSON -> file + optional ELK)
   - Every event with correlation ID
   - Latency measurements inline
   - Strategy decisions with reasoning
   - Error context and stack traces

3. TRACES (optional, for debugging)
   - End-to-end request tracing
   - Tick -> Signal -> Order -> Fill chain
   - Useful for debugging latency spikes
```

### 8.2 Health Checks

```python
# Health check endpoint (FastAPI)
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "websocket": ws_manager.is_connected,
        "redis": await redis.ping(),
        "postgres": await pg_pool.fetchval("SELECT 1"),
        "market_hours": is_market_open(),
        "last_tick_age_ms": time_since_last_tick(),
        "active_strategies": strategy_engine.active_count,
        "uptime_seconds": get_uptime()
    }
```

---

## 9. SEBI Regulatory Compliance

### 9.1 Timeline (as of March 2026)

| Date | Requirement | Status |
|------|-------------|--------|
| Oct 31, 2025 | Brokers register minimum one retail algo | DONE |
| Nov 30, 2025 | All retail algo products registered with exchanges | DONE |
| Jan 3, 2026 | Mock trading sessions completed | DONE |
| Jan 5, 2026 | Non-compliant brokers barred from new API clients | ACTIVE |
| **Apr 1, 2026** | **Full enforcement - all existing users must comply** | **UPCOMING** |

### 9.2 Compliance Requirements for This System

| Requirement | Implementation |
|-------------|----------------|
| **Unique Algo-ID per strategy** | Every order includes the exchange-assigned `algo_id` field |
| **< 10 OPS without registration** | RiskManager enforces rate limit; configurable threshold |
| **Static IP whitelisting** | Deploy on fixed-IP server; register IP with broker |
| **OAuth 2.0 authentication** | Use broker SDK's OAuth flow; auto-refresh tokens |
| **Two-Factor Authentication** | Implement TOTP-based 2FA for API session initialization |
| **Auto session logout** | Mandatory logout before next market pre-open |
| **5-year audit trail** | All API activity logged to PostgreSQL + S3 archive |
| **Broker as Principal** | Route all orders through registered broker (never direct to exchange) |
| **SEBI RA license for black-box** | Only needed if selling algo strategies commercially |

### 9.3 Order Rate Limiting

```python
class OrderRateLimiter:
    """
    SEBI mandates: orders exceeding 10 per second per exchange per client
    require mandatory algo registration.

    For unregistered retail algos, we MUST stay below 10 OPS.
    """
    def __init__(self, max_ops: int = 8):  # conservative: 8 instead of 10
        self.max_ops = max_ops
        self.window = deque()  # timestamps of orders in last 1 second

    def can_place_order(self) -> bool:
        now = time.monotonic()
        # Remove orders older than 1 second
        while self.window and now - self.window[0] > 1.0:
            self.window.popleft()
        return len(self.window) < self.max_ops

    def record_order(self):
        self.window.append(time.monotonic())
```

---

## 10. Open Source Frameworks & References

### 10.1 Production-Grade Frameworks

| Framework | Language | Stars | Strengths | Best For |
|-----------|----------|-------|-----------|----------|
| **NautilusTrader** | Rust + Python | 3.5k+ | Deterministic, production-grade, multi-venue | Serious production systems |
| **Backtrader** | Python | 13k+ | Mature, extensive documentation, live trading | Learning and prototyping |
| **Zipline-reloaded** | Python | Community fork | Event-driven, Quantopian heritage | Research and backtesting |
| **VectorBT** | Python | 4k+ | Vectorized backtesting, very fast | Rapid strategy research |
| **FreqTrade** | Python | 30k+ | Crypto-focused, excellent bot framework | Crypto algo trading |
| **vnpy** | Python | 25k+ | Chinese markets, comprehensive | Asian market trading |
| **QSTrader** | Python | 3k+ | Clean architecture, event-driven | Educational, equities |
| **Lean (QuantConnect)** | C# + Python | 9k+ | Institutional-grade, cloud platform | Multi-asset backtesting |

### 10.2 Recommended Study Repositories

- **NautilusTrader** (https://github.com/nautechsystems/nautilus_trader) - The gold standard for Rust+Python trading architecture. Study its MessageBus, event system, and adapter pattern.
- **awesome-systematic-trading** (https://github.com/wangzhe3224/awesome-systematic-trading) - Curated list of trading resources, libraries, and papers.
- **pytrade.org** (https://github.com/PFund-Software-Ltd/pytrade.org) - Comprehensive directory of Python trading libraries.

### 10.3 Indian Broker Python SDKs

| Broker | SDK | WebSocket | Cost | Notes |
|--------|-----|-----------|------|-------|
| **Zerodha** | pykiteconnect | Yes (binary) | Rs 500/month | Most mature, widely used |
| **Fyers** | fyers-apiv3 | Yes | Free | Good latency, free API |
| **Angel One** | smartapi-python | Yes | Free | Easy onboarding, free |
| **Dhan** | dhanhq | Yes | Free | Modern API, good for options |
| **Upstox** | upstox-python | Yes | Free/Paid tiers | High-speed APIs |

---

## 11. Project Structure

```
trade-plus/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml                # Python project config (uv/poetry)
├── Cargo.toml                    # Rust workspace root
├── config/
│   ├── default.toml              # Default configuration
│   ├── production.toml           # Production overrides
│   └── strategies/               # Strategy-specific configs
│       └── mean_reversion.toml
│
├── trade_plus_core/              # Rust extensions (PyO3)
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── indicators.rs         # RSI, MACD, Bollinger, VWAP
│       ├── bar_builder.rs        # Tick -> OHLCV aggregation
│       ├── risk_calc.rs          # Position sizing, margin
│       └── orderbook.rs          # L2 order book
│
├── trade_plus/                   # Main Python package
│   ├── __init__.py
│   ├── main.py                   # Application entry point
│   │
│   ├── core/                     # Core engine components
│   │   ├── __init__.py
│   │   ├── engine.py             # Main trading engine (NautilusKernel-inspired)
│   │   ├── message_bus.py        # In-process pub/sub message bus
│   │   ├── event.py              # Event types (TickEvent, SignalEvent, etc.)
│   │   ├── clock.py              # System/simulated clock
│   │   └── config.py             # Configuration management
│   │
│   ├── data/                     # Market data handling
│   │   ├── __init__.py
│   │   ├── handler.py            # MarketDataHandler
│   │   ├── websocket.py          # WebSocket manager with reconnection
│   │   ├── normalizer.py         # Tick normalization
│   │   ├── bar_aggregator.py     # OHLCV bar construction
│   │   └── replay.py             # Historical data replay (for backtest)
│   │
│   ├── strategy/                 # Strategy engine
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract Strategy class
│   │   ├── engine.py             # Strategy engine / registry
│   │   ├── indicator.py          # Indicator manager (wraps Rust)
│   │   └── examples/
│   │       ├── mean_reversion.py
│   │       ├── momentum.py
│   │       └── pairs_trading.py
│   │
│   ├── risk/                     # Risk management
│   │   ├── __init__.py
│   │   ├── manager.py            # RiskManager (pre-trade checks)
│   │   ├── limits.py             # Risk limit definitions
│   │   ├── kill_switch.py        # Emergency stop
│   │   └── rate_limiter.py       # SEBI OPS compliance
│   │
│   ├── execution/                # Order management
│   │   ├── __init__.py
│   │   ├── oms.py                # Order Management System
│   │   ├── order.py              # Order model and state machine
│   │   ├── fill.py               # Fill processing
│   │   └── reconciler.py         # Position reconciliation
│   │
│   ├── portfolio/                # Position and PnL
│   │   ├── __init__.py
│   │   ├── position.py           # Position tracker
│   │   ├── pnl.py                # PnL calculator
│   │   └── charges.py            # Indian market charge calculator
│   │
│   ├── adapters/                 # Broker adapters (ports & adapters)
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract broker adapter
│   │   ├── zerodha/
│   │   │   ├── __init__.py
│   │   │   ├── client.py         # Kite Connect wrapper
│   │   │   ├── websocket.py      # Kite WebSocket
│   │   │   └── mapper.py         # Map Kite responses to domain objects
│   │   ├── fyers/
│   │   │   └── ...
│   │   ├── angelone/
│   │   │   └── ...
│   │   └── paper/                # Paper trading adapter
│   │       ├── __init__.py
│   │       ├── client.py         # Simulated fills
│   │       └── data_feed.py      # Historical data replay
│   │
│   ├── persistence/              # Database layer
│   │   ├── __init__.py
│   │   ├── redis_store.py        # Redis operations
│   │   ├── timescale.py          # TimescaleDB tick writer
│   │   ├── postgres.py           # PostgreSQL order/trade writer
│   │   └── models.py             # SQLAlchemy/raw SQL models
│   │
│   ├── monitoring/               # Observability
│   │   ├── __init__.py
│   │   ├── metrics.py            # Prometheus metrics
│   │   ├── health.py             # Health check endpoint
│   │   └── alerts.py             # Telegram/email alerting
│   │
│   └── utils/                    # Shared utilities
│       ├── __init__.py
│       ├── time.py               # Time utilities (IST, exchange hours)
│       ├── instrument.py         # Instrument registry (NSE tokens)
│       └── logging.py            # Structured logging setup
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── backtest/
│
├── strategies/                   # User strategy configs (mounted volume)
├── sql/
│   ├── timescale-init.sql
│   └── postgres-init.sql
├── monitoring/
│   ├── prometheus.yml
│   └── grafana/
│       ├── dashboards/
│       └── datasources/
└── scripts/
    ├── setup.sh                  # Initial setup
    ├── download_instruments.py   # Download NSE instrument master
    └── backtest.py               # Run backtest from CLI
```

---

## 12. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-3)
- [ ] Project setup (pyproject.toml, Docker Compose, CI)
- [ ] Core event system (MessageBus, Event types)
- [ ] Market data handler with one broker adapter (Zerodha or Fyers)
- [ ] WebSocket connection with reconnection logic
- [ ] Tick normalization and bar aggregation
- [ ] Redis integration (tick caching, streams)
- [ ] Basic structured logging

### Phase 2: Strategy Engine (Weeks 4-6)
- [ ] Strategy base class and engine
- [ ] Indicator library (Python first, Rust later)
- [ ] One reference strategy (mean reversion)
- [ ] Paper trading adapter with simulated fills
- [ ] TimescaleDB tick persistence
- [ ] Basic backtest framework (replay historical data)

### Phase 3: Execution (Weeks 7-9)
- [ ] Order Management System (OMS)
- [ ] Risk management module (all pre-trade checks)
- [ ] Position tracker with reconciliation
- [ ] PnL calculator with Indian charges
- [ ] Order rate limiter (SEBI compliance)
- [ ] Kill switch (manual and automatic)

### Phase 4: Production Hardening (Weeks 10-12)
- [ ] Prometheus metrics + Grafana dashboards
- [ ] Telegram alerting integration
- [ ] Health check endpoint
- [ ] PostgreSQL order/trade persistence
- [ ] Connection pooling optimization
- [ ] Error handling and recovery testing
- [ ] SEBI algo-ID integration

### Phase 5: Performance (Weeks 13-16)
- [ ] Rust extensions for indicators (PyO3)
- [ ] Pre-allocated NumPy buffers
- [ ] Redis pipelining optimization
- [ ] Latency profiling and optimization
- [ ] Load testing (simulate high tick rates)
- [ ] Second broker adapter

### Phase 6: Advanced (Ongoing)
- [ ] Multiple strategy support
- [ ] Options strategy support (Greeks calculation)
- [ ] Advanced order types (bracket, cover, GTT)
- [ ] Multi-timeframe analysis
- [ ] ML signal integration
- [ ] Additional broker adapters

---

## Key Architecture Principles

1. **Hot path is sacred**: Never add anything to the tick->signal->order path that is not strictly necessary. No logging, no persistence, no network calls on the hot path. Use async fire-and-forget for cold path operations.

2. **Fail fast, fail loud**: Crash on data corruption rather than trading on bad data. A system that silently produces wrong numbers is worse than a system that stops.

3. **Broker API is the bottleneck**: For retail trading in India, the broker HTTP API call (20-80ms) dominates total latency. Optimize everything else, but accept this constraint.

4. **Same code, two modes**: Strategy code must work identically in backtest and live mode. The only difference is the data source and execution adapter.

5. **Defense in depth for risk**: Risk checks at strategy level, risk manager level, and broker level. The kill switch is the last line of defense.

6. **Compliance by design**: SEBI requirements (algo-ID, rate limiting, audit trail, static IP) are built into the architecture, not bolted on.

---

## References & Sources

### Architecture & Design
- [NautilusTrader Architecture](https://nautilustrader.io/docs/latest/concepts/architecture/)
- [Trading System Architecture 2026 - Tuvoc](https://www.tuvoc.com/blog/trading-system-architecture-microservices-agentic-mesh/)
- [Event-Driven Architecture vs Microservices](https://www.index.dev/blog/event-driven-architecture-vs-microservices)
- [Automated Trading Systems Design - QuantInsti](https://www.quantinsti.com/articles/automated-trading-system/)

### Low Latency
- [HFT Architecture: Kernel Bypass, DPDK](https://systemdr.substack.com/p/high-frequency-trading-architecture)
- [Low Latency Trading Systems 2026 - Tuvoc](https://www.tuvoc.com/blog/low-latency-trading-systems-guide/)
- [HTTP Connection Pooling for Trading APIs](https://www.marketcalls.in/python/slashing-api-order-latency-upto-70-with-http-connection-pooling.html)
- [Kernel Bypass in HFT - QuantVPS](https://www.quantvps.com/blog/kernel-bypass-in-hft)
- [Python in HFT: Low-Latency Techniques](https://www.pyquantnews.com/free-python-resources/python-in-high-frequency-trading-low-latency-techniques)

### Technology Stack
- [Redis for Real-Time Trading](https://redis.io/blog/real-time-trading-platform-with-redis-enterprise/)
- [Building HFT with Redis + InfluxDB](https://vardhmanandroid2015.medium.com/building-a-high-frequency-trading-system-with-hybrid-strategy-redis-influxdb-from-10ms-to-85716febefcb)
- [TimescaleDB vs InfluxDB Comparison](https://www.timescale.com/blog/timescaledb-vs-influxdb-for-time-series-data-timescale-influx-sql-nosql-36489299877)
- [Redis vs Kafka Comparison](https://double.cloud/blog/posts/2024/02/redis-vs-kafka/)
- [Choosing Messaging: Redis Streams vs Kafka](https://redis.io/blog/what-to-choose-for-your-synchronous-and-asynchronous-communication-needs-redis-streams-redis-pub-sub-kafka-etc-best-approaches-synchronous-asynchronous-communication/)
- [Rust vs C++ for Trading - Databento](https://databento.com/blog/rust-vs-cpp)
- [Rust in HFT Systems](https://dasroot.net/posts/2026/02/rust-high-frequency-trading-systems/)

### Indian Market Specific
- [SEBI Algo Trading Regulations - Official Circular](https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html)
- [SEBI Algo Trading Rules April 2026 - Fintrens](https://blogs.fintrens.com/sebi-algo-trading-rules-april-2026-what-every-retail-trader-in-india-must-know-before-the-deadline/)
- [SEBI Algo Trading Rules - AlgoBulls](https://algobulls.com/blog/industry-insights-and-updates/sebi-new-algotrading-regulations-for-retail-investors-2026)
- [NSE Co-location Facility](https://www.nseindia.com/static/trade/platform-services-co-location-facility)
- [Best Brokers for Algo Trading India 2026](https://algotest.in/blog/best-brokers-for-algo-trading-in-india/)
- [Static IP for Algo Trading India](https://www.myalgomate.com/static-ip-for-algo-trading-india/)

### Frameworks & Tools
- [NautilusTrader - GitHub](https://github.com/nautechsystems/nautilus_trader)
- [Backtrader](https://www.wrighters.io/backtrader-a-python-backtesting-and-trading-framework/)
- [awesome-systematic-trading - GitHub](https://github.com/wangzhe3224/awesome-systematic-trading)
- [pytrade.org - Python Trading Libraries](https://github.com/PFund-Software-Ltd/pytrade.org)
- [Top 21 Python Trading Tools](https://analyzingalpha.com/python-trading-tools)
- [Zerodha Kite Connect API](https://kite.trade/docs/connect/v3/)
- [pykiteconnect - GitHub](https://github.com/zerodha/pykiteconnect)

### Monitoring & Deployment
- [Docker Monitoring with Prometheus & Grafana](https://github.com/stefanprodan/dockprom)
- [Tick-to-Trade on AWS](https://aws.amazon.com/blogs/web3/optimize-tick-to-trade-latency-for-digital-assets-exchanges-and-trading-platforms-on-aws/)
