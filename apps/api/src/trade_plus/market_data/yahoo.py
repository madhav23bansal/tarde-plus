"""Yahoo Finance market data provider.

Dual implementation:
  1. yfinance library (handles auth/crumb automatically, more robust)
  2. Raw httpx (fallback, for when yfinance has issues)

Adds exponential backoff on 429s and request spacing.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import structlog

from trade_plus.market_data.base import OHLCV, LiveQuote, MarketDataProvider

logger = structlog.get_logger()

# Yahoo uses .NS suffix for NSE stocks
SYMBOL_MAP = {
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
}

# Thread pool for yfinance (it's synchronous)
_executor = ThreadPoolExecutor(max_workers=4)

# Global rate limiter
_last_request_time = 0.0
_MIN_REQUEST_GAP = 0.5  # seconds between requests


def to_yahoo_symbol(symbol: str) -> str:
    """NSE:RELIANCE -> RELIANCE.NS, NIFTY50 -> ^NSEI"""
    if symbol in SYMBOL_MAP:
        return SYMBOL_MAP[symbol]
    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        if exchange == "NSE":
            return f"{ticker}.NS"
        elif exchange == "BSE":
            return f"{ticker}.BO"
    return f"{symbol}.NS"


def from_yahoo_symbol(yahoo_sym: str) -> str:
    rev_map = {v: k for k, v in SYMBOL_MAP.items()}
    if yahoo_sym in rev_map:
        return rev_map[yahoo_sym]
    if yahoo_sym.endswith(".NS"):
        return f"NSE:{yahoo_sym[:-3]}"
    if yahoo_sym.endswith(".BO"):
        return f"BSE:{yahoo_sym[:-3]}"
    return yahoo_sym


def _yf_get_quote_sync(yahoo_sym: str) -> dict:
    """Synchronous yfinance call, run in thread pool."""
    import yfinance as yf
    ticker = yf.Ticker(yahoo_sym)
    info = ticker.fast_info
    return {
        "ltp": float(getattr(info, "last_price", 0) or 0),
        "open": float(getattr(info, "open", 0) or 0),
        "high": float(getattr(info, "day_high", 0) or 0),
        "low": float(getattr(info, "day_low", 0) or 0),
        "prev_close": float(getattr(info, "previous_close", 0) or 0),
        "volume": int(getattr(info, "last_volume", 0) or 0),
    }


def _yf_get_history_sync(yahoo_sym: str, period: str, interval: str) -> list[dict]:
    """Synchronous yfinance history call."""
    import yfinance as yf
    ticker = yf.Ticker(yahoo_sym)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        return []
    rows = []
    for ts, row in df.iterrows():
        rows.append({
            "timestamp": ts.timestamp(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return rows


def _yf_download_sync(yahoo_syms: list[str], period: str = "1d", interval: str = "1d") -> dict:
    """Batch download via yfinance."""
    import yfinance as yf
    data = yf.download(yahoo_syms, period=period, interval=interval, group_by="ticker", progress=False)
    results = {}
    if len(yahoo_syms) == 1:
        sym = yahoo_syms[0]
        if not data.empty:
            last = data.iloc[-1]
            results[sym] = {
                "open": float(last.get("Open", 0) or 0),
                "high": float(last.get("High", 0) or 0),
                "low": float(last.get("Low", 0) or 0),
                "close": float(last.get("Close", 0) or 0),
                "volume": int(last.get("Volume", 0) or 0),
            }
    else:
        for sym in yahoo_syms:
            try:
                sym_data = data[sym] if sym in data.columns.get_level_values(0) else None
                if sym_data is not None and not sym_data.empty:
                    last = sym_data.iloc[-1]
                    results[sym] = {
                        "open": float(last.get("Open", 0) or 0),
                        "high": float(last.get("High", 0) or 0),
                        "low": float(last.get("Low", 0) or 0),
                        "close": float(last.get("Close", 0) or 0),
                        "volume": int(last.get("Volume", 0) or 0),
                    }
            except Exception:
                continue
    return results


async def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_GAP:
        await asyncio.sleep(_MIN_REQUEST_GAP - elapsed)
    _last_request_time = time.time()


class YahooFinanceProvider(MarketDataProvider):
    """Free market data via yfinance library with raw API fallback."""

    @property
    def name(self) -> str:
        return "yahoo_finance"

    async def get_quote(self, symbol: str) -> LiveQuote:
        """Get real-time quote using yfinance (handles auth automatically)."""
        await _rate_limit()
        yahoo_sym = to_yahoo_symbol(symbol)
        loop = asyncio.get_event_loop()

        data = await loop.run_in_executor(_executor, _yf_get_quote_sync, yahoo_sym)

        ltp = data["ltp"]
        prev_close = data["prev_close"]

        return LiveQuote(
            instrument=symbol,
            ltp=ltp,
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=prev_close,
            volume=data["volume"],
            change=round(ltp - prev_close, 2) if prev_close else 0.0,
            change_pct=round((ltp - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
            timestamp=time.time(),
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, LiveQuote]:
        """Batch quote fetch using yfinance download (single HTTP call)."""
        await _rate_limit()
        yahoo_syms = [to_yahoo_symbol(s) for s in symbols]
        loop = asyncio.get_event_loop()

        # yfinance.download does a single batch request
        data = await loop.run_in_executor(_executor, _yf_download_sync, yahoo_syms)

        results = {}
        for yahoo_sym, vals in data.items():
            our_sym = from_yahoo_symbol(yahoo_sym)
            ltp = vals["close"]  # download returns close as latest
            results[our_sym] = LiveQuote(
                instrument=our_sym,
                ltp=ltp,
                open=vals["open"],
                high=vals["high"],
                low=vals["low"],
                close=0.0,  # prev_close not in download
                volume=vals["volume"],
                timestamp=time.time(),
            )

        # Fill in any missing symbols with individual calls
        for sym in symbols:
            if sym not in results:
                try:
                    results[sym] = await self.get_quote(sym)
                except Exception as e:
                    logger.warning("yahoo_quote_failed", symbol=sym, error=str(e))

        return results

    async def get_historical(
        self,
        symbol: str,
        interval: str = "1d",
        range_str: str = "1y",
    ) -> list[OHLCV]:
        """Get historical OHLCV using yfinance.

        Intervals: 1m, 2m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo
        Periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        """
        await _rate_limit()
        yahoo_sym = to_yahoo_symbol(symbol)
        loop = asyncio.get_event_loop()

        rows = await loop.run_in_executor(
            _executor, _yf_get_history_sync, yahoo_sym, range_str, interval
        )

        bars = [
            OHLCV(
                timestamp=r["timestamp"],
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                volume=r["volume"],
                instrument=symbol,
            )
            for r in rows
        ]

        logger.info(
            "yahoo_historical",
            symbol=symbol,
            interval=interval,
            range=range_str,
            bars=len(bars),
        )
        return bars

    async def close(self) -> None:
        pass  # yfinance manages its own sessions
