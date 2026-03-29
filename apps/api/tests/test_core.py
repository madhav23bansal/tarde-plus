"""Tests for core components — message bus, events, risk manager."""

import asyncio
import time
from decimal import Decimal

import pytest

from trade_plus.core.events import (
    EventType,
    OrderEvent,
    OrderType,
    Side,
    SignalEvent,
    TickEvent,
)
from trade_plus.core.message_bus import MessageBus
from trade_plus.risk.manager import RiskManager
from trade_plus.core.config import RiskConfig


# --- MessageBus Tests ---

@pytest.mark.asyncio
async def test_message_bus_publish_subscribe():
    bus = MessageBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(EventType.TICK, handler)
    tick = TickEvent(instrument="NSE:RELIANCE", ltp=Decimal("2450.50"), volume=1000)
    await bus.publish(tick)

    assert len(received) == 1
    assert received[0].instrument == "NSE:RELIANCE"


@pytest.mark.asyncio
async def test_message_bus_multiple_handlers():
    bus = MessageBus()
    count = {"a": 0, "b": 0}

    async def handler_a(event):
        count["a"] += 1

    async def handler_b(event):
        count["b"] += 1

    bus.subscribe(EventType.TICK, handler_a)
    bus.subscribe(EventType.TICK, handler_b)

    tick = TickEvent(instrument="NSE:TCS", ltp=Decimal("3800"), volume=500)
    await bus.publish(tick)

    assert count["a"] == 1
    assert count["b"] == 1


@pytest.mark.asyncio
async def test_message_bus_latency_tracking():
    bus = MessageBus()

    async def handler(event):
        pass

    bus.subscribe(EventType.TICK, handler)

    for _ in range(10):
        tick = TickEvent(instrument="NSE:RELIANCE", ltp=Decimal("2450"), volume=100)
        await bus.publish(tick)

    stats = bus.stats()
    assert stats["sample_count"] == 10
    assert stats["avg_us"] >= 0  # should be measurable


@pytest.mark.asyncio
async def test_message_bus_error_isolation():
    bus = MessageBus()
    good_received = []

    async def bad_handler(event):
        raise ValueError("boom")

    async def good_handler(event):
        good_received.append(event)

    bus.subscribe(EventType.TICK, bad_handler)
    bus.subscribe(EventType.TICK, good_handler)

    tick = TickEvent(instrument="NSE:INFY", ltp=Decimal("1520"), volume=200)
    await bus.publish(tick)

    # Good handler should still receive despite bad handler throwing
    assert len(good_received) == 1


# --- Risk Manager Tests ---

def test_risk_manager_approval():
    config = RiskConfig()
    rm = RiskManager(config)

    signal = SignalEvent(
        instrument="NSE:RELIANCE", side=Side.BUY, strength=0.5, strategy_id="test"
    )
    approved, reason = rm.check_signal(signal)
    assert approved
    assert reason == "approved"


def test_risk_manager_daily_loss_halt():
    config = RiskConfig(max_daily_loss=1000.0)
    rm = RiskManager(config)

    rm.update_pnl(-1001.0)

    signal = SignalEvent(
        instrument="NSE:RELIANCE", side=Side.BUY, strength=0.5, strategy_id="test"
    )
    approved, reason = rm.check_signal(signal)
    assert not approved
    assert "loss limit" in reason.lower()
    assert rm.is_halted


def test_risk_manager_max_positions():
    config = RiskConfig(max_open_positions=2)
    rm = RiskManager(config)
    rm.update_positions(2)

    signal = SignalEvent(
        instrument="NSE:RELIANCE", side=Side.BUY, strength=0.5, strategy_id="test"
    )
    approved, reason = rm.check_signal(signal)
    assert not approved
    assert "positions" in reason.lower()


def test_risk_manager_order_value_limit():
    config = RiskConfig(max_order_value=100_000.0)
    rm = RiskManager(config)

    order = OrderEvent(
        instrument="NSE:RELIANCE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        price=Decimal("5000"),  # 100 * 5000 = 500k > 100k limit
        strategy_id="test",
    )
    approved, reason = rm.check_order(order)
    assert not approved
    assert "order value" in reason.lower()


def test_risk_manager_rate_limit():
    config = RiskConfig(max_orders_per_second=3)
    rm = RiskManager(config)

    # Simulate 3 orders
    for _ in range(3):
        rm.record_order_sent()

    signal = SignalEvent(
        instrument="NSE:RELIANCE", side=Side.BUY, strength=0.5, strategy_id="test"
    )
    approved, reason = rm.check_signal(signal)
    assert not approved
    assert "rate limit" in reason.lower()


def test_risk_manager_kill_switch():
    config = RiskConfig()
    rm = RiskManager(config)

    rm.kill_switch("Manual test")
    assert rm.is_halted

    signal = SignalEvent(
        instrument="NSE:RELIANCE", side=Side.BUY, strength=0.5, strategy_id="test"
    )
    approved, _ = rm.check_signal(signal)
    assert not approved

    rm.resume()
    assert not rm.is_halted
    approved, _ = rm.check_signal(signal)
    assert approved


# --- Mock Broker Tests ---

@pytest.mark.asyncio
async def test_mock_broker_connect():
    from trade_plus.brokers.mock import MockBroker

    broker = MockBroker()
    await broker.connect()
    assert broker.name == "mock"

    ltp = await broker.get_ltp(["NSE:RELIANCE", "NSE:TCS"])
    assert "NSE:RELIANCE" in ltp
    assert ltp["NSE:RELIANCE"] > 0

    await broker.disconnect()


@pytest.mark.asyncio
async def test_mock_broker_place_order():
    from trade_plus.brokers.mock import MockBroker

    broker = MockBroker()
    await broker.connect()

    resp = await broker.place_order(
        instrument="NSE:RELIANCE",
        side="BUY",
        order_type="MARKET",
        quantity=10,
    )
    assert resp.status == "FILLED"
    assert resp.broker_order_id.startswith("MOCK-")

    positions = await broker.get_positions()
    assert len(positions) == 1
    assert positions[0].instrument == "NSE:RELIANCE"
    assert positions[0].quantity == 10

    await broker.disconnect()


@pytest.mark.asyncio
async def test_mock_broker_tick_stream():
    from trade_plus.brokers.mock import MockBroker

    broker = MockBroker(tick_interval=0.05)
    await broker.connect()

    ticks = []
    async for quote in broker.subscribe_ticks(["NSE:RELIANCE"]):
        ticks.append(quote)
        if len(ticks) >= 5:
            break

    assert len(ticks) == 5
    assert all(t.instrument == "NSE:RELIANCE" for t in ticks)
    assert all(t.ltp > 0 for t in ticks)

    await broker.disconnect()
