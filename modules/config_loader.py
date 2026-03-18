from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = Path("config.yaml")

# ---------------------------------------------------------------------------
# Timeframe utilities
# ---------------------------------------------------------------------------

TIMEFRAME_BAR_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "daily": 390,  # ~6.5 hours trading day
}


def get_timeframe_multiplier(timeframe: str, base_timeframe: str = "60m") -> float:
    """Return multiplier to scale parameters from base_timeframe to target timeframe.

    Example: 5m relative to 60m  → 60 / 5  = 12.0  (need 12× more bars to cover same time)
    Example: daily relative to 60m → 60 / 390 ≈ 0.154 (need fewer bars)
    """
    base_minutes = TIMEFRAME_BAR_MINUTES.get(base_timeframe, 60)
    target_minutes = TIMEFRAME_BAR_MINUTES.get(timeframe, 60)
    if target_minutes <= 0:
        return 1.0
    return base_minutes / target_minutes


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """Load config from YAML file. Falls back to defaults if file missing."""
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH

    if not config_path.exists():
        print(f"[WARN] Config file not found at {config_path}, using hardcoded defaults.")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    print(f"[OK] Loaded config from {config_path}")
    return config


def get_nested(config: dict, *keys, default: Any = None) -> Any:
    """Safely get a nested config value. Example: get_nested(cfg, 'engine', 'initial_capital')"""
    current = config
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current
