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

    # Parallel AI sentiment (morning fetch, cached)
    ai_news_sentiment: float = 0.0
    ai_news_count: int = 0

    # Collection metadata
    collection_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_bias_signals(self) -> dict:
        """Convert to dict for BiasPredictor."""
        return {
            "sp500_change": self.sp500_change,
            "india_vix": self.india_vix,
            "crude_oil_change": self.crude_oil_change,
            "fii_net": self.fii_net,
            "usd_inr_change": self.usd_inr_change,
            "rsi_14": self.rsi_14,
            "returns_1d": self.returns_1d,
            "returns_5d": self.returns_5d,
            "volume_ratio": self.volume_ratio,
        }

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

        # FII/DII (NSE)
        fii = await self._fetch_fii_dii()
        snap.fii_net = fii.get("fii_net", 0)
        snap.dii_net = fii.get("dii_net", 0)

        snap.collection_time_ms = round((time.time() - start) * 1000, 1)

        logger.info("signals_collected",
                   sp500=snap.sp500_change, vix=snap.india_vix,
                   crude=snap.crude_oil_change, fii=snap.fii_net,
                   rsi=snap.rsi_14, ms=snap.collection_time_ms)

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
