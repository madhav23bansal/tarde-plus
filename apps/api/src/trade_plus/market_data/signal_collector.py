"""Simplified signal collector — only the 5 signals that matter.

Collects pre-market/daily bias signals:
  1. S&P 500 overnight change
  2. India VIX level
  3. Crude oil change
  4. FII/DII flows (from NSE)
  5. USD/INR change

Also collects NIFTYBEES price history for intraday technicals.

ML DATA NOTE: Every signal snapshot is stored in TimescaleDB for
future model training. When we have 300+ trades, we can train
a model on: (signals at trade time) → (trade outcome).
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import structlog

from trade_plus.instruments import GLOBAL_SYMBOLS, NIFTYBEES
from trade_plus.market_data.market_hours import get_session, MarketSession

logger = structlog.get_logger()
_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class SignalSnapshot:
    """Pre-market / daily signals for bias prediction.

    ML FUTURE: All fields stored in DB. When adding ML layer later,
    use these as input features + trade outcome as label.
    """
    timestamp: float = 0.0

    # Global signals (5 that matter)
    sp500_change: float = 0.0
    sp500_5d: float = 0.0
    crude_oil_change: float = 0.0
    crude_oil_5d: float = 0.0
    india_vix: float = 0.0
    india_vix_change: float = 0.0
    usd_inr_change: float = 0.0

    # FII/DII (from NSE)
    fii_net: float = 0.0
    dii_net: float = 0.0

    # NIFTYBEES daily technicals (from yfinance history)
    nifty_close: float = 0.0
    nifty_change: float = 0.0
    rsi_14: float = 50.0
    returns_1d: float = 0.0
    returns_5d: float = 0.0
    volume_ratio: float = 1.0

    # News sentiment (free RSS + financial VADER)
    news_score: float = 0.0         # -1 to +1 aggregate sentiment
    news_magnitude: float = 0.0     # strength of sentiment
    news_bullish: int = 0
    news_bearish: int = 0
    news_total: int = 0

    # FII cumulative momentum
    fii_5d: float = 0.0              # 5-day cumulative FII net
    fii_10d: float = 0.0             # 10-day cumulative
    fii_acceleration: float = 0.0     # is selling speeding up?
    fii_consecutive: int = 0          # streak of same-direction days
    fii_streak_direction: str = ""
    fii_momentum_signal: str = "neutral"
    fii_momentum_score: float = 0.0

    # Gap prediction (pre-market signal)
    predicted_gap_pct: float = 0.0    # predicted opening gap %
    gap_direction: str = "flat"       # gap_up, gap_down, flat
    gap_confidence: float = 0.0

    # NSE enhanced data (free, scraped from NSE API)
    ad_ratio: float = 0.0       # Nifty 50 advance/decline ratio
    ad_advances: int = 0
    ad_declines: int = 0
    ad_breadth_pct: float = 0.0 # % of Nifty 50 stocks advancing
    nse_vix: float = 0.0        # Real-time VIX from NSE (more accurate than yfinance)
    nse_vix_change: float = 0.0
    nifty_live: float = 0.0     # Live Nifty from NSE
    banknifty_live: float = 0.0 # Live BankNifty from NSE
    nifty_open: float = 0.0     # Today's Nifty open

    # Parallel AI sentiment (morning fetch, cached)
    ai_news_sentiment: float = 0.0
    ai_news_count: int = 0

    # Collection metadata
    collection_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    # Compatibility: old code accesses snapshot.instruments["NIFTYBEES"]
    instrument: str = "NIFTYBEES"
    sector: str = "index"
    price: float = 0.0          # alias for nifty_close
    prev_close: float = 0.0
    change_pct: float = 0.0     # alias for nifty_change
    day_high: float = 0.0
    day_low: float = 0.0
    volume: int = 0
    macd_histogram: float = 0.0
    bb_position: float = 0.5
    ema_9: float = 0.0
    ema_21: float = 0.0
    atr_14: float = 0.0
    returns_10d: float = 0.0
    news_sentiment: float = 0.0
    news_count: int = 0
    social_sentiment: float = 0.0
    social_post_count: int = 0
    social_trending: list = field(default_factory=list)
    ai_news_positive: int = 0
    ai_news_negative: int = 0
    india_vix_change_pct: float = 0.0
    pcr_oi: float = 0.0
    ad_ratio: float = 0.0
    global_signals: dict = field(default_factory=dict)
    sector_signals: dict = field(default_factory=dict)
    data_staleness: str = "stale"
    session: str = ""

    @property
    def instruments(self) -> dict:
        """Compatibility: old code expects snapshot.instruments['NIFTYBEES']."""
        self.price = self.nifty_close
        self.change_pct = self.nifty_change
        return {"NIFTYBEES": self}

    def to_bias_signals(self) -> dict:
        """Convert to dict for BiasPredictor."""
        return {
            "sp500_change": self.sp500_change,
            "india_vix": self.nse_vix if self.nse_vix > 0 else self.india_vix,
            "india_vix_change": self.nse_vix_change if self.nse_vix > 0 else self.india_vix_change,
            "crude_oil_change": self.crude_oil_change,
            "fii_net": self.fii_net,
            "usd_inr_change": self.usd_inr_change,
            "rsi_14": self.rsi_14,
            "returns_1d": self.returns_1d,
            "returns_5d": self.returns_5d,
            "volume_ratio": self.volume_ratio,
            "ad_ratio": self.ad_ratio,
            "ad_breadth_pct": self.ad_breadth_pct,
            "news_score": self.news_score,
            "news_bullish": self.news_bullish,
            "news_bearish": self.news_bearish,
            "news_total": self.news_total,
            "predicted_gap_pct": self.predicted_gap_pct,
            "gap_direction": self.gap_direction,
            "gap_confidence": self.gap_confidence,
            "fii_5d": self.fii_5d,
            "fii_10d": self.fii_10d,
            "fii_acceleration": self.fii_acceleration,
            "fii_consecutive": self.fii_consecutive,
            "fii_streak_direction": self.fii_streak_direction,
            "fii_momentum_score": self.fii_momentum_score,
        }

    def to_feature_dict(self) -> dict:
        """Compatibility: old code calls snap.to_feature_dict() for DB storage."""
        return self.to_db_dict()

    @property
    def feature_count(self) -> int:
        return len(self.to_db_dict())

    def to_db_dict(self) -> dict:
        """All fields for DB storage (future ML training)."""
        return {k: v for k, v in self.__dict__.items() if k != "errors"}


class SignalCollector:
    """Collects the 5 signals that matter + NIFTYBEES technicals."""

    def __init__(self) -> None:
        self._cache: dict = {}
        self._cache_ts: float = 0

    async def collect(self) -> SignalSnapshot:
        """Collect all signals. Takes ~2-3 seconds."""
        start = time.time()
        snap = SignalSnapshot(timestamp=start)

        # Global markets (parallel in thread pool)
        loop = asyncio.get_event_loop()
        global_data = await loop.run_in_executor(_executor, self._fetch_globals)

        snap.sp500_change = global_data.get("sp500_change", 0)
        snap.sp500_5d = global_data.get("sp500_5d", 0)
        snap.crude_oil_change = global_data.get("crude_oil_change", 0)
        snap.crude_oil_5d = global_data.get("crude_oil_5d", 0)
        snap.india_vix = global_data.get("india_vix_close", 0)
        snap.india_vix_change = global_data.get("india_vix_change", 0)
        snap.usd_inr_change = global_data.get("usd_inr_change", 0)
        snap.nifty_close = global_data.get("nifty50_close", 0)
        snap.nifty_change = global_data.get("nifty50_change", 0)

        # NIFTYBEES technicals
        tech = await loop.run_in_executor(_executor, self._fetch_technicals)
        snap.rsi_14 = tech.get("rsi_14", 50)
        snap.returns_1d = tech.get("returns_1d", 0)
        snap.returns_5d = tech.get("returns_5d", 0)
        snap.volume_ratio = tech.get("volume_ratio", 1)

        # Gap prediction (pre-market signal — S&P futures + Asian markets)
        try:
            from trade_plus.market_data.gap_predictor import predict_gap
            gap = await predict_gap()
            snap.predicted_gap_pct = gap.gap_pct
            snap.gap_direction = gap.direction
            snap.gap_confidence = gap.confidence
            snap.global_signals["gap_prediction"] = {
                "gap_pct": gap.gap_pct,
                "direction": gap.direction,
                "confidence": gap.confidence,
                "signals": gap.signals,
            }
        except Exception as e:
            snap.errors.append(f"gap_predictor: {e}")

        # News sentiment (free RSS feeds + financial lexicon)
        try:
            from trade_plus.market_data.news_sentiment import NewsFeedCollector
            if not hasattr(self, '_news_collector'):
                self._news_collector = NewsFeedCollector()
            news = await self._news_collector.collect()
            snap.news_score = news.score
            snap.news_magnitude = news.magnitude
            snap.news_bullish = news.bullish_count
            snap.news_bearish = news.bearish_count
            snap.news_total = news.total_articles
            snap.ai_news_sentiment = news.score  # backward compat with dashboard
            snap.ai_news_count = news.total_articles
        except Exception as e:
            snap.errors.append(f"news_sentiment: {e}")

        # FII/DII (NSE — old endpoint, kept as fallback)
        fii = await self._fetch_fii_dii()
        snap.fii_net = fii.get("fii_net", 0)
        snap.dii_net = fii.get("dii_net", 0)

        # FII cumulative momentum (5-day/10-day tracking)
        try:
            from trade_plus.market_data.fii_tracker import FIITracker
            if not hasattr(self, '_fii_tracker'):
                self._fii_tracker = FIITracker()
            if snap.fii_net != 0:
                self._fii_tracker.record(snap.fii_net, snap.dii_net)
            momentum = self._fii_tracker.get_momentum(snap.fii_net, snap.dii_net)
            snap.fii_5d = momentum.fii_5d
            snap.fii_10d = momentum.fii_10d
            snap.fii_acceleration = momentum.fii_acceleration
            snap.fii_consecutive = momentum.fii_consecutive
            snap.fii_streak_direction = momentum.fii_streak_direction
            snap.fii_momentum_signal = momentum.signal
            snap.fii_momentum_score = momentum.signal_score
        except Exception as e:
            snap.errors.append(f"fii_tracker: {e}")

        # Free API aggregator (NewsAPI + Reddit — if keys configured)
        try:
            from trade_plus.market_data.free_apis import FreeDataAggregator
            if not hasattr(self, '_free_apis'):
                self._free_apis = FreeDataAggregator()
            extra = await self._free_apis.collect_all()
            if extra.get("blended_score"):
                # Blend with RSS score (weighted average)
                rss_weight = 0.6
                api_weight = 0.4
                snap.news_score = round(
                    snap.news_score * rss_weight + extra["blended_score"] * api_weight, 4
                ) if snap.news_score else extra["blended_score"]
            snap.global_signals["free_apis"] = extra
        except Exception as e:
            snap.errors.append(f"free_apis: {e}")

        # NSE enhanced data: A/D ratio, live VIX, market status
        try:
            from trade_plus.market_data.nse_client import get_nse_client
            nse = get_nse_client()
            nse_data = await nse.collect_all_enhanced()
            if nse_data:
                snap.ad_ratio = nse_data.get("ad_ratio", 0)
                snap.ad_advances = nse_data.get("ad_advances", 0)
                snap.ad_declines = nse_data.get("ad_declines", 0)
                snap.ad_breadth_pct = nse_data.get("ad_breadth_pct", 0)
                snap.nse_vix = nse_data.get("nse_vix", 0)
                snap.nse_vix_change = nse_data.get("nse_vix_change", 0)
                snap.nifty_live = nse_data.get("nifty_live", 0)
                snap.banknifty_live = nse_data.get("banknifty_live", 0)
                snap.nifty_open = nse_data.get("nifty_open", 0)
                # Override FII/DII if NSE enhanced has it
                if nse_data.get("fii_net"):
                    snap.fii_net = nse_data["fii_net"]
                if nse_data.get("dii_net"):
                    snap.dii_net = nse_data["dii_net"]
                logger.info("nse_enhanced_collected",
                           ad_ratio=snap.ad_ratio, breadth=snap.ad_breadth_pct,
                           nse_vix=snap.nse_vix, nifty_live=snap.nifty_live)
        except Exception as e:
            snap.errors.append(f"nse_enhanced: {e}")

        snap.collection_time_ms = round((time.time() - start) * 1000, 1)

        logger.info("signals_collected",
                   sp500=snap.sp500_change, vix=snap.nse_vix or snap.india_vix,
                   crude=snap.crude_oil_change, fii=snap.fii_net,
                   rsi=snap.rsi_14, ad=snap.ad_ratio,
                   ms=snap.collection_time_ms)

        return snap

    def _fetch_globals(self) -> dict:
        """Fetch 5 global signals from yfinance."""
        import yfinance as yf
        results = {}
        for name, sym in GLOBAL_SYMBOLS.items():
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="10d")
                if len(hist) >= 2:
                    close = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2])
                    change = (close - prev) / prev * 100 if prev else 0
                    results[f"{name}_close"] = close
                    results[f"{name}_change"] = round(change, 3)
                    if len(hist) >= 6:
                        prev5 = float(hist["Close"].iloc[-6])
                        results[f"{name}_5d"] = round((close - prev5) / prev5 * 100, 3)
            except Exception:
                pass
        return results

    def _fetch_technicals(self) -> dict:
        """Compute NIFTYBEES daily technicals."""
        import yfinance as yf
        import numpy as np
        try:
            t = yf.Ticker(NIFTYBEES.yahoo_symbol)
            hist = t.history(period="30d", interval="1d")
            if len(hist) < 15:
                return {}
            close = hist["Close"].values.astype(float)
            volume = hist["Volume"].values.astype(float)

            # RSI 14
            delta = np.diff(close)
            gain = np.where(delta > 0, delta, 0)
            loss = np.where(delta < 0, -delta, 0)
            avg_gain = np.mean(gain[-14:])
            avg_loss = np.mean(loss[-14:])
            rs = avg_gain / (avg_loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))

            vol_avg = np.mean(volume[-20:]) if len(volume) >= 20 else np.mean(volume)
            vol_ratio = volume[-1] / vol_avg if vol_avg > 0 else 1

            return {
                "rsi_14": round(float(rsi), 1),
                "returns_1d": round((close[-1] / close[-2] - 1) * 100, 3),
                "returns_5d": round((close[-1] / close[-6] - 1) * 100, 3) if len(close) >= 6 else 0,
                "volume_ratio": round(float(vol_ratio), 2),
            }
        except Exception:
            return {}

    async def _fetch_fii_dii(self) -> dict:
        """Fetch FII/DII from NSE."""
        import httpx
        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/",
            }
            async with httpx.AsyncClient(headers=headers, timeout=10, follow_redirects=True) as client:
                await client.get("https://www.nseindia.com/", headers={**headers, "Accept": "text/html"})
                await asyncio.sleep(1.5)
                resp = await client.get("https://www.nseindia.com/api/fiidiiTradeReact")
                if resp.status_code == 200:
                    result = {}
                    for entry in resp.json():
                        cat = entry.get("category", "")
                        buy = float(entry.get("buyValue", 0))
                        sell = float(entry.get("sellValue", 0))
                        if "FII" in cat or "FPI" in cat:
                            result["fii_net"] = round(buy - sell, 2)
                        elif "DII" in cat:
                            result["dii_net"] = round(buy - sell, 2)
                    return result
        except Exception:
            pass
        return {}
