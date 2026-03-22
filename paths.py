from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
REPO_DATA_DIR = REPO_ROOT / "Data"
LEGACY_RESULTS_DIR = REPO_ROOT / "cloud_results"

CONSOLE_STORAGE_ROOT = Path(os.environ.get("STRATEGY_CONSOLE_STORAGE", str(Path.home() / "strategy_console_storage"))).expanduser()
UPLOADS_DIR = CONSOLE_STORAGE_ROOT / "uploads"
RUNS_DIR = CONSOLE_STORAGE_ROOT / "runs"
EXPORTS_DIR = CONSOLE_STORAGE_ROOT / "exports"
BACKUPS_DIR = CONSOLE_STORAGE_ROOT / "backups"
RUN_STATUS_PATH = CONSOLE_STORAGE_ROOT / "run_status.json"
CONSOLE_SELECTION_PATH = CONSOLE_STORAGE_ROOT / "console_selection.json"
