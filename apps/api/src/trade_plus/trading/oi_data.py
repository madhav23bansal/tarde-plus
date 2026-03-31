"""Open Interest data collector for multiple indices.

Fetches OI from NSE option chain for NIFTY and BANKNIFTY.
Each returns: highest Call/Put OI strikes, Max Pain, PCR, OI change direction.
Called every 5 minutes during market hours.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

logger = structlog.get_logger()

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


async def fetch_index_oi(index_symbol: str = "NIFTY") -> dict:
    """Fetch option chain OI data for any NSE index.

    Args:
        index_symbol: "NIFTY" or "BANKNIFTY"

    Returns dict with: oi_resistance, oi_support, max_pain, pcr, etc.
    """
    try:
        async with httpx.AsyncClient(headers=NSE_HEADERS, timeout=15, follow_redirects=True) as client:
            await client.get("https://www.nseindia.com/", headers={**NSE_HEADERS, "Accept": "text/html"})
            await asyncio.sleep(1.5)

            resp = await client.get(
                f"https://www.nseindia.com/api/option-chain-indices?symbol={index_symbol}"
            )
            if resp.status_code != 200:
                logger.warning("oi_fetch_failed", index=index_symbol, status=resp.status_code)
                return {}

            data = resp.json()
            records = data.get("records", {})
            filtered = data.get("filtered", {})
            spot = records.get("underlyingValue", 0)

            if not spot or not filtered.get("data"):
                return {"index": index_symbol, "spot": spot, "empty": True}

            max_call_oi = max_call_strike = max_put_oi = max_put_strike = 0
            total_call_oi = total_put_oi = total_call_chg = total_put_chg = 0
            strikes = []

            for row in filtered["data"]:
                ce = row.get("CE", {})
                pe = row.get("PE", {})
                strike = row.get("strikePrice", 0)
                ce_oi = ce.get("openInterest", 0)
                pe_oi = pe.get("openInterest", 0)
                ce_chg = ce.get("changeinOpenInterest", 0)
                pe_chg = pe.get("changeinOpenInterest", 0)

                total_call_oi += ce_oi
                total_put_oi += pe_oi
                total_call_chg += ce_chg
                total_put_chg += pe_chg

                if ce_oi > max_call_oi:
                    max_call_oi = ce_oi
                    max_call_strike = strike
                if pe_oi > max_put_oi:
                    max_put_oi = pe_oi
                    max_put_strike = strike

                strikes.append({"strike": strike, "call_oi": ce_oi, "put_oi": pe_oi})

            # Max Pain
            max_pain_strike = 0
            min_pain_value = float("inf")
            for ep in [s["strike"] for s in strikes]:
                pain = sum(
                    max(0, ep - s["strike"]) * s["call_oi"] + max(0, s["strike"] - ep) * s["put_oi"]
                    for s in strikes
                )
                if pain < min_pain_value:
                    min_pain_value = pain
                    max_pain_strike = ep

            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

            # OI buildup direction
            oi_buildup = "neutral"
            if total_call_chg > total_put_chg * 1.5:
                oi_buildup = "bearish"
            elif total_put_chg > total_call_chg * 1.5:
                oi_buildup = "bullish"

            result = {
                "index": index_symbol,
                "spot": spot,
                "oi_resistance": max_call_strike,
                "oi_support": max_put_strike,
                "max_pain": max_pain_strike,
                "pcr": round(pcr, 3),
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "oi_buildup": oi_buildup,
                "timestamp": time.time(),
            }

            logger.info("oi_fetched", index=index_symbol, spot=spot,
                       resistance=max_call_strike, support=max_put_strike,
                       pcr=round(pcr, 2), buildup=oi_buildup)
            return result

    except Exception as e:
        logger.warning("oi_fetch_error", index=index_symbol, error=str(e))
        return {}


async def fetch_all_oi(indices: list[str]) -> dict[str, dict]:
    """Fetch OI for multiple indices. Returns {index_symbol: oi_data}.

    Rate-limited: 1.5s between NSE calls.
    """
    results = {}
    for idx in indices:
        data = await fetch_index_oi(idx)
        if data and not data.get("empty"):
            results[idx] = data
        await asyncio.sleep(1.5)  # NSE rate limit
    return results
