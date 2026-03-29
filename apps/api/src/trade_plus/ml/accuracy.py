"""Prediction accuracy tracker.

After each trading day ends (post 3:30 PM), compares predictions
made during the day against actual price changes and updates
the `was_correct` field in the predictions table.

Also maintains a daily accuracy summary table.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal

import structlog
import yfinance as yf

from trade_plus.instruments import ALL_INSTRUMENTS

logger = structlog.get_logger()


async def evaluate_day(pool, target_date: date | None = None) -> dict:
    """Evaluate all predictions for a given day against actual outcomes.

    Called after market close. Fetches actual closing prices and
    marks each prediction as correct or wrong.

    Returns summary dict per instrument.
    """
    if target_date is None:
        target_date = date.today()

    start_of_day = datetime(target_date.year, target_date.month, target_date.day)
    end_of_day = start_of_day + timedelta(days=1)

    logger.info("accuracy_evaluation_start", date=target_date.isoformat())

    # Get all predictions from this day that haven't been evaluated
    rows = await pool.fetch(
        """
        SELECT ctid, run_id, instrument, direction, score, confidence, time
        FROM predictions
        WHERE time >= $1 AND time < $2 AND was_correct IS NULL
        ORDER BY time
        """,
        start_of_day, end_of_day,
    )

    if not rows:
        logger.info("accuracy_no_pending", date=target_date.isoformat())
        return {}

    # Fetch actual closing prices for the prediction day and next day
    actual_prices: dict[str, dict] = {}
    for inst in ALL_INSTRUMENTS:
        try:
            ticker = yf.Ticker(inst.yahoo_symbol)
            hist = ticker.history(
                start=target_date - timedelta(days=1),
                end=target_date + timedelta(days=3),
                interval="1d",
            )
            if len(hist) >= 2:
                # Normalize index
                hist.index = hist.index.tz_localize(None)

                # Find the target date's close and next day's close
                target_rows = hist[hist.index.date == target_date]
                next_rows = hist[hist.index.date > target_date]

                if not target_rows.empty and not next_rows.empty:
                    day_close = float(target_rows["Close"].iloc[-1])
                    next_close = float(next_rows["Close"].iloc[0])
                    actual_change = (next_close - day_close) / day_close * 100

                    actual_prices[inst.ticker] = {
                        "day_close": day_close,
                        "next_close": next_close,
                        "actual_change_pct": round(actual_change, 4),
                        "went_up": actual_change > 0,
                    }
        except Exception as e:
            logger.warning("accuracy_price_fetch_failed", instrument=inst.ticker, error=str(e))

    # Evaluate each prediction
    results: dict[str, dict] = {}
    for row in rows:
        inst = row["instrument"]
        if inst not in actual_prices:
            continue

        actual = actual_prices[inst]
        predicted_up = row["direction"] == "LONG"
        actually_up = actual["went_up"]
        was_correct = predicted_up == actually_up

        # Update the prediction row
        await pool.execute(
            """
            UPDATE predictions
            SET was_correct = $1,
                actual_change_eod = $2
            WHERE run_id = $3 AND instrument = $4 AND time = $5
            """,
            was_correct,
            Decimal(str(actual["actual_change_pct"])),
            row["run_id"],
            inst,
            row["time"],
        )

        # Accumulate per-instrument stats
        if inst not in results:
            results[inst] = {"total": 0, "correct": 0, "wrong": 0, "scores": [], "confidences": []}
        results[inst]["total"] += 1
        if was_correct:
            results[inst]["correct"] += 1
        else:
            results[inst]["wrong"] += 1
        results[inst]["scores"].append(float(row["score"]))
        results[inst]["confidences"].append(float(row["confidence"]))
        results[inst]["actual_change"] = actual["actual_change_pct"]

    # Write daily summary
    for inst, stats in results.items():
        total = stats["total"]
        correct = stats["correct"]
        accuracy = correct / total if total > 0 else 0
        avg_score = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
        avg_conf = sum(stats["confidences"]) / len(stats["confidences"]) if stats["confidences"] else 0

        await pool.execute(
            """
            INSERT INTO prediction_accuracy (date, instrument, total, correct, wrong, accuracy, avg_score, avg_confidence, actual_change)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (date, instrument) DO UPDATE SET
                total = EXCLUDED.total, correct = EXCLUDED.correct, wrong = EXCLUDED.wrong,
                accuracy = EXCLUDED.accuracy, avg_score = EXCLUDED.avg_score,
                avg_confidence = EXCLUDED.avg_confidence, actual_change = EXCLUDED.actual_change
            """,
            target_date, inst, total, correct, stats["wrong"],
            Decimal(str(round(accuracy, 4))),
            Decimal(str(round(avg_score, 4))),
            Decimal(str(round(avg_conf, 4))),
            Decimal(str(stats.get("actual_change", 0))),
        )

        logger.info(
            "accuracy_evaluated",
            date=target_date.isoformat(),
            instrument=inst,
            total=total,
            correct=correct,
            accuracy=f"{accuracy:.1%}",
            actual_change=f"{stats.get('actual_change', 0):+.2f}%",
        )

    return results


async def get_accuracy_summary(pool, instrument: str, days: int = 30) -> dict:
    """Get accuracy summary for an instrument over the last N days."""
    rows = await pool.fetch(
        """
        SELECT date, total, correct, wrong, accuracy, avg_score, avg_confidence, actual_change
        FROM prediction_accuracy
        WHERE instrument = $1
        ORDER BY date DESC
        LIMIT $2
        """,
        instrument, days,
    )

    if not rows:
        return {"instrument": instrument, "days": [], "overall": {}}

    days_data = []
    total_correct = 0
    total_predictions = 0

    for r in rows:
        days_data.append({
            "date": r["date"].isoformat(),
            "total": r["total"],
            "correct": r["correct"],
            "wrong": r["wrong"],
            "accuracy": float(r["accuracy"]) if r["accuracy"] else 0,
            "avg_score": float(r["avg_score"]) if r["avg_score"] else 0,
            "actual_change": float(r["actual_change"]) if r["actual_change"] else 0,
        })
        total_correct += r["correct"]
        total_predictions += r["total"]

    overall_accuracy = total_correct / total_predictions if total_predictions > 0 else 0

    return {
        "instrument": instrument,
        "days": days_data,
        "overall": {
            "total_predictions": total_predictions,
            "total_correct": total_correct,
            "accuracy": round(overall_accuracy, 4),
            "days_tracked": len(days_data),
        },
    }
