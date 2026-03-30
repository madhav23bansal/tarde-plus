"""Nifty Open Interest data collector.

Fetches OI from NSE option chain every 5 minutes during market hours.
Extracts:
  - Highest Call OI strike (resistance wall)
  - Highest Put OI strike (support wall)
  - Max Pain strike
  - PCR (Put-Call Ratio)
  - OI change direction (building/unwinding)
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


async def fetch_nifty_oi() -> dict:
    """Fetch Nifty option chain OI data from NSE.

    Returns dict with: oi_resistance, oi_support, max_pain, pcr,
    top_call_strikes, top_put_strikes, total_call_oi, total_put_oi
    """
    try:
        async with httpx.AsyncClient(headers=NSE_HEADERS, timeout=15, follow_redirects=True) as client:
            # Get cookies
            await client.get("https://www.nseindia.com/", headers={**NSE_HEADERS, "Accept": "text/html"})
            await asyncio.sleep(1.5)

            resp = await client.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY")
            if resp.status_code != 200:
                logger.warning("oi_fetch_failed", status=resp.status_code)
                return {}

            data = resp.json()
            records = data.get("records", {})
            filtered = data.get("filtered", {})
            spot = records.get("underlyingValue", 0)

            if not spot or not filtered.get("data"):
                return {"spot": spot, "empty": True}

            max_call_oi = 0
            max_call_strike = 0
            max_put_oi = 0
            max_put_strike = 0
            total_call_oi = 0
            total_put_oi = 0
            total_call_chg = 0
            total_put_chg = 0

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

                strikes.append({
                    "strike": strike,
                    "call_oi": ce_oi, "put_oi": pe_oi,
                    "call_chg": ce_chg, "put_chg": pe_chg,
                })

            # Max Pain calculation
            max_pain_strike = 0
            min_pain_value = float("inf")
            for expiry_price in [s["strike"] for s in strikes]:
                total_pain = 0
                for s in strikes:
                    call_itm = max(0, expiry_price - s["strike"])
                    total_pain += call_itm * s["call_oi"]
                    put_itm = max(0, s["strike"] - expiry_price)
                    total_pain += put_itm * s["put_oi"]
                if total_pain < min_pain_value:
                    min_pain_value = total_pain
                    max_pain_strike = expiry_price

            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

            # OI change direction
            oi_buildup = "neutral"
            if total_call_chg > total_put_chg * 1.5:
                oi_buildup = "bearish"  # more call writing = resistance building
            elif total_put_chg > total_call_chg * 1.5:
                oi_buildup = "bullish"  # more put writing = support building

            result = {
                "spot": spot,
                "oi_resistance": max_call_strike,
                "oi_resistance_oi": max_call_oi,
                "oi_support": max_put_strike,
                "oi_support_oi": max_put_oi,
                "max_pain": max_pain_strike,
                "pcr": round(pcr, 3),
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "call_oi_change": total_call_chg,
                "put_oi_change": total_put_chg,
                "oi_buildup": oi_buildup,
                "timestamp": time.time(),
            }

            logger.info("oi_fetched", spot=spot, resistance=max_call_strike,
                       support=max_put_strike, max_pain=max_pain_strike, pcr=round(pcr, 2),
                       buildup=oi_buildup)

            return result

    except Exception as e:
        logger.warning("oi_fetch_error", error=str(e))
        return {}
