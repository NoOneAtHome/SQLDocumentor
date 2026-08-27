"""Configuration models and loader."""

from sqldoc.config.errors import ConfigError
from sqldoc.config.loader import load_config
from sqldoc.config.schema import (
    AppConfig,
    AuthCfg,
    ConnectionCfg,
    DatabaseCfg,
    ScanOptions,
    StorageCfg,
)

__all__ = [
    "AppConfig",
    "AuthCfg",
    "ConfigError",
    "ConnectionCfg",
    "DatabaseCfg",
    "ScanOptions",
    "StorageCfg",
    "load_config",
]
