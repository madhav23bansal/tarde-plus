"""Generic, instrument-aware signal collector.

Collects data in 3 layers:
  Layer 1: GLOBAL signals (same for all instruments — collected once)
           US markets, commodities, forex, VIX, bond yields
  Layer 2: SECTOR signals (specific to gold/index/silver/banking)
           Sector-specific drivers, reference prices
  Layer 3: INSTRUMENT signals (specific to each ETF)
           Price history, technicals, volume, sentiment

Edge cases handled:
  - API failures (graceful degradation, use stale data)
  - Market closed (return last known values with staleness flag)
  - Partial data (collect what we can, flag what's missing)
  - Rate limiting (NSE: 1 req/1.5s, Yahoo: 0.5s gap)
  - Holidays (skip NSE calls, still collect global)
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import structlog

from trade_plus.instruments import ALL_INSTRUMENTS, Instrument, Sector
from trade_plus.market_data.market_hours import (
    is_trading_day,
    get_session,
    MarketSession,
    now_ist,
)

logger = structlog.get_logger()

_executor = ThreadPoolExecutor(max_workers=4)


@dataclass
class SignalSnapshot:
    """All signals for one instrument at a point in time."""
    instrument: str = ""
    sector: str = ""
    timestamp: float = 0.0
    collection_time_ms: float = 0.0

    # How fresh is this data?
    is_market_open: bool = False
    data_staleness: str = "fresh"       # fresh | stale | partial | unavailable

    # ── Global signals (shared across instruments) ──
    global_signals: dict[str, float] = field(default_factory=dict)

    # ── Sector-specific signals ──
    sector_signals: dict[str, float] = field(default_factory=dict)

    # ── Instrument-specific signals ──
    price: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    volume: int = 0
    volume_ratio: float = 0.0          # vs 20d avg

    # Technicals (computed from history)
    rsi_14: float = 50.0
    macd_histogram: float = 0.0
    bb_position: float = 0.5           # 0=lower band, 1=upper band
    atr_14: float = 0.0
    ema_9: float = 0.0
    ema_21: float = 0.0
    returns_1d: float = 0.0
    returns_5d: float = 0.0
    returns_10d: float = 0.0

    # Sentiment (RSS + VADER)
    news_sentiment: float = 0.0
    news_count: int = 0

    # Social sentiment (X/Twitter via Grok)
    social_sentiment: float = 0.0
    social_positive_pct: float = 0.0
    social_negative_pct: float = 0.0
    social_post_count: int = 0
    social_trending: list[str] = field(default_factory=list)

    # AI news search (Parallel AI)
    ai_news_sentiment: float = 0.0
    ai_news_count: int = 0
    ai_news_positive: int = 0
    ai_news_negative: int = 0

    # NSE-specific (only for index/banking)
    fii_net: float = 0.0
    dii_net: float = 0.0
    india_vix: float = 0.0
    india_vix_change: float = 0.0
    pcr_oi: float = 0.0
    ad_ratio: float = 0.0

    # Calendar
    day_of_week: int = 0
    is_expiry_week: bool = False
    days_to_monthly_expiry: int = 0

    # Errors during collection
    errors: list[str] = field(default_factory=list)

    def to_feature_dict(self) -> dict:
        """Flat dict of all features for ML model input.

        IMPORTANT: Feature names must exactly match what ml/features.py produces
        during training. The ML model expects these specific keys.
        """
        features = {}

        # Global signals — include ALL (not filtered by sector)
        # ML model trains on all globals for every instrument
        for k, v in self.global_signals.items():
            features[f"global_{k}"] = v

        # Sector signals (additional context)
        for k, v in self.sector_signals.items():
            features[f"sector_{k}"] = v

        # Instrument technicals — must match ml/features.py::build_instrument_features()
        features.update({
            "price_change_pct": self.change_pct,
            "volume_ratio": self.volume_ratio,
            "rsi_14": self.rsi_14,
            "macd_histogram": self.macd_histogram,
            "bb_position": self.bb_position,
            "atr_14": self.atr_14,
            "ema_9": self.ema_9,       # raw values needed by ML
            "ema_21": self.ema_21,
            "ema_crossover": 1.0 if self.ema_9 > self.ema_21 else -1.0 if self.ema_9 < self.ema_21 else 0.0,
            "returns_1d": self.returns_1d,
            "returns_5d": self.returns_5d,
            "returns_10d": self.returns_10d,
            # Sentiment (RSS)
            "news_sentiment": self.news_sentiment,
            "news_count": self.news_count,
            # Social sentiment (X/Twitter via Grok)
            "social_sentiment": self.social_sentiment,
            "social_post_count": self.social_post_count,
            # AI news (Parallel)
            "ai_news_sentiment": self.ai_news_sentiment,
            "ai_news_count": self.ai_news_count,
            # Calendar
            "day_of_week": self.day_of_week,
            "is_expiry_week": int(self.is_expiry_week),
            "days_to_expiry": self.days_to_monthly_expiry,
        })

        # NSE-specific (only populated for index/banking)
        if self.sector in ("index", "banking"):
            features.update({
                "fii_net": self.fii_net,
                "dii_net": self.dii_net,
                "india_vix": self.india_vix,
                "india_vix_change": self.india_vix_change,
                "pcr_oi": self.pcr_oi,
                "ad_ratio": self.ad_ratio,
            })

        return features

    @property
    def feature_count(self) -> int:
        return len(self.to_feature_dict())


@dataclass
class MarketSnapshot:
    """All instruments' signals at a point in time."""
    timestamp: float = 0.0
    session: str = ""
    instruments: dict[str, SignalSnapshot] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"Market Snapshot ({self.session}) @ {time.strftime('%H:%M:%S', time.localtime(self.timestamp))}"]
        for ticker, snap in self.instruments.items():
            direction = "UP" if snap.change_pct > 0 else "DOWN" if snap.change_pct < 0 else "FLAT"
            lines.append(
                f"  {ticker:<12s}: Rs {snap.price:>8.2f} ({snap.change_pct:>+6.2f}%) "
                f"RSI={snap.rsi_14:.0f} Sent={snap.news_sentiment:>+.3f} "
                f"[{snap.feature_count} features, {len(snap.errors)} errors]"
            )
        return "\n".join(lines)


class SignalCollector:
    """Collects prediction signals for all instruments."""

    def __init__(self, instruments: list[Instrument] | None = None) -> None:
        self._instruments = instruments or ALL_INSTRUMENTS
        self._global_cache: dict[str, float] = {}
        self._global_cache_ts: float = 0.0
        self._nse_cookies_ts: float = 0.0

        # AI clients (initialized lazily if API keys are set)
        self._grok = None
        self._parallel = None
        try:
            from trade_plus.core.config import AIConfig
            ai = AIConfig()
            if ai.xai_api_key:
                from trade_plus.market_data.grok_sentiment import GrokSentimentClient
                self._grok = GrokSentimentClient(ai.xai_api_key)
                logger.info("grok_client_initialized")
            if ai.parallel_api_key:
                from trade_plus.market_data.parallel_news import ParallelNewsClient
                self._parallel = ParallelNewsClient(ai.parallel_api_key)
                logger.info("parallel_client_initialized")
        except Exception as e:
            logger.debug("ai_clients_not_available", error=str(e))

    # ─── Layer 1: Global Signals ────────────────────────────────

    async def _collect_global(self) -> dict[str, float]:
        """Collect all global market data. Cached for 60s."""
        if time.time() - self._global_cache_ts < 60 and self._global_cache:
            return self._global_cache

        loop = asyncio.get_event_loop()

        def _fetch():
            import yfinance as yf
            symbols = {
                "sp500": "^GSPC", "nasdaq": "^IXIC", "dow": "^DJI",
                "nikkei": "^N225", "hangseng": "^HSI",
                "us_futures": "ES=F",
                "crude_oil": "CL=F", "gold": "GC=F", "silver": "SI=F",
                "copper": "HG=F",
                "usd_inr": "USDINR=X", "dxy": "DX-Y.NYB",
                "us_10y": "^TNX",
                "india_vix": "^INDIAVIX",
                "nifty50": "^NSEI", "banknifty": "^NSEBANK",
            }
            results = {}
            for name, sym in symbols.items():
                try:
                    t = yf.Ticker(sym)
                    hist = t.history(period="10d")
                    if len(hist) >= 2:
                        close = float(hist["Close"].iloc[-1])
                        prev = float(hist["Close"].iloc[-2])
                        change = (close - prev) / prev * 100 if prev else 0
                        results[f"{name}_close"] = close
                        results[f"{name}_prev"] = prev
                        results[f"{name}_change"] = round(change, 3)

                        # 5-day change (matches ML training feature)
                        if len(hist) >= 6:
                            prev5 = float(hist["Close"].iloc[-6])
                            change5 = (close - prev5) / prev5 * 100 if prev5 else 0
                            results[f"{name}_5d"] = round(change5, 3)
                        else:
                            results[f"{name}_5d"] = 0.0
                    elif len(hist) == 1:
                        results[f"{name}_close"] = float(hist["Close"].iloc[-1])
                        results[f"{name}_change"] = 0.0
                        results[f"{name}_5d"] = 0.0
                except Exception:
                    results[f"{name}_close"] = 0.0
                    results[f"{name}_change"] = 0.0
                    results[f"{name}_5d"] = 0.0

            # Derived signals
            gold_c = results.get("gold_close", 0)
            silver_c = results.get("silver_close", 0)
            results["gold_silver_ratio"] = round(gold_c / silver_c, 2) if silver_c > 0 else 0
            results["gs_ratio_signal"] = (1.0 if results["gold_silver_ratio"] > 85 else -1.0 if results["gold_silver_ratio"] < 70 else 0.0) if silver_c > 0 else 0.0

            return results

        self._global_cache = await loop.run_in_executor(_executor, _fetch)
        self._global_cache_ts = time.time()
        logger.info("global_signals_collected", count=len(self._global_cache))
        return self._global_cache

    # ─── Layer 2: Sector Signals ────────────────────────────────

    def _extract_sector_signals(self, instrument: Instrument, global_data: dict) -> dict[str, float]:
        """Extract sector-relevant signals from global data."""
        sector_signals = {}

        for driver in instrument.global_drivers:
            # Map driver name to global data keys
            close_key = f"{driver}_close"
            change_key = f"{driver}_change"

            if close_key in global_data:
                sector_signals[f"{driver}_close"] = global_data[close_key]
            if change_key in global_data:
                sector_signals[f"{driver}_change"] = global_data[change_key]

        # Sector-specific derived signals
        if instrument.sector == Sector.GOLD:
            sector_signals["dxy_inverse"] = -global_data.get("dxy_change", 0)
            sector_signals["real_yield_proxy"] = -(global_data.get("us_10y_change", 0))

        elif instrument.sector == Sector.SILVER:
            sector_signals["gold_silver_ratio"] = global_data.get("gold_silver_ratio", 0)
            # High ratio = silver cheap relative to gold = bullish silver
            sector_signals["gs_ratio_signal"] = 1.0 if global_data.get("gold_silver_ratio", 80) > 85 else -1.0 if global_data.get("gold_silver_ratio", 80) < 70 else 0.0

        elif instrument.sector == Sector.INDEX:
            # Nifty-specific
            sector_signals["global_risk_on"] = 1.0 if global_data.get("sp500_change", 0) > 0.5 else -1.0 if global_data.get("sp500_change", 0) < -0.5 else 0.0

        elif instrument.sector == Sector.BANKING:
            sector_signals["rate_sensitivity"] = -global_data.get("us_10y_change", 0)

        return sector_signals

    # ─── Layer 3: Instrument Signals (technicals) ───────────────

    async def _collect_instrument_technicals(self, instrument: Instrument) -> dict:
        """Compute technical indicators from price history."""
        loop = asyncio.get_event_loop()

        def _compute():
            import yfinance as yf
            try:
                # Use Ticker.history() — yf.download has multi-index issues
                ticker = yf.Ticker(instrument.yahoo_symbol)
                hist = ticker.history(period="6mo", interval="1d")
                if hist.empty or len(hist) < 20:
                    return {"error": f"insufficient_history for {instrument.yahoo_symbol} ({len(hist)} rows)"}

                close = hist["Close"].values.astype(float)
                high = hist["High"].values.astype(float)
                low = hist["Low"].values.astype(float)
                volume = hist["Volume"].values.astype(float)

                # Current price info
                result = {
                    "price": close[-1],
                    "prev_close": close[-2] if len(close) > 1 else close[-1],
                    "change_pct": round((close[-1] / close[-2] - 1) * 100, 3) if len(close) > 1 else 0,
                    "day_high": high[-1],
                    "day_low": low[-1],
                    "volume": int(volume[-1]),
                }

                # Volume ratio
                vol_avg = np.mean(volume[-20:])
                result["volume_ratio"] = round(volume[-1] / vol_avg, 2) if vol_avg > 0 else 1.0

                # RSI 14
                delta = np.diff(close)
                gain = np.where(delta > 0, delta, 0)
                loss = np.where(delta < 0, -delta, 0)
                if len(gain) >= 14:
                    avg_gain = np.convolve(gain, np.ones(14)/14, mode='valid')
                    avg_loss = np.convolve(loss, np.ones(14)/14, mode='valid')
                    rs = avg_gain[-1] / (avg_loss[-1] + 1e-10)
                    result["rsi_14"] = round(100 - (100 / (1 + rs)), 1)
                else:
                    result["rsi_14"] = 50.0

                # EMA 9 and 21
                def ema(data, period):
                    alpha = 2 / (period + 1)
                    e = np.zeros_like(data, dtype=float)
                    e[0] = data[0]
                    for i in range(1, len(data)):
                        e[i] = alpha * data[i] + (1 - alpha) * e[i-1]
                    return e

                ema9 = ema(close, 9)
                ema21 = ema(close, 21)
                result["ema_9"] = round(ema9[-1], 2)
                result["ema_21"] = round(ema21[-1], 2)

                # MACD (12, 26, 9)
                ema12 = ema(close, 12)
                ema26 = ema(close, 26)
                macd_line = ema12 - ema26
                signal_line = ema(macd_line, 9)
                result["macd_histogram"] = round(macd_line[-1] - signal_line[-1], 2)

                # Bollinger Bands (20, 2)
                if len(close) >= 20:
                    sma20 = np.mean(close[-20:])
                    std20 = np.std(close[-20:])
                    upper = sma20 + 2 * std20
                    lower = sma20 - 2 * std20
                    bb_range = upper - lower
                    result["bb_position"] = round((close[-1] - lower) / bb_range, 3) if bb_range > 0 else 0.5
                else:
                    result["bb_position"] = 0.5

                # ATR 14
                if len(close) >= 15:
                    tr = np.maximum(
                        high[1:] - low[1:],
                        np.maximum(
                            np.abs(high[1:] - close[:-1]),
                            np.abs(low[1:] - close[:-1]),
                        ),
                    )
                    result["atr_14"] = round(np.mean(tr[-14:]), 2)
                else:
                    result["atr_14"] = 0

                # Returns
                result["returns_1d"] = round((close[-1] / close[-2] - 1) * 100, 3) if len(close) > 1 else 0
                result["returns_5d"] = round((close[-1] / close[-6] - 1) * 100, 3) if len(close) > 5 else 0
                result["returns_10d"] = round((close[-1] / close[-11] - 1) * 100, 3) if len(close) > 10 else 0

                return result
            except Exception as e:
                return {"error": str(e)}

        return await loop.run_in_executor(_executor, _compute)

    # ─── News Sentiment ─────────────────────────────────────────

    async def _collect_sentiment(self, instrument: Instrument) -> dict:
        """Collect news sentiment relevant to this instrument's sector."""
        loop = asyncio.get_event_loop()

        def _score():
            import feedparser
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            # Sector-specific search terms and feeds
            sector_feeds = {
                Sector.INDEX: [
                    "https://news.google.com/rss/search?q=nifty+OR+sensex+OR+indian+stock+market&hl=en-IN&gl=IN",
                    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                ],
                Sector.GOLD: [
                    "https://news.google.com/rss/search?q=gold+price+india+OR+gold+market+OR+gold+etf&hl=en-IN&gl=IN",
                    "https://news.google.com/rss/search?q=gold+price+forecast+OR+COMEX+gold&hl=en&gl=US",
                ],
                Sector.SILVER: [
                    "https://news.google.com/rss/search?q=silver+price+india+OR+silver+market&hl=en-IN&gl=IN",
                    "https://news.google.com/rss/search?q=silver+forecast+OR+COMEX+silver&hl=en&gl=US",
                ],
                Sector.BANKING: [
                    "https://news.google.com/rss/search?q=bank+nifty+OR+indian+banking+sector+OR+RBI+policy&hl=en-IN&gl=IN",
                    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                ],
            }

            # Also always include broad market sentiment
            common_feeds = [
                "https://www.moneycontrol.com/rss/MCtopnews.xml",
            ]

            feeds = sector_feeds.get(instrument.sector, []) + common_feeds
            headlines = []
            for url in feeds:
                try:
                    feed = feedparser.parse(url)
                    headlines.extend([e.title for e in feed.entries[:15]])
                except Exception:
                    continue

            if not headlines:
                return {"news_sentiment": 0, "news_count": 0}

            analyzer = SentimentIntensityAnalyzer()
            scores = [analyzer.polarity_scores(h)["compound"] for h in headlines]

            return {
                "news_sentiment": round(float(np.mean(scores)), 4),
                "news_count": len(headlines),
            }

        return await loop.run_in_executor(_executor, _score)

    # ─── NSE-specific (FII/DII, PCR, VIX) ──────────────────────

    async def _collect_nse_data(self) -> dict:
        """Collect NSE-specific data: FII/DII, option chain PCR, VIX, breadth."""
        import httpx

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }

        result = {}
        try:
            async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True) as client:
                # Get cookies
                await client.get("https://www.nseindia.com/", headers={
                    **headers, "Accept": "text/html",
                })

                # All indices (VIX + breadth)
                await asyncio.sleep(1.5)
                resp = await client.get("https://www.nseindia.com/api/allIndices")
                if resp.status_code == 200:
                    for idx in resp.json().get("data", []):
                        name = idx.get("index", "")
                        if name == "INDIA VIX":
                            result["india_vix"] = float(idx.get("last", 0))
                            result["india_vix_change"] = float(idx.get("percentChange", 0))
                        elif name == "NIFTY 50":
                            adv = int(idx.get("advances", 0))
                            dec = int(idx.get("declines", 0))
                            result["ad_ratio"] = round(adv / dec, 2) if dec > 0 else 1.0

                # FII/DII
                await asyncio.sleep(1.5)
                resp = await client.get("https://www.nseindia.com/api/fiidiiTradeReact")
                if resp.status_code == 200:
                    for entry in resp.json():
                        cat = entry.get("category", "")
                        buy = float(entry.get("buyValue", 0))
                        sell = float(entry.get("sellValue", 0))
                        if "FII" in cat or "FPI" in cat:
                            result["fii_net"] = round(buy - sell, 2)
                        elif "DII" in cat:
                            result["dii_net"] = round(buy - sell, 2)

                # Option chain (PCR) — only during market hours
                if get_session() in (MarketSession.REGULAR, MarketSession.PRE_OPEN):
                    await asyncio.sleep(1.5)
                    resp = await client.get(
                        "https://www.nseindia.com/api/option-chain-indices",
                        params={"symbol": "NIFTY"},
                    )
                    if resp.status_code == 200:
                        filtered = resp.json().get("filtered", {})
                        total_ce = sum(r.get("CE", {}).get("openInterest", 0) for r in filtered.get("data", []))
                        total_pe = sum(r.get("PE", {}).get("openInterest", 0) for r in filtered.get("data", []))
                        result["pcr_oi"] = round(total_pe / total_ce, 3) if total_ce > 0 else 0

        except Exception as e:
            logger.warning("nse_data_collection_failed", error=str(e))
            result["_error"] = str(e)

        return result

    # ─── Calendar ───────────────────────────────────────────────

    def _collect_calendar(self) -> dict:
        from calendar import monthcalendar
        now = now_ist()

        def last_thursday(year, month):
            cal = monthcalendar(year, month)
            for week in reversed(cal):
                if week[3] != 0:
                    return datetime(year, month, week[3])
            return None

        exp = last_thursday(now.year, now.month)
        if exp and exp.date() < now.date():
            nm = now.month + 1 if now.month < 12 else 1
            ny = now.year if now.month < 12 else now.year + 1
            exp = last_thursday(ny, nm)

        days_to_exp = (exp.date() - now.date()).days if exp else 30

        return {
            "day_of_week": now.weekday(),
            "is_expiry_week": days_to_exp <= 5,
            "days_to_monthly_expiry": days_to_exp,
        }

    # ─── Master: Collect Everything ─────────────────────────────

    async def collect(self) -> MarketSnapshot:
        """Collect all signals for all instruments.

        Execution plan:
          1. Global data (one call, shared) — parallel
          2. Per-instrument technicals — parallel
          3. Per-instrument sentiment — parallel
          4. NSE data (rate-limited) — sequential
          5. Calendar (no IO) — instant
        """
        start = time.time()
        session = get_session()

        snapshot = MarketSnapshot(
            timestamp=start,
            session=session.value,
        )

        # Step 1+2+3: Run global, all technicals, and all sentiment in parallel
        global_task = asyncio.create_task(self._collect_global())
        tech_tasks = {
            inst.ticker: asyncio.create_task(self._collect_instrument_technicals(inst))
            for inst in self._instruments
        }
        sent_tasks = {
            inst.ticker: asyncio.create_task(self._collect_sentiment(inst))
            for inst in self._instruments
        }

        # Step 3b: AI sentiment (Grok + Parallel) — parallel per instrument
        grok_tasks = {}
        parallel_tasks = {}
        if self._grok:
            for inst in self._instruments:
                grok_tasks[inst.ticker] = asyncio.create_task(
                    self._grok.get_sentiment(inst.sector.value, inst.ticker)
                )
        if self._parallel:
            for inst in self._instruments:
                parallel_tasks[inst.ticker] = asyncio.create_task(
                    self._parallel.search_news(inst.sector.value)
                )

        # Step 4: NSE data (sequential due to rate limiting)
        nse_data = {}
        nse_sectors = {Sector.INDEX, Sector.BANKING}
        if any(i.sector in nse_sectors for i in self._instruments):
            nse_data = await self._collect_nse_data()

        # Step 5: Calendar
        calendar = self._collect_calendar()

        # Await parallel tasks
        global_data = await global_task

        # Build snapshot for each instrument
        for inst in self._instruments:
            snap = SignalSnapshot(
                instrument=inst.ticker,
                sector=inst.sector.value,
                timestamp=start,
                is_market_open=session == MarketSession.REGULAR,
            )

            # Global signals — include ALL so ML model gets complete feature set
            # (filtering by sector drivers caused 64% of ML features to be zero-filled)
            snap.global_signals = dict(global_data)

            # Sector signals
            snap.sector_signals = self._extract_sector_signals(inst, global_data)

            # Technicals
            tech = await tech_tasks[inst.ticker]
            if "error" in tech:
                snap.errors.append(f"technicals: {tech['error']}")
            else:
                snap.price = tech.get("price", 0)
                snap.prev_close = tech.get("prev_close", 0)
                snap.change_pct = tech.get("change_pct", 0)
                snap.day_high = tech.get("day_high", 0)
                snap.day_low = tech.get("day_low", 0)
                snap.volume = tech.get("volume", 0)
                snap.volume_ratio = tech.get("volume_ratio", 1)
                snap.rsi_14 = tech.get("rsi_14", 50)
                snap.ema_9 = tech.get("ema_9", 0)
                snap.ema_21 = tech.get("ema_21", 0)
                snap.macd_histogram = tech.get("macd_histogram", 0)
                snap.bb_position = tech.get("bb_position", 0.5)
                snap.atr_14 = tech.get("atr_14", 0)
                snap.returns_1d = tech.get("returns_1d", 0)
                snap.returns_5d = tech.get("returns_5d", 0)
                snap.returns_10d = tech.get("returns_10d", 0)

            # RSS Sentiment
            sent = await sent_tasks[inst.ticker]
            snap.news_sentiment = sent.get("news_sentiment", 0)
            snap.news_count = sent.get("news_count", 0)

            # Grok X/Twitter sentiment
            if inst.ticker in grok_tasks:
                try:
                    grok_result = await grok_tasks[inst.ticker]
                    snap.social_sentiment = grok_result.score
                    snap.social_positive_pct = grok_result.positive_pct
                    snap.social_negative_pct = grok_result.negative_pct
                    snap.social_post_count = grok_result.post_count
                    snap.social_trending = grok_result.trending_topics[:3]
                except Exception as e:
                    snap.errors.append(f"grok: {e}")

            # Parallel AI news sentiment
            if inst.ticker in parallel_tasks:
                try:
                    parallel_result = await parallel_tasks[inst.ticker]
                    snap.ai_news_sentiment = parallel_result.score
                    snap.ai_news_count = parallel_result.article_count
                    snap.ai_news_positive = parallel_result.positive_count
                    snap.ai_news_negative = parallel_result.negative_count
                except Exception as e:
                    snap.errors.append(f"parallel: {e}")

            # NSE data (for index/banking sectors)
            if inst.sector in nse_sectors:
                snap.fii_net = nse_data.get("fii_net", 0)
                snap.dii_net = nse_data.get("dii_net", 0)
                snap.india_vix = nse_data.get("india_vix", 0)
                snap.india_vix_change = nse_data.get("india_vix_change", 0)
                snap.pcr_oi = nse_data.get("pcr_oi", 0)
                snap.ad_ratio = nse_data.get("ad_ratio", 0)
            else:
                # Gold/Silver still benefit from VIX
                snap.india_vix = nse_data.get("india_vix", global_data.get("india_vix_close", 0))

            # Calendar
            snap.day_of_week = calendar["day_of_week"]
            snap.is_expiry_week = calendar["is_expiry_week"]
            snap.days_to_monthly_expiry = calendar["days_to_monthly_expiry"]

            # Staleness check
            if snap.errors:
                snap.data_staleness = "partial"
            elif not is_trading_day():
                snap.data_staleness = "stale"

            snap.collection_time_ms = round((time.time() - start) * 1000, 1)
            snapshot.instruments[inst.ticker] = snap

        elapsed = time.time() - start
        logger.info(
            "market_snapshot_collected",
            instruments=len(snapshot.instruments),
            elapsed_s=round(elapsed, 1),
            session=session.value,
        )

        return snapshot
