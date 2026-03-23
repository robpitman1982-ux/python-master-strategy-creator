from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
REPO_DATA_DIR = REPO_ROOT / "Data"
LEGACY_RESULTS_DIR = REPO_ROOT / "cloud_results"

_console_storage_override = os.environ.get("STRATEGY_CONSOLE_STORAGE")
_home_console_storage = (Path.home() / "strategy_console_storage").expanduser()

if _console_storage_override:
    CONSOLE_STORAGE_ROOT = Path(_console_storage_override).expanduser()
elif _home_console_storage.exists():
    CONSOLE_STORAGE_ROOT = _home_console_storage
else:
    CONSOLE_STORAGE_ROOT = REPO_ROOT / "strategy_console_storage"

UPLOADS_DIR = CONSOLE_STORAGE_ROOT / "uploads"
RUNS_DIR = CONSOLE_STORAGE_ROOT / "runs"
EXPORTS_DIR = CONSOLE_STORAGE_ROOT / "exports"
BACKUPS_DIR = CONSOLE_STORAGE_ROOT / "backups"
RUN_STATUS_PATH = CONSOLE_STORAGE_ROOT / "run_status.json"
CONSOLE_SELECTION_PATH = CONSOLE_STORAGE_ROOT / "console_selection.json"
