"""Load sqldoc.yaml: YAML -> ${ENV} interpolation -> validated AppConfig.

Environment variables referenced as ``${NAME}`` are resolved from the process
environment first, then from a ``.env`` file sitting next to the config file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import ValidationError

from sqldoc.config.errors import ConfigError
from sqldoc.config.schema import AppConfig

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_config(path: Path | str) -> AppConfig:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    env = _environment(path.parent / ".env")
    data = _interpolate(raw, env, path="")
    try:
        cfg = AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_describe(path, exc)) from exc

    if not cfg.storage.sqlite_path.is_absolute():
        cfg.storage.sqlite_path = path.parent / cfg.storage.sqlite_path
    return cfg


def _environment(dotenv_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if dotenv_path.is_file():
        env.update({k: v for k, v in dotenv_values(dotenv_path).items() if v is not None})
    env.update(os.environ)  # process environment wins
    return env


def _interpolate(value: Any, env: dict[str, str], path: str) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in env:
                raise ConfigError(
                    f"{path}: references environment variable '{name}' which is not set"
                )
            return env[name]

        return _ENV_REF.sub(replace, value)
    if isinstance(value, dict):
        return {
            k: _interpolate(v, env, f"{path}.{k}" if path else str(k)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_interpolate(v, env, f"{path}[{i}]") for i, v in enumerate(value)]
    return value


def _describe(path: Path, exc: ValidationError) -> str:
    lines = [f"{path}: invalid configuration"]
    for err in exc.errors():
        loc = _format_loc(err.get("loc", ()))
        msg = err.get("msg", "")
        msg = msg.removeprefix("Value error, ")
        lines.append(f"  {loc}: {msg}" if loc else f"  {msg}")
    return "\n".join(lines)


def _format_loc(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out
