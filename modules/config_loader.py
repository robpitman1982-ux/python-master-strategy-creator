from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = Path("config.yaml")


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
