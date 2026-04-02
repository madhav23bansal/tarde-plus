"""FastAPI + WebSocket server for live market predictions.

REST endpoints for initial data load, WebSocket for real-time pushes.
Background loop collects signals and broadcasts to all connected clients.
"""

from __future__ import annotations

# Load .env before any config reads
from pathlib import Path as _Path
_env_file = _Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)

logger = structlog.get_logger()

from trade_plus.core.config import AppConfig
from trade_plus.data.redis_store import RedisStore
from trade_plus.data.timescale_store import TimescaleStore
from trade_plus.instruments import ALL_INSTRUMENTS, Direction
from trade_plus.market_data.market_hours import (
    MarketSession,
    can_open_new_position,
    get_session,
    market_status_summary,
    now_ist,
    should_squareoff,
)
from trade_plus.market_data.signal_collector import SignalCollector
from trade_plus.prediction import BiasPredictor
from trade_plus.trading.paper_trader import PaperTrader
from trade_plus.trading.intraday import IntradayTrader
from trade_plus.trading.fyers_feed import get_fyers_feed

# ── Config + DB connections ───────────────────────────────────────

_config = AppConfig()
_redis = RedisStore(_config.redis)
_tsdb = TimescaleStore(_config.timescale)

# ── Shared state (in-memory for WS broadcast speed) ──────────────

_state = {
    "last_snapshot": None,
    "last_predictions": [],
    "last_update": 0.0,
    "collection_count": 0,
    "errors": [],
    "history": [],
    "activity_log": [],
    "cycle_details": {},
    "db_status": {"redis": False, "timescaledb": False},
    "last_accuracy": {},
    "paper_trader": None,
    "intraday_trader": None,
    "fast_loop_count": 0,
    "last_prices": {},
}

FAST_LOOP_SEC = 30  # scalping cycle

POLL_INTERVAL_SEC = 120
PRE_MARKET_INTERVAL_SEC = 600

# ── WebSocket clients (queue-based for safe concurrent send) ─────

_ws_queues: dict[int, asyncio.Queue] = {}  # id(ws) -> Queue
_ws_count = 0


async def _broadcast(message: dict):
    """Push to all connected WebSocket clients via their queues."""
    if not _ws_queues:
        return
    payload = json.dumps(message, default=str)
    for q in _ws_queues.values():
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # drop if client is too slow


def _safe_float(v, default=0.0):
    """Convert to JSON-safe float (NaN/Inf → default)."""
    import math
    try:
        f = float(v)
        return default if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return default

def _build_predictions_payload() -> dict:
    predictions = _state["last_predictions"]
    snapshot = _state["last_snapshot"]  # SignalSnapshot
    if not predictions:
        return {"predictions": [], "message": "Collecting..."}

    itrader = _state.get("intraday_trader")
    bias = predictions[0] if predictions else None
    live_prices = _state.get("last_prices") or {}
    result = []

    # One entry per instrument, all sharing the same daily bias
    for inst in ALL_INSTRUMENTS:
        lp = live_prices.get(inst.ticker)
        price = lp.price if lp else 0

        entry = {
            "instrument": inst.ticker,
            "direction": bias.direction.value if bias else "FLAT",
            "score": _safe_float(bias.score) if bias else 0,
            "confidence": _safe_float(bias.confidence) if bias else 0,
            "reasons": bias.reasons if bias else [],
            "features_used": 5,
            "method": bias.method if bias else "rules",
            "ensemble": {
                "ml_score": _safe_float(bias.ml_score) if bias else 0,
                "rules_score": _safe_float(bias.rules_score) if bias else 0,
                "ml_confidence": 0,
                "rules_confidence": _safe_float(bias.confidence) if bias else 0,
            },
        }

        # Market data (from snapshot for shared signals, live price for instrument)
        if snapshot:
            entry["market_data"] = {
                "price": _safe_float(price or snapshot.nifty_close),
                "prev_close": 0,
                "change_pct": _safe_float(snapshot.nifty_change),
                "day_high": 0, "day_low": 0, "volume": 0,
                "volume_ratio": _safe_float(snapshot.volume_ratio),
                "rsi_14": _safe_float(snapshot.rsi_14, 50),
                "macd_histogram": 0, "bb_position": 0,
                "ema_9": 0, "ema_21": 0, "atr_14": 0,
                "returns_1d": _safe_float(snapshot.returns_1d),
                "returns_5d": _safe_float(snapshot.returns_5d),
                "returns_10d": 0,
                "news_sentiment": 0, "news_count": 0,
                "social_sentiment": 0, "social_post_count": 0, "social_trending": [],
                "ai_news_sentiment": _safe_float(snapshot.ai_news_sentiment),
                "ai_news_count": int(snapshot.ai_news_count or 0),
                "ai_news_positive": 0, "ai_news_negative": 0,
            }
            entry["nse_data"] = {
                "fii_net": _safe_float(snapshot.fii_net),
                "dii_net": _safe_float(snapshot.dii_net),
                "india_vix": _safe_float(snapshot.nse_vix or snapshot.india_vix),
                "india_vix_change": _safe_float(snapshot.nse_vix_change or snapshot.india_vix_change),
                "pcr_oi": 0,
                "ad_ratio": _safe_float(snapshot.ad_ratio),
                "ad_breadth_pct": _safe_float(snapshot.ad_breadth_pct),
                "ad_advances": snapshot.ad_advances,
                "ad_declines": snapshot.ad_declines,
                "nifty_live": _safe_float(snapshot.nifty_live),
                "banknifty_live": _safe_float(snapshot.banknifty_live),
            }
            entry["sector_signals"] = {
                "sp500_change": _safe_float(snapshot.sp500_change),
                "crude_oil_change": _safe_float(snapshot.crude_oil_change),
            }

        # Level-based data per instrument
        if itrader:
            levels = itrader.levels.get(inst.ticker)
            if levels:
                entry["levels"] = levels.to_dict()
            # Intraday state (decisions, etc.)
            status = itrader.get_status()
            decision = status.get("decisions", {}).get(inst.ticker)
            if decision:
                entry["decision"] = decision

        result.append(entry)

    return {
        "predictions": result,
        "updated_at": _state["last_update"],
        "session": snapshot.timestamp if snapshot else 0,
        "collection_count": _state["collection_count"],
    }


def _build_status_payload() -> dict:
    ms = market_status_summary()
    return {
        "market": ms,
        "server": {
            "collection_count": _state["collection_count"],
            "last_update": _state["last_update"],
            "last_update_ago_sec": round(time.time() - _state["last_update"], 1) if _state["last_update"] else None,
            "errors": _state["errors"][-5:],
            "ws_clients": len(_ws_queues),
            "db": _state["db_status"],
        },
    }


# ── Background collection loop ───────────────────────────────────

async def _collection_loop():
    collector = SignalCollector()
    engine = BiasPredictor()

    # Initialize paper trader
    trader = PaperTrader(capital=50_000.0, leverage=5.0, broker="fyers")
    _state["paper_trader"] = trader
    logger.info("paper_trader_initialized", capital=trader.capital, leverage=trader.leverage)

    # Redis cache for Parallel AI (if configured)
    try:
        from trade_plus.market_data import parallel_news
        if _state["db_status"]["redis"]:
            parallel_news._redis_client = _redis.client
    except Exception:
        pass

    first_run = True  # Always collect once on startup for dashboard

    while True:
        try:
            session = get_session()

            # First run: always collect regardless of session (dashboard needs data)
            if first_run:
                interval = PRE_MARKET_INTERVAL_SEC
            elif session == MarketSession.REGULAR:
                interval = POLL_INTERVAL_SEC
            elif session in (MarketSession.PRE_MARKET, MarketSession.PRE_OPEN):
                interval = PRE_MARKET_INTERVAL_SEC
            elif session in (MarketSession.CLOSED, MarketSession.POST_MARKET, MarketSession.CLOSING):
                await asyncio.sleep(1800)
                continue
            else:
                interval = PRE_MARKET_INTERVAL_SEC

            collect_start = time.time()
            snapshot = await collector.collect()
            collect_dur = round(time.time() - collect_start, 2)

            # Generate daily bias from signals (same bias applies to all Nifty-tracking ETFs)
            bias = engine.predict(snapshot.to_bias_signals(), full_snapshot=snapshot)
            predictions = [bias]

            run_id = uuid.uuid4()
            run_id_str = str(run_id)

            # ── Set bias + execute intraday trades for ALL instruments ──
            itrader = _state.get("intraday_trader")
            if itrader:
                # Same bias for all instruments (FII/VIX/S&P affect all equally)
                for inst in ALL_INSTRUMENTS:
                    itrader.set_bias(inst.ticker, bias.direction, bias.score)
                    itrader.last_prediction[inst.ticker] = bias

                if session == MarketSession.REGULAR:
                    price_map = {t: p.price for t, p in (_state.get("last_prices") or {}).items()}
                    for inst in ALL_INSTRUMENTS:
                        price = price_map.get(inst.ticker, 0)
                        if price > 0:
                            decision = itrader.decide(inst.ticker, bias, price)
                            order = itrader.execute(decision, price, run_id_str)
                            if order:
                                logger.info("intraday_trade", instrument=order.instrument,
                                          side=order.side, qty=order.quantity, price=order.fill_price,
                                          action=decision.get("action"),
                                          reasons=decision.get("reasons", [])[:2])

            _state["last_snapshot"] = snapshot
            _state["last_predictions"] = predictions
            _state["last_update"] = time.time()
            _state["collection_count"] += 1
            _state["errors"] = []
            first_run = False

            # Activity log entry
            act = {
                "run_id": run_id_str,
                "cycle": _state["collection_count"],
                "timestamp": now_ist().isoformat(),
                "session": session.value,
                "duration_sec": collect_dur,
                "next_run_at": (time.time() + interval),  # absolute timestamp for countdown
                "data_sources": {
                    "global_signals": len(snapshot.instruments.get(
                        list(snapshot.instruments.keys())[0]).global_signals) if snapshot.instruments else 0,
                    "instruments": len(snapshot.instruments),
                },
                "predictions": {
                    "NIFTYBEES": {
                        "direction": predictions[0].direction.value if predictions else "FLAT",
                        "score": _safe_float(predictions[0].score) if predictions else 0,
                        "confidence": _safe_float(predictions[0].confidence) if predictions else 0,
                        "price": _safe_float(snapshot.nifty_close),
                        "features": 5,
                        "errors": snapshot.errors,
                    }
                } if predictions else {},
                "status": "ok",
            }
            _state["activity_log"].append(act)
            if len(_state["activity_log"]) > 50:
                _state["activity_log"] = _state["activity_log"][-50:]

            # Store full cycle detail for the detail page
            detail = {
                "run_id": run_id_str,
                "cycle": _state["collection_count"],
                "timestamp": now_ist().isoformat(),
                "session": session.value,
                "duration_sec": collect_dur,
                "instruments": {},
            }
            for ticker, snap in snapshot.instruments.items():
                pred = predictions[0] if predictions else None
                detail["instruments"][ticker] = {
                    "features": snap.to_feature_dict(),
                    "global_signals": snap.global_signals,
                    "sector_signals": snap.sector_signals,
                    "price": snap.price,
                    "prev_close": snap.prev_close,
                    "change_pct": snap.change_pct,
                    "day_high": snap.day_high,
                    "day_low": snap.day_low,
                    "volume": snap.volume,
                    "volume_ratio": snap.volume_ratio,
                    "rsi_14": snap.rsi_14,
                    "macd_histogram": snap.macd_histogram,
                    "bb_position": snap.bb_position,
                    "ema_9": snap.ema_9,
                    "ema_21": snap.ema_21,
                    "atr_14": snap.atr_14,
                    "returns_1d": snap.returns_1d,
                    "returns_5d": snap.returns_5d,
                    "returns_10d": snap.returns_10d,
                    "news_sentiment": getattr(snap, 'news_sentiment', 0),
                    "news_count": getattr(snap, 'news_count', 0),
                    "social_sentiment": getattr(snap, 'social_sentiment', 0),
                    "social_positive_pct": getattr(snap, 'social_positive_pct', 0),
                    "social_negative_pct": getattr(snap, 'social_negative_pct', 0),
                    "social_post_count": getattr(snap, 'social_post_count', 0),
                    "social_trending": getattr(snap, 'social_trending', []),
                    "ai_news_sentiment": getattr(snap, 'ai_news_sentiment', 0),
                    "ai_news_count": getattr(snap, 'ai_news_count', 0),
                    "ai_news_positive": getattr(snap, 'ai_news_positive', 0),
                    "ai_news_negative": snap.ai_news_negative,
                    "fii_net": snap.fii_net,
                    "dii_net": snap.dii_net,
                    "india_vix": snap.india_vix,
                    "pcr_oi": snap.pcr_oi,
                    "ad_ratio": snap.ad_ratio,
                    "errors": snap.errors,
                    "data_staleness": snap.data_staleness,
                    "prediction": {
                        "direction": pred.direction.value if pred else "FLAT",
                        "score": _safe_float(pred.score) if pred else 0,
                        "confidence": _safe_float(pred.confidence) if pred else 0,
                        "reasons": pred.reasons if pred else [],
                        "features_used": 5,
                    } if pred else None,
                }
            _state["cycle_details"][run_id_str] = detail
            # Keep last 20 full details
            if len(_state["cycle_details"]) > 20:
                oldest_key = next(iter(_state["cycle_details"]))
                del _state["cycle_details"][oldest_key]

            # History
            entry = {
                "timestamp": now_ist().isoformat(),
                "session": session.value,
                "instruments": {},
            }
            for ticker, snap in snapshot.instruments.items():
                pred = predictions[0] if predictions else None
                entry["instruments"][ticker] = {
                    "price": snap.price,
                    "change_pct": snap.change_pct,
                    "rsi": snap.rsi_14,
                    "score": pred.score if pred else 0,
                    "direction": pred.direction.value if pred else "FLAT",
                    "confidence": pred.confidence if pred else 0,
                }
            _state["history"].append(entry)
            if len(_state["history"]) > 100:
                _state["history"] = _state["history"][-100:]

            # ── Persist to databases ──────────────────────────────────
            try:
                sess_val = session.value

                # TimescaleDB: signals + predictions + pipeline run
                if _state["db_status"]["timescaledb"]:
                    for ticker, snap in snapshot.instruments.items():
                        await _tsdb.insert_signal(run_id, sess_val, snap)
                    for inst in ALL_INSTRUMENTS:
                        for pred in predictions:
                            await _tsdb.insert_prediction(run_id, sess_val, pred, inst.ticker)
                    await _tsdb.insert_pipeline_run(
                        run_id, sess_val, collect_dur, len(snapshot.instruments),
                    )

                # Redis: cache latest prices + predictions (convert numpy types)
                if _state["db_status"]["redis"]:
                    for ticker, snap in snapshot.instruments.items():
                        await _redis.set_price(ticker, {
                            "price": float(snap.price), "change_pct": float(snap.change_pct),
                            "high": float(snap.day_high), "low": float(snap.day_low),
                            "volume": int(snap.volume),
                        })
                    for pred in predictions:
                        await _redis.set_prediction("NIFTYBEES", {
                            "direction": pred.direction.value,
                            "score": _safe_float(pred.score),
                            "confidence": _safe_float(pred.confidence),
                            "reasons": pred.reasons,
                        })
                    await _redis.set_pipeline_status({
                        "run_id": run_id_str, "session": sess_val,
                        "cycle": _state["collection_count"],
                        "duration": collect_dur, "timestamp": now_ist().isoformat(),
                    })
            except Exception as db_err:
                logger.warning("db_write_failed", error=str(db_err))

            # Broadcast to all WebSocket clients
            trading_status = trader.get_status() if trader else {}
            await _broadcast({
                "type": "update",
                "status": _build_status_payload(),
                "predictions": _build_predictions_payload(),
                "history": _state["history"][-20:],
                "activity": _state["activity_log"][-10:],
                "trading": trading_status,
            })

            logger.info(
                "cycle_complete",
                count=_state["collection_count"],
                session=session.value,
                ws_clients=len(_ws_queues),
                duration=collect_dur,
                next_in_sec=interval,
            )

        except Exception as e:
            logger.exception("collection_error")
            _state["errors"].append(str(e))
            err_act = {
                "run_id": str(uuid.uuid4()),
                "cycle": _state["collection_count"] + 1,
                "timestamp": now_ist().isoformat(),
                "session": get_session().value,
                "status": "error",
                "error": str(e),
            }
            _state["activity_log"].append(err_act)
            interval = 60

        await asyncio.sleep(interval)


# ── Status heartbeat (pushes time/session every 5s) ──────────────

async def _price_monitor_loop():
    """Monitor loop: fetch prices every 30s, store ticks, check stops, update indicators."""
    from trade_plus.instruments import ALL_INSTRUMENTS

    while _state.get("paper_trader") is None:
        await asyncio.sleep(2)

    trader = _state["paper_trader"]
    itrader = IntradayTrader(trader)
    _state["intraday_trader"] = itrader

    inst_map = {i.ticker: i.yahoo_symbol for i in ALL_INSTRUMENTS}
    has_db = _state["db_status"]["timescaledb"]
    backfilled = False
    levels_computed = False
    last_oi_fetch = 0
    OI_INTERVAL = 300  # fetch OI every 5 minutes

    # Initialize Fyers feed (auto-fallback to yfinance if not configured)
    feed = get_fyers_feed()
    feed_name = "fyers" if feed.is_configured else "yfinance"
    logger.info("monitor_loop_started", mode="intraday_swing", interval=FAST_LOOP_SEC,
                price_feed=feed_name)

    while True:
        try:
            session = get_session()

            if session not in (MarketSession.REGULAR, MarketSession.PRE_OPEN, MarketSession.CLOSING):
                # After market: square off any remaining positions and save daily result
                if session == MarketSession.POST_MARKET and trader.positions:
                    prices = {t: p.price for t, p in (_state.get("last_prices") or {}).items()}
                    if prices:
                        trader.square_off_all(prices)
                if session == MarketSession.POST_MARKET and trader.closed_trades and not _state.get("daily_saved"):
                    try:
                        from trade_plus.trading.trade_history import save_daily_result
                        save_daily_result(trader, trader.closed_trades)
                        _state["daily_saved"] = True
                    except Exception as e:
                        logger.warning("daily_save_failed", error=str(e))
                        logger.info("eod_squareoff")
                await asyncio.sleep(30)
                continue

            # One-time: backfill historical ticks
            if has_db and not backfilled:
                try:
                    from trade_plus.trading.tick_store import backfill_ticks
                    count = await backfill_ticks(_tsdb.pool, inst_map)
                    backfilled = True
                    logger.info("tick_backfill_done", rows=count)
                except Exception as e:
                    logger.warning("tick_backfill_failed", error=str(e))
                    backfilled = True

            # Compute morning levels (once per day)
            if not levels_computed and session == MarketSession.REGULAR:
                try:
                    import yfinance as yf
                    ohlc_data = {}
                    for ticker, yahoo_sym in inst_map.items():
                        t = yf.Ticker(yahoo_sym)
                        hist = t.history(period="5d", interval="1d")
                        if len(hist) >= 2:
                            prev = hist.iloc[-2]
                            today = hist.iloc[-1]
                            ohlc_data[ticker] = {
                                "high": float(prev["High"]),
                                "low": float(prev["Low"]),
                                "close": float(prev["Close"]),
                                "open_today": float(today["Open"]),
                            }
                    if ohlc_data:
                        itrader.compute_morning_levels(ohlc_data)
                        levels_computed = True
                except Exception as e:
                    logger.warning("levels_compute_failed", error=str(e))

            # Fetch OI data for all indices (every 5 min during market hours)
            if session == MarketSession.REGULAR and time.time() - last_oi_fetch > OI_INTERVAL:
                try:
                    from trade_plus.trading.oi_data import fetch_all_oi
                    from trade_plus.instruments import OI_INDICES
                    all_oi = await fetch_all_oi(OI_INDICES)  # ["NIFTY", "BANKNIFTY"]
                    if all_oi:
                        itrader.update_oi(all_oi)
                        last_oi_fetch = time.time()
                except Exception as e:
                    logger.debug("oi_fetch_failed", error=str(e))

            # Fetch prices
            ticks = await feed.fetch_prices(inst_map)
            _state["last_prices"] = ticks
            _state["fast_loop_count"] += 1

            # Store ticks + compute intraday indicators
            if has_db:
                try:
                    from trade_plus.trading.tick_store import store_ticks_batch, compute_intraday_indicators, get_today_stats
                    batch = [(t, p.price, p.volume) for t, p in ticks.items() if p.price > 0]
                    if batch:
                        await store_ticks_batch(_tsdb.pool, batch)

                    for ticker in inst_map:
                        try:
                            ind = await compute_intraday_indicators(_tsdb.pool, ticker)
                            if ind:
                                itrader.set_intraday_indicators(ticker, ind)
                            stats = await get_today_stats(_tsdb.pool, ticker)
                            if stats:
                                itrader.day_volatility[ticker] = stats.get("range_pct", 0)
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug("tick_store_error", error=str(e))

            # Update prices and check stops/targets (the slow loop handles entries)
            price_map = {t: p.price for t, p in ticks.items() if p.price > 0}
            trader.update_prices(price_map)

            # Check stop loss / take profit on open positions
            if trader.positions:
                for inst in list(trader.positions.keys()):
                    pred = itrader.last_prediction.get(inst)
                    if pred and price_map.get(inst, 0) > 0:
                        decision = itrader.decide(inst, pred, price_map[inst])
                        if decision["action"] == "EXIT":
                            order = itrader.execute(decision, price_map[inst], str(uuid.uuid4()))
                            if order:
                                logger.info("monitor_exit", instrument=inst, reason=decision["reasons"][0])

            # Broadcast live state
            if _ws_queues:
                await _broadcast({
                    "type": "trading_update",
                    "trading": trader.get_status(),
                    "momentum": itrader.get_status(),
                    "prices": {t: {"price": p.price, "bid": p.bid, "ask": p.ask, "fetch_ms": p.fetch_ms}
                              for t, p in ticks.items() if p.price > 0},
                    "fast_loop": _state["fast_loop_count"],
                })

        except Exception as e:
            logger.exception("monitor_loop_error")

        await asyncio.sleep(FAST_LOOP_SEC)


async def _heartbeat_loop():
    """Push lightweight status every 5 seconds for live timers."""
    while True:
        await asyncio.sleep(5)
        if _ws_queues:
            await _broadcast({
                "type": "heartbeat",
                "status": _build_status_payload(),
            })


# ── Accuracy evaluation (runs once after market close each day) ───

async def _accuracy_loop():
    """After market closes, evaluate today's prediction accuracy."""
    evaluated_today = False

    while True:
        session = get_session()

        # Evaluate once when market transitions to post_market/closed
        if session in (MarketSession.POST_MARKET, MarketSession.CLOSED) and not evaluated_today:
            if _state["db_status"]["timescaledb"] and _state["collection_count"] > 0:
                try:
                    from trade_plus.ml.accuracy import evaluate_day
                    results = await evaluate_day(_tsdb.pool)
                    if results:
                        _state["last_accuracy"] = results
                        logger.info("accuracy_evaluation_done", instruments=list(results.keys()))
                    evaluated_today = True
                except Exception as e:
                    logger.warning("accuracy_evaluation_failed", error=str(e))

        # Reset flag at start of new pre-market
        if session == MarketSession.PRE_MARKET:
            evaluated_today = False

        await asyncio.sleep(300)  # check every 5 min


# ── FastAPI app ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect databases (non-fatal — pipeline works without them)
    try:
        await _redis.connect()
        _state["db_status"]["redis"] = True
    except Exception as e:
        logger.warning("redis_connect_failed", error=str(e))

    try:
        await _tsdb.connect()
        _state["db_status"]["timescaledb"] = True
    except Exception as e:
        logger.warning("timescaledb_connect_failed", error=str(e))

    logger.info("db_status", redis=_state["db_status"]["redis"], timescaledb=_state["db_status"]["timescaledb"])

    # Seed in-memory state from DB (so page reload doesn't lose history)
    if _state["db_status"]["timescaledb"]:
        try:
            from collections import defaultdict

            runs = await _tsdb.get_pipeline_runs(limit=50)
            for run in reversed(runs):  # oldest first
                rid = str(run["run_id"])
                run_time = run["time"].timestamp() if run.get("time") else 0
                _state["activity_log"].append({
                    "run_id": rid,
                    "cycle": len(_state["activity_log"]) + 1,
                    "timestamp": run["time"].isoformat() if run.get("time") else "",
                    "session": run.get("session", ""),
                    "duration_sec": float(run["duration_sec"]) if run.get("duration_sec") else 0,
                    "status": run.get("status", "ok"),
                    "error": run.get("error"),
                    "predictions": {},
                    "next_run_at": 0,  # historical — no countdown
                })

            # Seed predictions per run
            for act in _state["activity_log"]:
                rid = act["run_id"]
                rows = await _tsdb.pool.fetch(
                    "SELECT instrument, direction, score, confidence, features_used "
                    "FROM predictions WHERE run_id = $1", uuid.UUID(rid),
                )
                for r in rows:
                    act["predictions"][r["instrument"]] = {
                        "direction": r["direction"],
                        "score": float(r["score"]),
                        "confidence": float(r["confidence"]),
                        "features": r["features_used"] or 0,
                        "price": 0, "errors": [],
                    }

            # Seed signal history
            hist_rows = await _tsdb.pool.fetch(
                """SELECT DISTINCT ON (run_id, instrument)
                    time, run_id, instrument, price, change_pct, rsi_14
                FROM signal_snapshots ORDER BY run_id, instrument, time DESC
                LIMIT 400""",
            )
            by_run: dict[str, dict] = defaultdict(lambda: {"instruments": {}})
            for r in hist_rows:
                rid = str(r["run_id"])
                by_run[rid]["instruments"][r["instrument"]] = {
                    "price": float(r["price"]) if r["price"] else 0,
                    "change_pct": float(r["change_pct"]) if r["change_pct"] else 0,
                    "rsi": float(r["rsi_14"]) if r["rsi_14"] else 0,
                    "score": 0, "direction": "FLAT", "confidence": 0,
                }
            pred_rows = await _tsdb.pool.fetch(
                "SELECT run_id, instrument, direction, score, confidence FROM predictions ORDER BY time",
            )
            for r in pred_rows:
                rid = str(r["run_id"])
                if rid in by_run and r["instrument"] in by_run[rid]["instruments"]:
                    by_run[rid]["instruments"][r["instrument"]].update({
                        "score": float(r["score"]),
                        "direction": r["direction"],
                        "confidence": float(r["confidence"]),
                    })

            for act in _state["activity_log"]:
                rid = act["run_id"]
                if rid in by_run:
                    _state["history"].append({
                        "timestamp": act["timestamp"],
                        "session": act["session"],
                        "instruments": by_run[rid]["instruments"],
                    })

            # Deduplicate by run_id
            seen: set[str] = set()
            deduped = []
            for a in _state["activity_log"]:
                if a["run_id"] not in seen:
                    seen.add(a["run_id"])
                    deduped.append(a)
            _state["activity_log"] = deduped

            _state["collection_count"] = len(deduped)

            logger.info("state_seeded_from_db",
                activity=len(_state["activity_log"]),
                history=len(_state["history"]),
                last_cycle=_state["collection_count"],
            )
        except Exception as e:
            logger.warning("db_seed_failed", error=str(e))

    t1 = asyncio.create_task(_collection_loop())
    t2 = asyncio.create_task(_heartbeat_loop())
    t3 = asyncio.create_task(_accuracy_loop())
    t4 = asyncio.create_task(_price_monitor_loop())
    logger.info("api_started", msg="Slow loop (2min) + monitor loop (30s) + heartbeat + accuracy")
    yield
    t1.cancel()
    t2.cancel()
    t3.cancel()
    t4.cancel()
    await _redis.disconnect()
    await _tsdb.disconnect()


app = FastAPI(title="Trade-Plus API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _ws_count
    await ws.accept()
    _ws_count += 1
    wid = id(ws)
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _ws_queues[wid] = queue
    logger.info("ws_connected", total=len(_ws_queues))

    # Send current state immediately
    try:
        trader = _state.get("paper_trader")
        await ws.send_text(json.dumps({
            "type": "init",
            "status": _build_status_payload(),
            "predictions": _build_predictions_payload(),
            "history": _state["history"][-20:],
            "activity": _state["activity_log"][-10:],
            "trading": trader.get_status() if trader else {},
        }, default=str))
    except Exception:
        _ws_queues.pop(wid, None)
        return

    async def _sender():
        """Drain the queue and send to this client."""
        try:
            while True:
                payload = await queue.get()
                await ws.send_text(payload)
        except Exception:
            pass

    async def _receiver():
        """Read client messages (pings)."""
        try:
            while True:
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
        except Exception:
            pass

    # Run sender and receiver concurrently; when either dies, cleanup
    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(_sender()), asyncio.create_task(_receiver())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        _ws_queues.pop(wid, None)
        logger.info("ws_disconnected", total=len(_ws_queues))


# REST endpoints (for initial load / fallback)
@app.get("/api/status")
async def get_status():
    return _build_status_payload()

@app.get("/api/predictions")
async def get_predictions():
    return _build_predictions_payload()

@app.get("/api/trading")
async def get_trading():
    """Paper trading status — capital, positions, P&L, orders."""
    trader = _state.get("paper_trader")
    if not trader:
        return {"error": "Paper trader not initialized"}
    return trader.get_status()

@app.get("/api/trading/day-result")
async def get_day_result():
    """End of day trading summary."""
    trader = _state.get("paper_trader")
    if not trader:
        return {"error": "Paper trader not initialized"}
    return trader.get_day_result().to_dict()

@app.get("/api/trading/momentum")
async def get_momentum():
    """Intraday trader live state — decisions, indicators, volatility."""
    itrader = _state.get("intraday_trader")
    if not itrader:
        return {"error": "Intraday trader not initialized"}
    return {
        "momentum": itrader.get_status(),
        "fast_loop_count": _state["fast_loop_count"],
        "fast_loop_interval": FAST_LOOP_SEC,
    }

@app.get("/api/instruments")
async def get_instruments():
    return {
        "instruments": [
            {"ticker": i.ticker, "name": i.name, "sector": i.sector.value,
             "approx_price": i.approx_price, "shortable": i.shortable_intraday,
             "drivers": i.global_drivers}
            for i in ALL_INSTRUMENTS
        ]
    }

@app.get("/api/feed-status")
async def get_feed_status():
    """Check which price feed is active (Fyers or yfinance fallback)."""
    feed = get_fyers_feed()
    return {
        "feed": "fyers" if feed._initialized else "yfinance",
        "fyers_configured": feed.is_configured,
        "fyers_connected": feed._initialized,
        "latency": "~100ms" if feed._initialized else "~15min delayed",
    }

@app.post("/api/fyers-token")
async def set_fyers_token(body: dict):
    """Set Fyers access token after OAuth login.

    POST /api/fyers-token {"token": "your_access_token"}
    """
    token = body.get("token", "")
    if not token:
        return {"error": "No token provided"}
    feed = get_fyers_feed()
    if feed.set_access_token(token):
        return {"status": "ok", "feed": "fyers", "msg": "Real-time feed active"}
    return {"error": "Token validation failed"}

@app.get("/api/history")
async def get_history():
    return {"history": _state["history"]}

@app.get("/api/activity")
async def get_activity():
    return {"activity": _state["activity_log"]}

@app.get("/api/trade-history")
async def get_trade_history():
    """All daily trading results with cumulative stats."""
    from trade_plus.trading.trade_history import get_cumulative_stats
    return get_cumulative_stats()

@app.get("/api/trade-history/{date}")
async def get_trade_history_day(date: str):
    """Detailed trades for a specific day (YYYY-MM-DD)."""
    from trade_plus.trading.trade_history import get_daily_result
    result = get_daily_result(date)
    if result:
        return result
    return {"error": f"No trade data for {date}"}

@app.post("/api/trade-history/save")
async def save_trade_history_now():
    """Manually save today's trading result (for testing)."""
    trader = _state.get("paper_trader")
    if not trader:
        return {"error": "Paper trader not initialized"}
    from trade_plus.trading.trade_history import save_daily_result
    result = save_daily_result(trader, trader.closed_trades)
    return result

@app.get("/api/accuracy/{instrument}")
async def get_accuracy(instrument: str, days: int = 30):
    """Get prediction accuracy history for an instrument."""
    if not _state["db_status"]["timescaledb"]:
        return {"error": "TimescaleDB not connected"}
    try:
        from trade_plus.ml.accuracy import get_accuracy_summary
        return await get_accuracy_summary(_tsdb.pool, instrument, days)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/accuracy")
async def get_all_accuracy():
    """Get accuracy summary for all instruments."""
    if not _state["db_status"]["timescaledb"]:
        return {"error": "TimescaleDB not connected"}
    try:
        from trade_plus.ml.accuracy import get_accuracy_summary
        result = {}
        for inst in ALL_INSTRUMENTS:
            result[inst.ticker] = await get_accuracy_summary(_tsdb.pool, inst.ticker, 30)
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/run/{run_id}")
async def get_run_detail(run_id: str):
    # Try in-memory first
    detail = _state["cycle_details"].get(run_id)
    if detail:
        return detail

    # Fall back to DB
    if not _state["db_status"]["timescaledb"]:
        return {"error": "Run not in memory and DB not connected"}

    try:
        rid = uuid.UUID(run_id)
        signals = await _tsdb.pool.fetch(
            "SELECT * FROM signal_snapshots WHERE run_id = $1", rid,
        )
        preds = await _tsdb.pool.fetch(
            "SELECT * FROM predictions WHERE run_id = $1", rid,
        )
        runs = await _tsdb.pool.fetch(
            "SELECT * FROM pipeline_runs WHERE run_id = $1", rid,
        )
        if not signals:
            return {"error": f"Run {run_id} not found in database"}

        run = dict(runs[0]) if runs else {}
        detail = {
            "run_id": run_id,
            "timestamp": run.get("time", "").isoformat() if run.get("time") else "",
            "session": run.get("session", ""),
            "duration_sec": float(run.get("duration_sec", 0)),
            "instruments": {},
        }
        for row in signals:
            inst = row["instrument"]
            pred_row = next((dict(p) for p in preds if p["instrument"] == inst), {})
            detail["instruments"][inst] = {
                "features": row["features"] or {},
                "global_signals": row["global_signals"] or {},
                "sector_signals": row["sector_signals"] or {},
                "price": float(row["price"]) if row["price"] else 0,
                "prev_close": float(row["prev_close"]) if row["prev_close"] else 0,
                "change_pct": float(row["change_pct"]) if row["change_pct"] else 0,
                "day_high": float(row["day_high"]) if row["day_high"] else 0,
                "day_low": float(row["day_low"]) if row["day_low"] else 0,
                "volume": int(row["volume"]) if row["volume"] else 0,
                "volume_ratio": float(row["volume_ratio"]) if row["volume_ratio"] else 0,
                "rsi_14": float(row["rsi_14"]) if row["rsi_14"] else 0,
                "macd_histogram": float(row["macd_histogram"]) if row["macd_histogram"] else 0,
                "bb_position": float(row["bb_position"]) if row["bb_position"] else 0,
                "ema_9": float(row["ema_9"]) if row["ema_9"] else 0,
                "ema_21": float(row["ema_21"]) if row["ema_21"] else 0,
                "atr_14": float(row["atr_14"]) if row["atr_14"] else 0,
                "returns_1d": float(row["returns_1d"]) if row["returns_1d"] else 0,
                "returns_5d": float(row["returns_5d"]) if row["returns_5d"] else 0,
                "returns_10d": float(row["returns_10d"]) if row["returns_10d"] else 0,
                "news_sentiment": float(row["news_sentiment"]) if row["news_sentiment"] else 0,
                "news_count": int(row["news_count"]) if row["news_count"] else 0,
                "social_sentiment": float(row["social_sentiment"]) if row.get("social_sentiment") else 0,
                "social_positive_pct": float(row["social_positive_pct"]) if row.get("social_positive_pct") else 0,
                "social_negative_pct": float(row["social_negative_pct"]) if row.get("social_negative_pct") else 0,
                "social_post_count": int(row["social_post_count"]) if row.get("social_post_count") else 0,
                "social_trending": list(row["social_trending"]) if row.get("social_trending") else [],
                "ai_news_sentiment": float(row["ai_news_sentiment"]) if row.get("ai_news_sentiment") else 0,
                "ai_news_count": int(row["ai_news_count"]) if row.get("ai_news_count") else 0,
                "ai_news_positive": int(row["ai_news_positive"]) if row.get("ai_news_positive") else 0,
                "ai_news_negative": int(row["ai_news_negative"]) if row.get("ai_news_negative") else 0,
                "fii_net": float(row["fii_net"]) if row["fii_net"] else 0,
                "dii_net": float(row["dii_net"]) if row["dii_net"] else 0,
                "india_vix": float(row["india_vix"]) if row["india_vix"] else 0,
                "pcr_oi": float(row["pcr_oi"]) if row["pcr_oi"] else 0,
                "ad_ratio": float(row["ad_ratio"]) if row["ad_ratio"] else 0,
                "errors": list(row["errors"]) if row["errors"] else [],
                "data_staleness": row["data_staleness"] or "unknown",
                "prediction": {
                    "direction": pred_row.get("direction", "FLAT"),
                    "score": float(pred_row["score"]) if pred_row.get("score") else 0,
                    "confidence": float(pred_row["confidence"]) if pred_row.get("confidence") else 0,
                    "reasons": list(pred_row.get("reasons", [])),
                    "features_used": pred_row.get("features_used", 0),
                } if pred_row else None,
            }
        return detail
    except Exception as e:
        return {"error": f"DB query failed: {e}"}


def main():
    import click

    @click.command()
    @click.option("--port", default=8000, type=int)
    @click.option("--host", default="0.0.0.0")
    def _run(port: int, host: str):
        uvicorn.run(app, host=host, port=port, log_level="info")

    _run()


if __name__ == "__main__":
    main()
