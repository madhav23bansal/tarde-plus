"""Support & Resistance level computation.

Computes all key intraday levels from previous day's OHLC:
  - Standard Pivot Points (P, R1, R2, S1, S2)
  - CPR (Central Pivot Range) + day type classification
  - Camarilla (H3, H4, L3, L4)
  - Previous Day High/Low/Close (PDH, PDL, PDC)
  - Opening Range (15-min high/low) — set after market open
  - OI-based levels (from NSE option chain)
  - Gap analysis

All levels stored as a sorted list so the engine can find
"nearest support" and "nearest resistance" from current price.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Level:
    """A single support/resistance level."""
    price: float
    name: str           # e.g., "R1", "Camarilla H3", "PDH", "Call OI 23500"
    type: str           # "support" or "resistance" or "pivot"
    strength: float     # 0-1, how important this level is
    source: str         # "pivot", "camarilla", "cpr", "pdhl", "orb", "oi"


@dataclass
class DayLevels:
    """All S/R levels for one instrument for today."""
    instrument: str
    levels: list[Level] = field(default_factory=list)

    # Key reference values
    pivot: float = 0.0
    cpr_tc: float = 0.0
    cpr_bc: float = 0.0
    cpr_width_pct: float = 0.0
    day_type: str = "unknown"  # "trending" or "range"

    pdh: float = 0.0
    pdl: float = 0.0
    pdc: float = 0.0

    orb_high: float = 0.0
    orb_low: float = 0.0
    orb_set: bool = False

    gap_pct: float = 0.0
    gap_type: str = ""  # "gap_up", "gap_down", "flat"

    # OI-based
    oi_resistance: float = 0.0  # highest Call OI strike
    oi_support: float = 0.0     # highest Put OI strike
    max_pain: float = 0.0
    pcr: float = 0.0

    def nearest_support(self, price: float) -> Level | None:
        """Find the nearest support level below current price."""
        supports = [l for l in self.levels if l.price < price and l.type in ("support", "pivot")]
        return max(supports, key=lambda l: l.price) if supports else None

    def nearest_resistance(self, price: float) -> Level | None:
        """Find the nearest resistance level above current price."""
        resistances = [l for l in self.levels if l.price > price and l.type in ("resistance", "pivot")]
        return min(resistances, key=lambda l: l.price) if resistances else None

    def at_level(self, price: float, threshold_pct: float = 0.15) -> Level | None:
        """Check if price is within threshold% of any level."""
        for level in self.levels:
            if abs(price - level.price) / price * 100 <= threshold_pct:
                return level
        return None

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "pivot": self.pivot,
            "cpr": {"tc": self.cpr_tc, "bc": self.cpr_bc, "width_pct": round(self.cpr_width_pct, 3), "day_type": self.day_type},
            "pdh": self.pdh, "pdl": self.pdl, "pdc": self.pdc,
            "orb": {"high": self.orb_high, "low": self.orb_low, "set": self.orb_set},
            "gap": {"pct": round(self.gap_pct, 3), "type": self.gap_type},
            "oi": {"resistance": self.oi_resistance, "support": self.oi_support, "max_pain": self.max_pain, "pcr": round(self.pcr, 3)},
            "levels": [{"price": round(l.price, 2), "name": l.name, "type": l.type, "strength": l.strength, "source": l.source} for l in sorted(self.levels, key=lambda x: x.price)],
        }


def compute_levels(instrument: str, prev_high: float, prev_low: float, prev_close: float, today_open: float = 0) -> DayLevels:
    """Compute all S/R levels from previous day's OHLC."""
    dl = DayLevels(instrument=instrument)
    dl.pdh = prev_high
    dl.pdl = prev_low
    dl.pdc = prev_close

    # Standard Pivots
    pivot = (prev_high + prev_low + prev_close) / 3
    r1 = 2 * pivot - prev_low
    r2 = pivot + (prev_high - prev_low)
    s1 = 2 * pivot - prev_high
    s2 = pivot - (prev_high - prev_low)

    dl.pivot = round(pivot, 2)
    dl.levels.append(Level(round(pivot, 2), "Pivot", "pivot", 0.9, "pivot"))
    dl.levels.append(Level(round(r1, 2), "R1", "resistance", 0.8, "pivot"))
    dl.levels.append(Level(round(r2, 2), "R2", "resistance", 0.7, "pivot"))
    dl.levels.append(Level(round(s1, 2), "S1", "support", 0.8, "pivot"))
    dl.levels.append(Level(round(s2, 2), "S2", "support", 0.7, "pivot"))

    # CPR
    bc = (prev_high + prev_low) / 2
    tc = (pivot - bc) + pivot
    cpr_width = abs(tc - bc) / pivot * 100

    dl.cpr_tc = round(tc, 2)
    dl.cpr_bc = round(bc, 2)
    dl.cpr_width_pct = cpr_width
    dl.day_type = "trending" if cpr_width < 0.35 else "range"

    # Camarilla
    cam_range = prev_high - prev_low
    h3 = prev_close + cam_range * 1.1 / 4
    h4 = prev_close + cam_range * 1.1 / 2
    l3 = prev_close - cam_range * 1.1 / 4
    l4 = prev_close - cam_range * 1.1 / 2

    dl.levels.append(Level(round(h3, 2), "Cam H3", "resistance", 0.85, "camarilla"))
    dl.levels.append(Level(round(h4, 2), "Cam H4", "resistance", 0.95, "camarilla"))
    dl.levels.append(Level(round(l3, 2), "Cam L3", "support", 0.85, "camarilla"))
    dl.levels.append(Level(round(l4, 2), "Cam L4", "support", 0.95, "camarilla"))

    # PDH/PDL
    dl.levels.append(Level(prev_high, "PDH", "resistance", 0.9, "pdhl"))
    dl.levels.append(Level(prev_low, "PDL", "support", 0.9, "pdhl"))

    # Gap analysis
    if today_open > 0:
        dl.gap_pct = (today_open - prev_close) / prev_close * 100
        if dl.gap_pct > 0.3:
            dl.gap_type = "gap_up"
        elif dl.gap_pct < -0.3:
            dl.gap_type = "gap_down"
        else:
            dl.gap_type = "flat"

    return dl


def set_opening_range(dl: DayLevels, orb_high: float, orb_low: float) -> None:
    """Set the 15-minute opening range after 9:30 AM."""
    dl.orb_high = orb_high
    dl.orb_low = orb_low
    dl.orb_set = True
    dl.levels.append(Level(orb_high, "ORB High", "resistance", 0.85, "orb"))
    dl.levels.append(Level(orb_low, "ORB Low", "support", 0.85, "orb"))


def set_oi_levels(dl: DayLevels, oi_resistance: float, oi_support: float, max_pain: float, pcr: float, nifty_to_etf_ratio: float = 100) -> None:
    """Set OI-based levels. Converts Nifty strikes to ETF prices."""
    dl.oi_resistance = round(oi_resistance / nifty_to_etf_ratio, 2)
    dl.oi_support = round(oi_support / nifty_to_etf_ratio, 2)
    dl.max_pain = round(max_pain / nifty_to_etf_ratio, 2)
    dl.pcr = pcr

    if dl.oi_resistance > 0:
        dl.levels.append(Level(dl.oi_resistance, f"OI Call Wall", "resistance", 0.95, "oi"))
    if dl.oi_support > 0:
        dl.levels.append(Level(dl.oi_support, f"OI Put Wall", "support", 0.95, "oi"))
    if dl.max_pain > 0:
        dl.levels.append(Level(dl.max_pain, "Max Pain", "pivot", 0.7, "oi"))
