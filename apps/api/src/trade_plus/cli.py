"""CLI entry point for trade-plus."""

from __future__ import annotations

import asyncio
import sys

import click
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)


@click.group()
def main():
    """Trade-Plus: Algorithmic trading system for Indian markets."""
    pass


@main.command()
@click.option("--once", is_flag=True, help="Single snapshot and exit")
@click.option("--interval", default=10.0, type=float, help="Minutes between polls")
def serve(once: bool, interval: float):
    """Start the live server (main command)."""
    from trade_plus.server import run_live, run_once

    if once:
        asyncio.run(run_once())
    else:
        try:
            asyncio.run(run_live(interval_minutes=interval))
        except KeyboardInterrupt:
            click.echo("\nServer stopped.")


@main.command()
def status():
    """Check infrastructure + market status."""
    asyncio.run(_check_status())


async def _check_status():
    import redis.asyncio as redis
    from trade_plus.core.config import AppConfig
    from trade_plus.market_data.market_hours import market_status_summary

    config = AppConfig()

    # Market status
    ms = market_status_summary()
    click.echo("Market Status:")
    click.echo(f"  Time:         {ms['time_ist']}")
    click.echo(f"  Session:      {ms['session']}")
    click.echo(f"  Trading Day:  {ms['is_trading_day']}")
    click.echo(f"  Can Trade:    {ms['can_trade']}")
    click.echo(f"  Time to Open: {ms['time_to_open']}")
    if ms.get("is_holiday"):
        click.echo(f"  Holiday:      Yes")

    # Infrastructure
    click.echo("\nInfrastructure:")
    results = {}
    try:
        r = redis.Redis.from_url(config.redis.url)
        await r.ping()
        results["redis"] = "OK"
        await r.aclose()
    except Exception as e:
        results["redis"] = f"FAIL: {e}"

    try:
        import asyncpg
        conn = await asyncpg.connect(dsn=config.timescale.dsn)
        await conn.fetchval("SELECT 1")
        await conn.close()
        results["timescaledb"] = "OK"
    except Exception as e:
        results["timescaledb"] = f"FAIL: {e}"

    try:
        import asyncpg
        conn = await asyncpg.connect(dsn=config.postgres.dsn)
        await conn.fetchval("SELECT 1")
        await conn.close()
        results["postgres"] = "OK"
    except Exception as e:
        results["postgres"] = f"FAIL: {e}"

    for svc, st in results.items():
        icon = "+" if st == "OK" else "x"
        click.echo(f"  [{icon}] {svc}: {st}")


@main.command()
def instruments():
    """List all tracked instruments."""
    from trade_plus.instruments import ALL_INSTRUMENTS
    click.echo("Tracked Instruments:\n")
    click.echo(f"  {'Ticker':<14s} {'Name':<25s} {'Sector':<10s} {'~Price':>8s} {'Short?':>7s}")
    click.echo(f"  {'-'*14} {'-'*25} {'-'*10} {'-'*8} {'-'*7}")
    for i in ALL_INSTRUMENTS:
        click.echo(
            f"  {i.ticker:<14s} {i.name:<25s} {i.sector.value:<10s} "
            f"Rs {i.approx_price:>5.0f} {'Yes' if i.shortable_intraday else 'No':>7s}"
        )


if __name__ == "__main__":
    main()
