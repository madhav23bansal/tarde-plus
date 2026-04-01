"""Indian broker charge calculator — exact fee structure per broker.

Calculates all statutory + broker charges for an intraday equity trade.
Statutory charges (STT, exchange, GST, stamp duty) are fixed by regulation —
same across all brokers. Only brokerage differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

D = Decimal


@dataclass(frozen=True)
class TradeCharges:
    """Breakdown of all charges for a single trade leg (buy OR sell)."""
    turnover: Decimal          # trade value
    brokerage: Decimal
    stt: Decimal               # Securities Transaction Tax
    exchange_txn: Decimal      # NSE transaction charge
    gst: Decimal               # 18% on (brokerage + exchange + SEBI)
    sebi_fee: Decimal
    stamp_duty: Decimal
    total: Decimal

    def to_dict(self) -> dict:
        return {k: float(v) for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class RoundTripCharges:
    """Total charges for a buy + sell round trip."""
    buy: TradeCharges
    sell: TradeCharges
    total: Decimal
    pct_of_turnover: Decimal   # total charges as % of total turnover

    def to_dict(self) -> dict:
        return {
            "buy": self.buy.to_dict(),
            "sell": self.sell.to_dict(),
            "total": float(self.total),
            "pct_of_turnover": float(self.pct_of_turnover),
        }


# ── Broker configs ───────────────────────────────────────────────

BROKER_CONFIGS = {
    "fyers": {
        "name": "Fyers",
        "brokerage_pct": D("0.0003"),    # 0.03%
        "brokerage_cap": D("20"),         # Rs 20 max per order
    },
    "zerodha": {
        "name": "Zerodha",
        "brokerage_pct": D("0.0003"),    # 0.03%
        "brokerage_cap": D("20"),         # Rs 20 max per order
    },
    "angelone": {
        "name": "Angel One",
        "brokerage_pct": D("0.0003"),
        "brokerage_cap": D("20"),
    },
    "dhan": {
        "name": "Dhan",
        "brokerage_pct": D("0.0003"),
        "brokerage_cap": D("20"),
    },
}

# ── Statutory rates (same for all brokers) ───────────────────────

STT_INTRADAY_SELL = D("0.00025")      # 0.025% on sell side only
EXCHANGE_TXN_NSE = D("0.0000297")     # 0.00297%
SEBI_FEE_PER_CRORE = D("10")          # Rs 10 per crore
GST_RATE = D("0.18")                   # 18%
STAMP_DUTY_BUY = D("0.00003")         # 0.003% on buy side only


def calculate_leg(
    turnover: Decimal,
    side: str,  # "BUY" or "SELL"
    broker: str = "fyers",
) -> TradeCharges:
    """Calculate charges for one leg (buy or sell) of an intraday trade."""
    cfg = BROKER_CONFIGS.get(broker, BROKER_CONFIGS["fyers"])

    # Brokerage: min(pct * turnover, cap)
    brokerage = min(cfg["brokerage_pct"] * turnover, cfg["brokerage_cap"])
    brokerage = brokerage.quantize(D("0.01"), rounding=ROUND_HALF_UP)

    # STT: only on sell side for intraday
    stt = (STT_INTRADAY_SELL * turnover).quantize(D("0.01")) if side == "SELL" else D("0")

    # Exchange transaction charge
    exchange_txn = (EXCHANGE_TXN_NSE * turnover).quantize(D("0.01"))

    # SEBI fee
    sebi_fee = (turnover / D("10000000") * SEBI_FEE_PER_CRORE).quantize(D("0.01"))

    # GST: 18% on (brokerage + exchange + SEBI)
    gst = (GST_RATE * (brokerage + exchange_txn + sebi_fee)).quantize(D("0.01"))

    # Stamp duty: only on buy side
    stamp_duty = (STAMP_DUTY_BUY * turnover).quantize(D("0.01")) if side == "BUY" else D("0")

    total = brokerage + stt + exchange_txn + gst + sebi_fee + stamp_duty

    return TradeCharges(
        turnover=turnover,
        brokerage=brokerage,
        stt=stt,
        exchange_txn=exchange_txn,
        gst=gst,
        sebi_fee=sebi_fee,
        stamp_duty=stamp_duty,
        total=total,
    )


def calculate_round_trip(
    buy_value: Decimal,
    sell_value: Decimal,
    broker: str = "fyers",
) -> RoundTripCharges:
    """Calculate all charges for a complete buy+sell round trip."""
    buy_charges = calculate_leg(buy_value, "BUY", broker)
    sell_charges = calculate_leg(sell_value, "SELL", broker)
    total = buy_charges.total + sell_charges.total
    total_turnover = buy_value + sell_value
    pct = (total / total_turnover * D("100")).quantize(D("0.0001")) if total_turnover > 0 else D("0")

    return RoundTripCharges(
        buy=buy_charges,
        sell=sell_charges,
        total=total,
        pct_of_turnover=pct,
    )
