"""Configuration management using pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    host: str = "localhost"
    port: int = 6380
    db: int = 0
    password: str | None = None

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class TimescaleConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TIMESCALE_")
    host: str = "localhost"
    port: int = 5434
    user: str = "tradeplus"
    password: str = "tradeplus_dev"
    database: str = "tradeplus_market"

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class PostgresConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_")
    host: str = "localhost"
    port: int = 5435
    user: str = "tradeplus"
    password: str = "tradeplus_dev"
    database: str = "tradeplus_trades"

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class BrokerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BROKER_")
    name: str = "mock"  # mock | zerodha | dhan | upstox
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    base_url: str = ""


class RiskConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISK_")
    max_position_size: int = 100
    max_daily_loss: float = 5000.0  # INR
    max_open_positions: int = 5
    max_orders_per_second: int = 8  # keep under SEBI 10 OPS limit
    max_order_value: float = 500_000.0  # INR


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADEPLUS_",
        env_nested_delimiter="__",
    )
    debug: bool = False
    log_level: str = "INFO"

    redis: RedisConfig = Field(default_factory=RedisConfig)
    timescale: TimescaleConfig = Field(default_factory=TimescaleConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
