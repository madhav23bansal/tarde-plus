"""Trade history — persists daily results with precise P&L calculations.

Stores per-day trade logs in JSON for manual examination.
Calculates actual invested amount (not full capital) for accurate returns.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog

logger = structlog.get_logger()

IST = ZoneInfo("Asia/Kolkata")
_HISTORY_DIR = Path(__file__).resolve().parents[3] / "data" / "trade_history"


def save_daily_result(trader, closed_trades: list[dict], day_date: date | None = None) -> dict:
    """Save complete daily trading result with precise calculations.

    Args:
        trader: PaperTrader instance
        closed_trades: list of closed trade dicts from trader
        day_date: override date (defaults to today IST)

    Returns: summary dict
    """
    if day_date is None:
        day_date = datetime.now(IST).date()

    date_str = day_date.isoformat()

    # Calculate actual amounts invested (not full capital)
    total_invested = 0.0
    total_gross_pnl = 0.0
    total_charges = 0.0
    total_net_pnl = 0.0
    trades = []

    for t in closed_trades:
        entry_value = t["entry_price"] * t["quantity"]
        exit_value = t["exit_price"] * t["quantity"]
        total_invested += entry_value
        total_gross_pnl += t.get("gross_pnl", 0)
        total_charges += t.get("charges", 0)
        total_net_pnl += t.get("net_pnl", 0)

        hold_seconds = t.get("exit_time", 0) - t.get("entry_time", 0)
        hold_minutes = round(hold_seconds / 60, 1) if hold_seconds > 0 else 0

        trades.append({
            "instrument": t["instrument"],
            "side": t["side"],
            "quantity": t["quantity"],
            "entry_price": round(t["entry_price"], 2),
            "exit_price": round(t["exit_price"], 2),
            "entry_value": round(entry_value, 2),
            "exit_value": round(exit_value, 2),
            "gross_pnl": round(t.get("gross_pnl", 0), 2),
            "charges": round(t.get("charges", 0), 2),
            "net_pnl": round(t.get("net_pnl", 0), 2),
            "return_pct": round(t.get("net_pnl", 0) / entry_value * 100, 4) if entry_value > 0 else 0,
            "hold_minutes": hold_minutes,
            "reason": t.get("reason", ""),
            "entry_time": datetime.fromtimestamp(t.get("entry_time", 0), IST).strftime("%H:%M:%S") if t.get("entry_time") else "",
            "exit_time": datetime.fromtimestamp(t.get("exit_time", 0), IST).strftime("%H:%M:%S") if t.get("exit_time") else "",
        })

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t["net_pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["net_pnl"] for t in losses) / len(losses) if losses else 0

    summary = {
        "date": date_str,
        "day_of_week": day_date.strftime("%A"),
        "starting_capital": round(trader.starting_capital, 2),
        "ending_capital": round(trader.capital, 2),
        "total_invested": round(total_invested, 2),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "gross_pnl": round(total_gross_pnl, 2),
        "total_charges": round(total_charges, 2),
        "net_pnl": round(total_net_pnl, 2),
        "return_on_invested_pct": round(total_net_pnl / total_invested * 100, 4) if total_invested > 0 else 0,
        "return_on_capital_pct": round(total_net_pnl / trader.starting_capital * 100, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "risk_reward": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
        "max_drawdown_pct": round(trader.max_drawdown * 100, 2),
        "trades": trades,
    }

    # Save to file
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _HISTORY_DIR / f"{date_str}.json"
    file_path.write_text(json.dumps(summary, indent=2))
    logger.info("daily_result_saved", date=date_str, trades=len(trades),
                net_pnl=total_net_pnl, file=str(file_path))

    return summary


def get_daily_result(day_date: date | str) -> dict | None:
    """Load a specific day's results."""
    if isinstance(day_date, str):
        date_str = day_date
    else:
        date_str = day_date.isoformat()

    file_path = _HISTORY_DIR / f"{date_str}.json"
    if file_path.exists():
        return json.loads(file_path.read_text())
    return None


def get_all_results() -> list[dict]:
    """Load all daily results, sorted by date."""
    if not _HISTORY_DIR.exists():
        return []

    results = []
    for f in sorted(_HISTORY_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            # Return summary without individual trades for the list view
            results.append({
                "date": data["date"],
                "day_of_week": data.get("day_of_week", ""),
                "total_trades": data["total_trades"],
                "wins": data["wins"],
                "losses": data["losses"],
                "win_rate_pct": data["win_rate_pct"],
                "net_pnl": data["net_pnl"],
                "total_charges": data["total_charges"],
                "total_invested": data["total_invested"],
                "return_on_invested_pct": data.get("return_on_invested_pct", 0),
                "return_on_capital_pct": data.get("return_on_capital_pct", 0),
            })
        except Exception:
            pass

    return results


def get_cumulative_stats() -> dict:
    """Calculate cumulative statistics across all trading days."""
    results = get_all_results()
    if not results:
        return {"total_days": 0}

    total_pnl = sum(r["net_pnl"] for r in results)
    total_trades = sum(r["total_trades"] for r in results)
    total_wins = sum(r["wins"] for r in results)
    total_invested = sum(r["total_invested"] for r in results)
    total_charges = sum(r["total_charges"] for r in results)
    winning_days = sum(1 for r in results if r["net_pnl"] > 0)

    return {
        "total_days": len(results),
        "winning_days": winning_days,
        "losing_days": len(results) - winning_days,
        "day_win_rate_pct": round(winning_days / len(results) * 100, 1) if results else 0,
        "total_trades": total_trades,
        "total_wins": total_wins,
        "total_losses": total_trades - total_wins,
        "trade_win_rate_pct": round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0,
        "total_net_pnl": round(total_pnl, 2),
        "total_charges": round(total_charges, 2),
        "total_invested": round(total_invested, 2),
        "avg_daily_pnl": round(total_pnl / len(results), 2) if results else 0,
        "best_day": max(results, key=lambda r: r["net_pnl"]) if results else None,
        "worst_day": min(results, key=lambda r: r["net_pnl"]) if results else None,
        "daily_results": results,
    }
