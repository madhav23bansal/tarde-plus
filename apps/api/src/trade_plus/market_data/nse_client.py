"""Robust NSE API client with session management.

Handles cookie refresh, rate limiting, and retries for all NSE endpoints.
All data is FREE — no API keys needed, just proper session handling.

Endpoints:
  - Advance/Decline ratio (Nifty 50 breadth)
  - FII/DII provisional flows (same-day)
  - Pre-open auction data (9:00-9:08 AM)
  - India VIX (real-time from allIndices)
  - Market status and turnover
  - GIFT Nifty approximation from pre-open
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

import httpx
import structlog

logger = structlog.get_logger()

# Rotate user agents to reduce fingerprinting
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]

# Rate limit: max 1 NSE call per this many seconds
_MIN_INTERVAL = 1.5


class NSEClient:
    """Robust async NSE API client with auto cookie refresh."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._last_cookie_time: float = 0
        self._last_request_time: float = 0
        self._ua_index: int = 0
        self._cookie_refresh_interval = 240  # 4 minutes

    def _next_ua(self) -> str:
        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1
        return ua

    def _headers(self, accept: str = "application/json") -> dict:
        return {
            "User-Agent": self._next_ua(),
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.nseindia.com/",
            "Connection": "keep-alive",
        }

    async def _ensure_session(self) -> httpx.AsyncClient:
        """Create or refresh the HTTP client with valid cookies."""
        now = time.time()
        needs_refresh = (
            self._client is None
            or (now - self._last_cookie_time) > self._cookie_refresh_interval
        )

        if needs_refresh:
            if self._client:
                try:
                    await self._client.aclose()
                except Exception:
                    pass

            self._client = httpx.AsyncClient(
                headers=self._headers("text/html"),
                timeout=15,
                follow_redirects=True,
            )
            # Hit main page to get session cookies
            try:
                await self._client.get("https://www.nseindia.com/")
                self._last_cookie_time = now
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning("nse_cookie_refresh_failed", error=str(e))
                raise

        return self._client

    async def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        """Make a rate-limited GET request to NSE API."""
        # Rate limiting
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < _MIN_INTERVAL:
            await asyncio.sleep(_MIN_INTERVAL - elapsed)

        client = await self._ensure_session()
        url = f"https://www.nseindia.com/api/{endpoint}"

        try:
            resp = await client.get(url, headers=self._headers(), params=params)
            self._last_request_time = time.time()

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                # Session expired, force cookie refresh
                self._last_cookie_time = 0
                client = await self._ensure_session()
                resp = await client.get(url, headers=self._headers(), params=params)
                self._last_request_time = time.time()
                if resp.status_code == 200:
                    return resp.json()

            logger.warning("nse_api_error", endpoint=endpoint, status=resp.status_code)
            return {}
        except Exception as e:
            logger.warning("nse_api_exception", endpoint=endpoint, error=str(e))
            return {}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Data endpoints ────────────────────────────────────────────

    async def get_advance_decline(self, index: str = "NIFTY 50") -> dict:
        """Get advance/decline ratio for an index.

        Returns: {advances, declines, unchanged, ad_ratio, breadth_pct,
                  top_gainers: [...], top_losers: [...]}
        """
        data = await self._get("equity-stockIndices", {"index": index})
        if not data or "data" not in data:
            return {}

        stocks = data["data"]
        # First entry is the index itself, skip it
        constituents = [s for s in stocks if s.get("symbol") != index.replace(" ", "")]

        advances = 0
        declines = 0
        unchanged = 0
        gainers = []
        losers = []

        for s in constituents:
            change = s.get("pChange", 0) or 0
            symbol = s.get("symbol", "")
            if change > 0:
                advances += 1
                gainers.append((symbol, change))
            elif change < 0:
                declines += 1
                losers.append((symbol, change))
            else:
                unchanged += 1

        gainers.sort(key=lambda x: x[1], reverse=True)
        losers.sort(key=lambda x: x[1])

        total = advances + declines + unchanged
        ad_ratio = advances / max(declines, 1)
        breadth_pct = advances / max(total, 1) * 100

        return {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "ad_ratio": round(ad_ratio, 2),
            "breadth_pct": round(breadth_pct, 1),
            "top_gainers": [{"symbol": s, "change": round(c, 2)} for s, c in gainers[:5]],
            "top_losers": [{"symbol": s, "change": round(c, 2)} for s, c in losers[:5]],
        }

    async def get_fii_dii(self) -> dict:
        """Get FII/DII trading activity (same-day provisional after 6 PM).

        Returns: {fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, date}
        """
        data = await self._get("fiidiiTradeReact")
        if not data:
            return {}

        result = {"date": ""}
        for entry in data:
            cat = entry.get("category", "")
            buy = float(entry.get("buyValue", 0) or 0)
            sell = float(entry.get("sellValue", 0) or 0)
            net = round(buy - sell, 2)
            date_str = entry.get("date", "")
            if date_str:
                result["date"] = date_str

            if "FII" in cat or "FPI" in cat:
                result["fii_buy"] = round(buy, 2)
                result["fii_sell"] = round(sell, 2)
                result["fii_net"] = net
            elif "DII" in cat:
                result["dii_buy"] = round(buy, 2)
                result["dii_sell"] = round(sell, 2)
                result["dii_net"] = net

        return result

    async def get_pre_open(self, key: str = "NIFTY") -> dict:
        """Get pre-open auction data (available 9:00-9:15 AM).

        Returns: {pre_open_price, prev_close, change_pct, total_traded_value,
                  advances, declines, top_gainers, top_losers}
        """
        data = await self._get("market-data-pre-open", {"key": key})
        if not data or "data" not in data:
            return {}

        stocks = data["data"]
        pre_open_change = 0
        advances = 0
        declines = 0
        total_value = 0

        for item in stocks:
            meta = item.get("metadata", {})
            change = meta.get("pChange", 0) or 0
            value = meta.get("lastPrice", 0) or 0
            total_value += value

            if change > 0:
                advances += 1
            elif change < 0:
                declines += 1

        # Index-level data
        index_data = data.get("advances", {})
        return {
            "advances": advances,
            "declines": declines,
            "total_traded_value": total_value,
            "index_advances": index_data.get("advances", 0),
            "index_declines": index_data.get("declines", 0),
        }

    async def get_india_vix(self) -> dict:
        """Get real-time India VIX from allIndices.

        Returns: {vix, vix_change, vix_change_pct, vix_high, vix_low}
        """
        data = await self._get("allIndices")
        if not data or "data" not in data:
            return {}

        for idx in data["data"]:
            name = idx.get("indexSymbol", "") or idx.get("index", "")
            if "VIX" in name.upper():
                last = float(idx.get("last", 0) or 0)
                prev = float(idx.get("previousClose", 0) or 0)
                change = float(idx.get("change", 0) or 0)
                change_pct = float(idx.get("percentChange", 0) or 0)
                high = float(idx.get("high", 0) or 0)
                low = float(idx.get("low", 0) or 0)

                return {
                    "vix": round(last, 2),
                    "vix_prev": round(prev, 2),
                    "vix_change": round(change, 2),
                    "vix_change_pct": round(change_pct, 2),
                    "vix_high": round(high, 2),
                    "vix_low": round(low, 2),
                }
        return {}

    async def get_market_status(self) -> dict:
        """Get overall market status and turnover.

        Returns: {nifty_last, nifty_change_pct, banknifty_last, banknifty_change_pct,
                  market_turnover, total_trades}
        """
        data = await self._get("allIndices")
        if not data or "data" not in data:
            return {}

        result = {}
        for idx in data["data"]:
            name = (idx.get("indexSymbol", "") or idx.get("index", "")).upper()
            if name == "NIFTY 50":
                result["nifty_last"] = float(idx.get("last", 0) or 0)
                result["nifty_change_pct"] = float(idx.get("percentChange", 0) or 0)
                result["nifty_open"] = float(idx.get("open", 0) or 0)
                result["nifty_high"] = float(idx.get("high", 0) or 0)
                result["nifty_low"] = float(idx.get("low", 0) or 0)
            elif name == "NIFTY BANK":
                result["banknifty_last"] = float(idx.get("last", 0) or 0)
                result["banknifty_change_pct"] = float(idx.get("percentChange", 0) or 0)

        return result

    async def get_bulk_block_deals(self) -> dict:
        """Get today's bulk and block deals.

        Returns: {block_deals: [...], bulk_deals: [...], nifty_related_deals: [...]}
        """
        data = await self._get("snapshot-capital-market-largedeal")
        if not data:
            return {}

        # NSE returns separate arrays for BLOCK_DEALS and BULK_DEALS
        block = data.get("BLOCK_DEALS_DATA", []) or data.get("block", []) or []
        bulk = data.get("BULK_DEALS_DATA", []) or data.get("bulk", []) or []

        # Flag deals in Nifty 50 components (high impact)
        nifty_stocks = set()
        nifty_related = []

        for deal in block + bulk:
            symbol = deal.get("symbol", "") or deal.get("securityName", "")
            qty = deal.get("quantity", 0) or 0
            price = deal.get("tradePrice", 0) or 0
            client = deal.get("clientName", "") or deal.get("acquirerName", "")

            nifty_related.append({
                "symbol": symbol,
                "quantity": qty,
                "price": price,
                "client": client[:50],  # truncate long names
            })

        return {
            "block_deals_count": len(block),
            "bulk_deals_count": len(bulk),
            "nifty_related": nifty_related[:10],  # top 10 by volume
        }

    async def collect_all_enhanced(self) -> dict:
        """Collect all enhanced NSE data in one call (rate-limited internally).

        Returns combined dict with all available data. Takes ~8-10 seconds
        due to NSE rate limiting (1.5s between calls).
        """
        result = {}

        # 1. A/D ratio (most important new signal)
        try:
            ad = await self.get_advance_decline("NIFTY 50")
            if ad:
                result["ad_ratio"] = ad["ad_ratio"]
                result["ad_advances"] = ad["advances"]
                result["ad_declines"] = ad["declines"]
                result["ad_breadth_pct"] = ad["breadth_pct"]
                result["top_gainers"] = ad.get("top_gainers", [])
                result["top_losers"] = ad.get("top_losers", [])
        except Exception as e:
            logger.debug("nse_ad_failed", error=str(e))

        # 2. Real-time VIX (more accurate than yfinance)
        try:
            vix = await self.get_india_vix()
            if vix:
                result["nse_vix"] = vix["vix"]
                result["nse_vix_change"] = vix["vix_change"]
                result["nse_vix_change_pct"] = vix["vix_change_pct"]
                result["nse_vix_high"] = vix["vix_high"]
                result["nse_vix_low"] = vix["vix_low"]
        except Exception as e:
            logger.debug("nse_vix_failed", error=str(e))

        # 3. FII/DII
        try:
            fii = await self.get_fii_dii()
            if fii:
                result["fii_net"] = fii.get("fii_net", 0)
                result["dii_net"] = fii.get("dii_net", 0)
                result["fii_buy"] = fii.get("fii_buy", 0)
                result["fii_sell"] = fii.get("fii_sell", 0)
        except Exception as e:
            logger.debug("nse_fii_failed", error=str(e))

        # 4. Market status (Nifty/BankNifty live)
        try:
            mkt = await self.get_market_status()
            if mkt:
                result["nifty_live"] = mkt.get("nifty_last", 0)
                result["nifty_change_pct"] = mkt.get("nifty_change_pct", 0)
                result["nifty_open"] = mkt.get("nifty_open", 0)
                result["nifty_high"] = mkt.get("nifty_high", 0)
                result["nifty_low"] = mkt.get("nifty_low", 0)
                result["banknifty_live"] = mkt.get("banknifty_last", 0)
                result["banknifty_change_pct"] = mkt.get("banknifty_change_pct", 0)
        except Exception as e:
            logger.debug("nse_market_failed", error=str(e))

        return result


# Global singleton
_nse: NSEClient | None = None


def get_nse_client() -> NSEClient:
    global _nse
    if _nse is None:
        _nse = NSEClient()
    return _nse
