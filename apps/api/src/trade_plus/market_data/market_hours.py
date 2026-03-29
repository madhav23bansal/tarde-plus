"""Indian market hours and session management.

Handles:
  - NSE equity hours (9:15 AM - 3:30 PM IST)
  - Pre-open session (9:00 - 9:08 AM)
  - MCX commodity hours (for gold/silver reference)
  - MIS auto-square-off deadline (3:20 PM on Zerodha)
  - Holidays
  - Weekend detection
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class MarketSession(Enum):
    PRE_MARKET = "pre_market"          # Before 9:00 AM — collect signals, prepare
    PRE_OPEN = "pre_open"              # 9:00 - 9:15 AM — pre-open auction
    REGULAR = "regular"                # 9:15 AM - 3:30 PM — active trading
    CLOSING = "closing"                # 3:30 - 4:00 PM — closing session
    POST_MARKET = "post_market"        # After 4:00 PM — EOD processing
    CLOSED = "closed"                  # Weekend / holiday


# ─── Time Constants ──────────────────────────────────────────────

PRE_OPEN_START = time(9, 0)
MARKET_OPEN = time(9, 15)
# Start winding down — square off MIS positions
MIS_SQUAREOFF_DEADLINE = time(15, 15)   # 3:15 PM (Zerodha does it at 3:20, we do 5 min early)
MARKET_CLOSE = time(15, 30)
CLOSING_SESSION_END = time(16, 0)

# When to start collecting signals for the day
SIGNAL_COLLECTION_START = time(8, 0)    # 8:00 AM — US markets closed, data available

# When to stop opening new positions
NO_NEW_POSITIONS_AFTER = time(14, 45)   # 2:45 PM — too close to close for new trades

# MCX commodity trading (gold/silver reference prices)
MCX_OPEN = time(9, 0)
MCX_CLOSE = time(23, 30)               # 11:30 PM


# ─── 2026 NSE Holidays (update annually) ────────────────────────
# Source: https://www.nseindia.com/market-data/trading-holiday-calendar

NSE_HOLIDAYS_2026 = {
    # Format: (month, day)
    # Source: NSE India official + Zerodha/Groww/ClearTax cross-verified
    (1, 15),   # Municipal Corporation Elections, Maharashtra
    (1, 26),   # Republic Day
    (3, 3),    # Holi
    (3, 26),   # Shri Ram Navami
    (3, 31),   # Shri Mahavir Jayanti
    (4, 3),    # Good Friday
    (4, 14),   # Dr. Ambedkar Jayanti
    (5, 1),    # Maharashtra Day
    (5, 28),   # Bakri Eid (Eid ul-Adha)
    (6, 26),   # Moharram
    (9, 14),   # Ganesh Chaturthi
    (10, 2),   # Mahatma Gandhi Jayanti
    (10, 20),  # Dussehra
    (11, 10),  # Diwali Balipratipada
    (11, 24),  # Prakash Gurpurb Sri Guru Nanak Dev
    (12, 25),  # Christmas
}


def now_ist() -> datetime:
    """Current time in IST."""
    return datetime.now(IST)


def is_holiday(dt: datetime | None = None) -> bool:
    """Check if a date is an NSE holiday."""
    dt = dt or now_ist()
    return (dt.month, dt.day) in NSE_HOLIDAYS_2026


def is_weekend(dt: datetime | None = None) -> bool:
    dt = dt or now_ist()
    return dt.weekday() >= 5  # Saturday=5, Sunday=6


def is_trading_day(dt: datetime | None = None) -> bool:
    """Is NSE open on this date?"""
    dt = dt or now_ist()
    return not is_weekend(dt) and not is_holiday(dt)


def get_session(dt: datetime | None = None) -> MarketSession:
    """Determine current market session."""
    dt = dt or now_ist()
    t = dt.time()

    if is_weekend(dt) or is_holiday(dt):
        return MarketSession.CLOSED

    if t < PRE_OPEN_START:
        return MarketSession.PRE_MARKET
    elif t < MARKET_OPEN:
        return MarketSession.PRE_OPEN
    elif t < MARKET_CLOSE:
        return MarketSession.REGULAR
    elif t < CLOSING_SESSION_END:
        return MarketSession.CLOSING
    else:
        return MarketSession.POST_MARKET


def can_trade(dt: datetime | None = None) -> bool:
    """Can we place new orders right now?"""
    return get_session(dt) == MarketSession.REGULAR


def should_collect_signals(dt: datetime | None = None) -> bool:
    """Should we be collecting prediction signals?"""
    dt = dt or now_ist()
    t = dt.time()
    if not is_trading_day(dt):
        return False
    return SIGNAL_COLLECTION_START <= t <= MARKET_CLOSE


def should_squareoff(dt: datetime | None = None) -> bool:
    """Should we be squaring off MIS positions?"""
    dt = dt or now_ist()
    t = dt.time()
    return can_trade(dt) and t >= MIS_SQUAREOFF_DEADLINE


def can_open_new_position(dt: datetime | None = None) -> bool:
    """Is it still early enough to open new positions?"""
    dt = dt or now_ist()
    t = dt.time()
    return can_trade(dt) and t < NO_NEW_POSITIONS_AFTER


def next_trading_day(dt: datetime | None = None) -> datetime:
    """Find the next trading day."""
    dt = dt or now_ist()
    candidate = dt + timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate.replace(hour=9, minute=15, second=0, microsecond=0)


def time_to_market_open(dt: datetime | None = None) -> timedelta | None:
    """Time remaining until market opens. None if already open or past close."""
    dt = dt or now_ist()
    session = get_session(dt)
    if session == MarketSession.REGULAR:
        return timedelta(0)
    if session in (MarketSession.PRE_MARKET, MarketSession.PRE_OPEN):
        open_dt = dt.replace(hour=9, minute=15, second=0, microsecond=0)
        return open_dt - dt
    # Market closed for the day or weekend/holiday
    nxt = next_trading_day(dt)
    return nxt - dt


def market_status_summary(dt: datetime | None = None) -> dict:
    """Full status for display/logging."""
    dt = dt or now_ist()
    session = get_session(dt)
    ttl = time_to_market_open(dt)

    return {
        "time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        "session": session.value,
        "is_trading_day": is_trading_day(dt),
        "can_trade": can_trade(dt),
        "can_open_new": can_open_new_position(dt),
        "should_squareoff": should_squareoff(dt),
        "should_collect_signals": should_collect_signals(dt),
        "time_to_open": str(ttl) if ttl else "N/A",
        "is_holiday": is_holiday(dt),
    }
