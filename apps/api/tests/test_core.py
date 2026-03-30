"""Tests for core components — message bus, events, levels, charges, paper trader."""

import asyncio
import time
from decimal import Decimal

import pytest

from trade_plus.core.events import EventType, TickEvent
from trade_plus.core.message_bus import MessageBus
from trade_plus.instruments import Direction, NIFTYBEES
from trade_plus.trading.levels import compute_levels, DayLevels
from trade_plus.trading.charges import calculate_round_trip, D
from trade_plus.trading.paper_trader import PaperTrader


# --- MessageBus Tests ---

@pytest.mark.asyncio
async def test_message_bus_publish_subscribe():
    bus = MessageBus()
    received = []
    async def handler(event):
        received.append(event)
    bus.subscribe(EventType.TICK, handler)
    tick = TickEvent(instrument="NIFTYBEES", ltp=Decimal("255.50"), volume=1000)
    await bus.publish(tick)
    assert len(received) == 1
    assert received[0].instrument == "NIFTYBEES"


@pytest.mark.asyncio
async def test_message_bus_multiple_handlers():
    bus = MessageBus()
    count = {"a": 0, "b": 0}
    async def handler_a(event): count["a"] += 1
    async def handler_b(event): count["b"] += 1
    bus.subscribe(EventType.TICK, handler_a)
    bus.subscribe(EventType.TICK, handler_b)
    tick = TickEvent(instrument="NIFTYBEES", ltp=Decimal("255"), volume=500)
    await bus.publish(tick)
    assert count["a"] == 1 and count["b"] == 1


@pytest.mark.asyncio
async def test_message_bus_error_isolation():
    bus = MessageBus()
    good_received = []
    async def bad_handler(event): raise ValueError("boom")
    async def good_handler(event): good_received.append(event)
    bus.subscribe(EventType.TICK, bad_handler)
    bus.subscribe(EventType.TICK, good_handler)
    tick = TickEvent(instrument="NIFTYBEES", ltp=Decimal("255"), volume=200)
    await bus.publish(tick)
    assert len(good_received) == 1


# --- S/R Levels Tests ---

def test_compute_levels():
    dl = compute_levels("NIFTYBEES", prev_high=265.20, prev_low=258.65, prev_close=258.89, today_open=258.42)
    assert dl.instrument == "NIFTYBEES"
    assert dl.pivot > 0
    assert dl.pdh == 265.20
    assert dl.pdl == 258.65
    assert len(dl.levels) >= 10  # at least pivots + camarilla + PDH/PDL
    assert dl.day_type in ("trending", "range")
    assert dl.gap_pct != 0  # there's a gap


def test_levels_at_level():
    dl = compute_levels("NIFTYBEES", prev_high=265.20, prev_low=258.65, prev_close=258.89)
    level = dl.at_level(258.70, threshold_pct=0.20)
    assert level is not None
    assert level.name == "PDL"


def test_levels_nearest():
    dl = compute_levels("NIFTYBEES", prev_high=265.20, prev_low=258.65, prev_close=258.89)
    support = dl.nearest_support(261.0)
    resistance = dl.nearest_resistance(261.0)
    assert support is not None
    assert resistance is not None
    assert support.price < 261.0
    assert resistance.price > 261.0


def test_levels_gap_classification():
    dl_up = compute_levels("TEST", 100, 90, 95, today_open=97)
    assert dl_up.gap_type == "gap_up"
    dl_down = compute_levels("TEST", 100, 90, 95, today_open=93)
    assert dl_down.gap_type == "gap_down"
    dl_flat = compute_levels("TEST", 100, 90, 95, today_open=95.1)
    assert dl_flat.gap_type == "flat"


# --- Charges Tests ---

def test_shoonya_charges():
    rt = calculate_round_trip(D("50000"), D("50000"), broker="shoonya")
    assert rt.total > 0
    assert rt.buy.brokerage <= D("5")  # Shoonya caps at Rs 5
    assert rt.sell.brokerage <= D("5")
    assert rt.sell.stt > 0  # STT on sell side
    assert rt.buy.stamp_duty > 0  # stamp on buy side


def test_zerodha_charges():
    rt = calculate_round_trip(D("50000"), D("50000"), broker="zerodha")
    assert rt.total > 0
    assert rt.buy.brokerage <= D("20")  # Zerodha caps at Rs 20


def test_small_trade_charges():
    rt = calculate_round_trip(D("1000"), D("1000"), broker="shoonya")
    # On Rs 1000, brokerage = min(0.03% * 1000, 5) = min(0.30, 5) = 0.30
    assert rt.buy.brokerage == D("0.30")
    assert rt.total < D("2")  # very low total charges


# --- Paper Trader Tests ---

def test_paper_trader_init():
    trader = PaperTrader(capital=50000, leverage=5, broker="shoonya")
    assert trader.capital == 50000
    assert trader.buying_power == 250000
    assert trader.day_trades == 0


def test_paper_trader_entry_exit():
    trader = PaperTrader(capital=50000, broker="shoonya")
    order = trader.execute_entry("NIFTYBEES", Direction.LONG, 255.0, 0.3, "test", "test reason")
    assert order is not None
    assert order.status == "COMPLETE"
    assert order.side == "BUY"
    assert trader.capital < 50000  # charges deducted
    assert "NIFTYBEES" in trader.positions

    # Close
    close_order = trader._close_position("NIFTYBEES", 256.0, "take profit")
    assert close_order is not None
    assert len(trader.positions) == 0
    assert trader.day_trades >= 1  # entry counted


def test_paper_trader_short():
    trader = PaperTrader(capital=50000, broker="shoonya")
    order = trader.execute_entry("NIFTYBEES", Direction.SHORT, 255.0, -0.3, "test", "short test")
    assert order.side == "SELL"
    pos = trader.positions["NIFTYBEES"]
    assert pos.side == "SHORT"
