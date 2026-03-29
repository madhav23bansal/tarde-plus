"""NSE India market data provider.

Provides real-time equity quotes, option chains, indices, and pre-open data.
Handles cookie-based session management required by NSE website APIs.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from trade_plus.market_data.base import (
    OHLCV,
    LiveQuote,
    MarketDataProvider,
    OptionChain,
    OptionChainEntry,
)

logger = structlog.get_logger()

BASE_URL = "https://www.nseindia.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

# Minimum seconds between requests to avoid rate limiting
REQUEST_INTERVAL = 1.5


class NSEProvider(MarketDataProvider):
    """Free market data from NSE India website APIs.

    Best source for: option chains, index data, pre-open market.
    Requires careful session/cookie management.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._last_cookie_refresh: float = 0.0
        self._last_request_time: float = 0.0
        self._cookie_lifetime = 300  # refresh cookies every 5 min

    @property
    def name(self) -> str:
        return "nse_india"

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=httpx.Timeout(15.0, connect=10.0),
                follow_redirects=True,
            )
        # Refresh cookies if stale
        if time.time() - self._last_cookie_refresh > self._cookie_lifetime:
            await self._refresh_cookies()
        return self._client

    async def _refresh_cookies(self) -> None:
        """Hit NSE homepage to get fresh session cookies."""
        if self._client is None:
            return
        try:
            resp = await self._client.get(
                BASE_URL,
                headers={
                    **HEADERS,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            self._last_cookie_refresh = time.time()
            logger.debug("nse_cookies_refreshed", status=resp.status_code)
        except Exception as e:
            logger.warning("nse_cookie_refresh_failed", error=str(e))

    async def _rate_limit(self) -> None:
        """Ensure we don't hit NSE too frequently."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_INTERVAL:
            await asyncio.sleep(REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Make a rate-limited GET request to NSE API."""
        client = await self._ensure_client()
        await self._rate_limit()

        url = f"{BASE_URL}{path}"
        resp = await client.get(url, params=params)

        if resp.status_code == 403:
            # Cookie expired, try refreshing
            logger.debug("nse_403_refreshing_cookies")
            await self._refresh_cookies()
            await self._rate_limit()
            resp = await client.get(url, params=params)

        resp.raise_for_status()
        return resp.json()

    async def get_quote(self, symbol: str) -> LiveQuote:
        """Get equity quote from NSE.

        Symbol format: NSE:RELIANCE -> RELIANCE
        """
        ticker = symbol.split(":")[-1] if ":" in symbol else symbol

        data = await self._get("/api/quote-equity", params={"symbol": ticker})

        price_info = data.get("priceInfo", {})
        ltp = price_info.get("lastPrice", 0)
        prev_close = price_info.get("previousClose", 0)
        change = price_info.get("change", 0)
        change_pct = price_info.get("pChange", 0)

        intra = price_info.get("intraDayHighLow", {})

        return LiveQuote(
            instrument=f"NSE:{ticker}",
            ltp=float(ltp),
            open=float(price_info.get("open", 0)),
            high=float(intra.get("max", 0)),
            low=float(intra.get("min", 0)),
            close=float(prev_close),
            volume=int(data.get("securityWiseDP", {}).get("quantityTraded", 0)),
            change=float(change),
            change_pct=float(change_pct),
            timestamp=time.time(),
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, LiveQuote]:
        """Get quotes for multiple symbols (sequential due to rate limiting)."""
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = await self.get_quote(symbol)
            except Exception as e:
                logger.warning("nse_quote_failed", symbol=symbol, error=str(e))
        return results

    async def get_historical(
        self,
        symbol: str,
        interval: str = "1d",
        range_str: str = "1y",
    ) -> list[OHLCV]:
        """Get daily historical data from NSE.

        Note: NSE only provides daily data via this endpoint.
        For intraday historical, use Yahoo Finance.
        """
        ticker = symbol.split(":")[-1] if ":" in symbol else symbol

        # Calculate date range
        from datetime import datetime, timedelta
        end = datetime.now()
        range_map = {
            "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825,
        }
        days = range_map.get(range_str, 365)
        start = end - timedelta(days=days)

        data = await self._get(
            "/api/historical/cm/equity",
            params={
                "symbol": ticker,
                "series": "EQ",
                "from": start.strftime("%d-%m-%Y"),
                "to": end.strftime("%d-%m-%Y"),
            },
        )

        bars = []
        for row in data.get("data", []):
            try:
                from datetime import datetime as dt
                ts = dt.strptime(row["CH_TIMESTAMP"], "%Y-%m-%d").timestamp()
                bars.append(OHLCV(
                    timestamp=ts,
                    open=float(row.get("CH_OPENING_PRICE", 0)),
                    high=float(row.get("CH_TRADE_HIGH_PRICE", 0)),
                    low=float(row.get("CH_TRADE_LOW_PRICE", 0)),
                    close=float(row.get("CH_CLOSING_PRICE", 0)),
                    volume=int(row.get("CH_TOT_TRADED_QTY", 0)),
                    instrument=f"NSE:{ticker}",
                ))
            except (KeyError, ValueError) as e:
                continue

        logger.info("nse_historical", symbol=symbol, bars=len(bars))
        return bars

    # --- NSE-specific endpoints ---

    async def get_option_chain(self, symbol: str, is_index: bool = True) -> OptionChain:
        """Get full option chain for an equity or index.

        This is the best free source for Indian F&O data.
        """
        if is_index:
            data = await self._get(
                "/api/option-chain-indices",
                params={"symbol": symbol},
            )
        else:
            data = await self._get(
                "/api/option-chain-equities",
                params={"symbol": symbol},
            )

        records = data.get("records", {})
        filtered = data.get("filtered", {})

        spot = records.get("underlyingValue", 0)
        expiry_dates = records.get("expiryDates", [])

        entries = []
        for row in filtered.get("data", []):
            ce = row.get("CE", {})
            pe = row.get("PE", {})
            strike = row.get("strikePrice", 0)
            expiry = ce.get("expiryDate", pe.get("expiryDate", ""))

            entries.append(OptionChainEntry(
                strike=float(strike),
                expiry=expiry,
                ce_ltp=float(ce.get("lastPrice", 0)),
                ce_oi=int(ce.get("openInterest", 0)),
                ce_volume=int(ce.get("totalTradedVolume", 0)),
                ce_iv=float(ce.get("impliedVolatility", 0)),
                ce_bid=float(ce.get("bidprice", 0)),
                ce_ask=float(ce.get("askPrice", 0)),
                pe_ltp=float(pe.get("lastPrice", 0)),
                pe_oi=int(pe.get("openInterest", 0)),
                pe_volume=int(pe.get("totalTradedVolume", 0)),
                pe_iv=float(pe.get("impliedVolatility", 0)),
                pe_bid=float(pe.get("bidprice", 0)),
                pe_ask=float(pe.get("askPrice", 0)),
            ))

        logger.info(
            "nse_option_chain",
            symbol=symbol,
            spot=spot,
            entries=len(entries),
            expiries=len(expiry_dates),
        )

        return OptionChain(
            symbol=symbol,
            spot_price=float(spot),
            expiry_dates=expiry_dates,
            entries=entries,
            timestamp=time.time(),
        )

    async def get_all_indices(self) -> list[dict]:
        """Get all NSE indices with current values."""
        data = await self._get("/api/allIndices")
        return data.get("data", [])

    async def get_market_status(self) -> dict:
        """Check if market is open/closed."""
        return await self._get("/api/marketStatus")

    async def get_pre_open(self, key: str = "NIFTY") -> list[dict]:
        """Get pre-open market data (9:00-9:08 AM session)."""
        data = await self._get("/api/market-data-pre-open", params={"key": key})
        return data.get("data", [])

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
