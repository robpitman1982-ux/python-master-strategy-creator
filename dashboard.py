from __future__ import annotations

import html
import json
import os
import re
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
import pandas as pd
import streamlit as st

from dashboard_utils import (
    badge_for_value,
    billing_status_for_launcher,
    build_run_choice_label,
    build_monitor_progress_rows,
    canonical_runs_root,
    classify_run_status,
    collect_console_run_records,
    choose_default_run_record,
    detect_preemption_warning,
    detect_result_files,
    estimate_run_cost,
    estimate_total_eta_seconds,
    fetch_live_dataset_statuses,
    fetch_cluster_live_statuses,
    format_bytes,
    format_currency,
    format_datetime,
    format_duration,
    format_duration_short,
    format_run_scope,
    list_export_files,
    list_uploaded_datasets,
    load_current_leader_snapshot,
    load_log_tail,
    load_promoted_candidates,
    load_strategy_results,
    operator_action_summary,
    parse_dataset_filename,
    pick_best_candidate_file,
    read_console_run_status,
    resolve_console_storage_paths,
    status_color,
    _ssh_subprocess_run,
)
from paths import EXPORTS_DIR, LEGACY_RESULTS_DIR, RUNS_DIR, UPLOADS_DIR

# â”€â”€ Page config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

st.set_page_config(page_title="Current Run", layout="wide", page_icon="")

st.markdown("""
<style>
/* â”€â”€ Base slate theme â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.main { background-color: #0f172a; color: #f8fafc; }
.block-container { padding-top: 1.5rem; padding-bottom: 3rem; }

.console-banner {
    padding: 0.9rem 1.4rem;
    border-radius: 12px;
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    color: #f8fafc;
    margin-bottom: 1.2rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.console-banner h1 { margin: 0; font-size: 1.5rem; letter-spacing: -0.5px; }
.console-banner p  { margin: 0.2rem 0 0 0; opacity: 0.75; font-size: 0.85rem; }

.status-success { color: #10b981; font-weight: bold; }
.status-warning { color: #f59e0b; font-weight: bold; }
.status-error   { color: #ef4444; font-weight: bold; }
.status-info    { color: #3b82f6; font-weight: bold; }
.status-neutral { color: #94a3b8; font-weight: bold; }

.flag-robust   { background:#064e3b; color:#6ee7b7; padding:2px 8px; border-radius:8px; font-size:0.78rem; }
.flag-stable   { background:#1e3a8a; color:#93c5fd; padding:2px 8px; border-radius:8px; font-size:0.78rem; }
.flag-marginal { background:#78350f; color:#fcd34d; padding:2px 8px; border-radius:8px; font-size:0.78rem; }
.flag-broken   { background:#7f1d1d; color:#fca5a5; padding:2px 8px; border-radius:8px; font-size:0.78rem; }

div[data-testid="metric-container"] {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 0.75rem;
    box-shadow: inset 0 0 10px rgba(0,0,0,0.2);
}

[data-testid="stSidebar"] { background: #f8fafc; }
[data-testid="stSidebar"] * { color: #0f172a !important; }
[data-testid="stSidebar"] code {
    color: #0f172a !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}
.stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; }
.dataframe { font-size: 0.82rem; }

/* â”€â”€ Live Monitor: dataset grid â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.dataset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
    gap: 1rem;
    margin-top: 0.75rem;
}

.ds-card {
    background: #111827;
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 1.2rem 1.25rem 1rem;
}
.ds-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.6rem;
}
.ds-title {
    font-size: 1.55rem;
    font-weight: 800;
    color: #f8fafc;
    line-height: 1;
}
.ds-tf {
    font-size: 1.1rem;
    font-weight: 600;
    color: #94a3b8;
    margin-left: 0.35rem;
}
.ds-elapsed {
    font-size: 0.75rem;
    color: #64748b;
    margin-top: 0.15rem;
}

/* Host badges */
.host-badge {
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    white-space: nowrap;
}
.host-c240 { background: #1e3a8a; color: #93c5fd; }
.host-r630 { background: #064e3b; color: #6ee7b7; }
.host-gen8 { background: #4c1d95; color: #c4b5fd; }
.host-g9   { background: #7c2d12; color: #fdba74; }
.host-unknown { background: #334155; color: #94a3b8; }

/* Progress bar */
.prog-outer {
    background: #1e293b;
    border-radius: 6px;
    height: 10px;
    margin: 0.65rem 0 0.3rem;
    overflow: hidden;
    border: 1px solid #334155;
}
.prog-inner { height: 100%; border-radius: 6px; transition: width 0.4s ease; }
.prog-active  { background: linear-gradient(90deg, #3b82f6 0%, #06b6d4 100%); }
.prog-done    { background: #10b981; }
.prog-waiting { background: #475569; }
.prog-pct {
    font-size: 0.72rem;
    color: #64748b;
    text-align: right;
    margin-bottom: 0.55rem;
}

/* ETA display */
.eta-value {
    font-size: 2rem;
    font-weight: 800;
    color: #06b6d4;
    line-height: 1;
    letter-spacing: -0.03em;
}
.eta-done {
    font-size: 1.3rem;
    font-weight: 700;
    color: #10b981;
}
.eta-unknown {
    font-size: 1.3rem;
    font-weight: 600;
    color: #475569;
}
.stage-line {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 0.2rem;
    margin-bottom: 0.75rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* Family group mini bars */
.fam-groups {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 5px 10px;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid #1e293b;
}
.fam-row {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.78rem;
}
.fam-label { color: #94a3b8; min-width: 58px; }
.fam-bar {
    flex: 1;
    background: #1e293b;
    border-radius: 3px;
    height: 5px;
    overflow: hidden;
}
.fam-fill { height: 100%; border-radius: 3px; }
.fg-done   { background: #10b981; }
.fg-active { background: #3b82f6; }
.fg-wait   { background: #475569; }
.fam-count { color: #cbd5e1; font-size: 0.72rem; min-width: 26px; text-align: right; }

/* Console run monitor (secondary) */
.live-scope-card {
    background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 18px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 1rem;
    text-align: center;
}
.live-scope-card h2 { margin: 0; font-size: 1.2rem; color: #cbd5e1; }
.live-scope-card .scope-line { margin-top: 0.4rem; font-size: 1.35rem; font-weight: 700; color: #f8fafc; }
.monitor-card {
    background: #111827;
    border: 1px solid #334155;
    border-radius: 18px;
    padding: 0.9rem 1.1rem 0.8rem;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    margin-bottom: 1rem;
}
.monitor-card h3 { margin: 0 0 0.25rem 0; color: #f8fafc; font-size: 1rem; }
.monitor-card .subtle { color: #94a3b8; font-size: 0.84rem; }
.monitor-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 0.8rem;
    margin-top: 0.8rem;
}
.dataset-card {
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 0.9rem 1rem;
    background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
}
.dataset-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.6rem;
    margin-bottom: 0.5rem;
}
.dataset-title { font-size: 1rem; font-weight: 700; color: #f8fafc; }
.dataset-meta { font-size: 0.76rem; color: #94a3b8; }
.family-list { display: flex; flex-direction: column; gap: 0.3rem; }
.family-pill {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-radius: 10px;
    padding: 0.4rem 0.75rem;
    font-size: 0.86rem;
    font-weight: 600;
    border: 1px solid transparent;
}
.family-pill .progress-bar-bg {
    flex: 1; height: 5px; background: #1e293b; border-radius: 3px; margin: 0 0.5rem;
}
.family-pill .progress-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.family-pill.complete .progress-bar-fill { background: #10b981; }
.family-pill.active .progress-bar-fill  { background: #3b82f6; }
.family-pill.pending .progress-bar-fill { background: #475569; }
.family-pill.complete { background: #064e3b; color: #6ee7b7; border-color: #065f46; }
.family-pill.active   { background: #1e3a8a; color: #93c5fd; border-color: #1e40af; }
.family-pill.pending  { background: #334155; color: #94a3b8; border-color: #475569; }
.family-pill.failed   { background: #7f1d1d; color: #fca5a5; border-color: #991b1b; }
.hero-banner {
    background: #450a0a; color: #f87171;
    border: 1px solid #ef4444; border-radius: 16px;
    padding: 0.9rem 1rem; font-size: 1.1rem; font-weight: 800;
    text-align: center; margin-bottom: 1rem;
}
.focus-card {
    background: #0f172a; border: 1px solid #334155; color: #f8fbff;
    border-radius: 16px; padding: 0.9rem 1rem; margin-bottom: 0.85rem;
}
.focus-card .eyebrow { color: rgba(248,251,255,0.6); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em; }
.focus-card .value   { margin-top: 0.3rem; font-size: 1.15rem; font-weight: 800; }
.focus-card .detail  { margin-top: 0.25rem; font-size: 0.84rem; color: rgba(248,251,255,0.7); }
</style>
""", unsafe_allow_html=True)

# â”€â”€ Strategy family grouping â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FAMILY_GROUPS: list[tuple[str, list[str]]] = [
    ("Trend",    ["trend", "trend_pullback_continuation", "trend_momentum_breakout", "trend_slope_recovery"]),
    ("MR",       ["mean_reversion", "mean_reversion_vol_dip", "mean_reversion_mom_exhaustion", "mean_reversion_trend_pullback"]),
    ("Breakout", ["breakout", "breakout_compression_squeeze", "breakout_range_expansion", "breakout_higher_low_structure"]),
    ("S.MR",     ["short_mean_reversion"]),
    ("S.Trend",  ["short_trend"]),
    ("S.BKT",    ["short_breakout"]),
]

# â”€â”€ Runtime metadata â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@st.cache_resource
def dashboard_runtime_metadata() -> dict[str, str]:
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        commit = "unknown"
    return {"commit": commit, "hostname": socket.gethostname(), "started_at": started_at}


def _plan_backup_root(plan: dict[str, object]) -> Path | None:
    auto_ingest = plan.get("auto_ingest")
    if not isinstance(auto_ingest, dict):
        return None
    backup_root = str(auto_ingest.get("backup_root") or "").strip()
    return Path(backup_root) if backup_root else None


def _load_run_manifest(plan: dict[str, object], run_id: str) -> dict[str, object]:
    if not run_id:
        return {}
    candidates: list[Path] = []
    backup_root = _plan_backup_root(plan)
    if backup_root is not None:
        candidates.append(backup_root / "sweep_results" / "runs" / run_id / "cluster_run_manifest.json")
    candidates.append(Path("G:/My Drive/strategy-data-backup/sweep_results/runs") / run_id / "cluster_run_manifest.json")
    for path in candidates:
        if not path.exists():
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(manifest, dict):
            return manifest
    return {}


def _manifest_ingested_keys(manifest: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    jobs = manifest.get("jobs")
    if not isinstance(jobs, dict):
        return keys
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        host = str(job.get("host") or "").strip()
        market = str(job.get("market") or "").strip().upper()
        timeframe = str(job.get("timeframe") or "").strip()
        if host and market and timeframe:
            keys.add(f"{host}:{market}:{timeframe}")
    return keys


def _format_local_dt(value: str | datetime | None) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().strftime("%d %b %Y %H:%M")


def _planned_scope_text(plan: dict[str, object]) -> str:
    jobs: list[dict[str, str]] = []
    for host_entry in plan.get("hosts", []) if isinstance(plan.get("hosts"), list) else []:
        if not isinstance(host_entry, dict):
            continue
        for job in host_entry.get("jobs", []) if isinstance(host_entry.get("jobs"), list) else []:
            if isinstance(job, dict):
                market = str(job.get("market") or "").strip().upper()
                timeframe = str(job.get("timeframe") or "").strip()
                if market and timeframe:
                    jobs.append({"market": market, "timeframe": timeframe})
    markets = sorted({job["market"] for job in jobs})
    timeframes = sorted({job["timeframe"] for job in jobs}, key=lambda tf: (tf == "daily", tf))
    market_text = ", ".join(markets) if markets else "unknown markets"
    timeframe_text = ", ".join(timeframes) if timeframes else "unknown timeframes"
    return f"Markets: {market_text} | Timeframes: {timeframe_text}"


def _load_auto_ingest_summary() -> dict[str, object]:
    plan_path = Path(".tmp_10market_plan.json")
    state_path = Path(".tmp_auto_ingest_10market_state.json")
    plan: dict[str, object] = {}
    summary: dict[str, object] = {
        "run_id": "",
        "total_jobs": 0,
        "ingested_count": 0,
        "remaining_count": 0,
        "active": False,
        "last_line": "",
    }
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            summary["run_id"] = str(plan.get("run_id") or "")
            summary["total_jobs"] = int(plan.get("total_jobs") or 0)
        except Exception:
            pass
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            ingested = state.get("ingested", [])
            if isinstance(ingested, list):
                summary["ingested_count"] = len(ingested)
        except Exception:
            pass
    manifest = _load_run_manifest(plan, str(summary.get("run_id") or ""))
    manifest_keys = _manifest_ingested_keys(manifest)
    if manifest_keys:
        state_keys = set()
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                ingested = state.get("ingested", [])
                if isinstance(ingested, list):
                    state_keys = {str(item) for item in ingested}
            except Exception:
                state_keys = set()
        summary["ingested_count"] = len(state_keys | manifest_keys)
    total_jobs = int(summary.get("total_jobs") or 0)
    ingested_count = int(summary.get("ingested_count") or 0)
    summary["remaining_count"] = max(total_jobs - ingested_count, 0)
    summary["active"] = total_jobs > 0 and ingested_count < total_jobs
    log_path = Path("logs") / "auto_ingest_10market_fixed.out.log"
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines:
                summary["last_line"] = lines[-1]
        except Exception:
            pass
    return summary


def _load_auto_ingest_plan() -> dict[str, object]:
    plan_path = Path(".tmp_10market_plan.json")
    if not plan_path.exists():
        return {}
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return plan if isinstance(plan, dict) else {}


def _active_backup_outputs_dir(plan: dict[str, object], run_id: str) -> Path | None:
    if not run_id:
        return None
    backup_root = _plan_backup_root(plan)
    if backup_root is None:
        return None
    outputs_dir = backup_root / "sweep_results" / "runs" / run_id / "artifacts" / "Outputs"
    return outputs_dir if outputs_dir.exists() else None


def _load_auto_ingest_detail() -> dict[str, object]:
    plan_path = Path(".tmp_10market_plan.json")
    state_path = Path(".tmp_auto_ingest_10market_state.json")
    log_path = Path("logs") / "auto_ingest_10market_fixed.out.log"

    plan: dict[str, object] = {}
    state: dict[str, object] = {}
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            plan = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    run_id = str(plan.get("run_id") or state.get("run_id") or "")
    manifest = _load_run_manifest(plan, run_id)
    manifest_jobs = manifest.get("jobs") if isinstance(manifest.get("jobs"), dict) else {}

    ingested_keys = set()
    raw_ingested = state.get("ingested", [])
    if isinstance(raw_ingested, list):
        ingested_keys = {str(item) for item in raw_ingested}
    ingested_keys |= _manifest_ingested_keys(manifest)

    host_rows: list[dict[str, object]] = []
    for host_entry in plan.get("hosts", []) if isinstance(plan.get("hosts"), list) else []:
        if not isinstance(host_entry, dict):
            continue
        host = str(host_entry.get("host") or "unknown")
        jobs = host_entry.get("jobs", [])
        job_rows: list[dict[str, object]] = []
        if isinstance(jobs, list):
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                market = str(job.get("market") or "?").upper()
                timeframe = str(job.get("timeframe") or "?")
                key = f"{host}:{market}:{timeframe}"
                job_rows.append(
                    {
                        "market": market,
                        "timeframe": timeframe,
                        "key": key,
                        "done": key in ingested_keys,
                    }
                )
        done_count = sum(1 for job in job_rows if bool(job["done"]))
        total_count = len(job_rows)
        host_rows.append(
            {
                "host": host,
                "done": done_count,
                "total": total_count,
                "remaining": max(total_count - done_count, 0),
                "pct": (done_count / total_count * 100.0) if total_count else 0.0,
                "jobs": job_rows,
            }
        )

    successful_event_times: dict[str, datetime] = {}
    manifest_event_times: dict[str, str] = {}
    if isinstance(manifest_jobs, dict):
        for job in manifest_jobs.values():
            if not isinstance(job, dict):
                continue
            host = str(job.get("host") or "").strip()
            market = str(job.get("market") or "").strip().upper()
            timeframe = str(job.get("timeframe") or "").strip()
            ingested_utc = str(job.get("ingested_utc") or "").strip()
            if host and market and timeframe and ingested_utc:
                manifest_event_times[f"{host}:{market}:{timeframe}"] = ingested_utc
    last_line = ""
    log_paths = sorted((Path("logs")).glob("auto_ingest_10market*.out.log")) if Path("logs").exists() else []
    all_lines: list[str] = []
    for candidate_log in log_paths:
        try:
            lines = candidate_log.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            lines = []
        all_lines.extend(lines)
    if all_lines:
        last_line = all_lines[-1]
    ingest_re = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+ingesting\s+(?P<host>[^:]+):(?P<market>[^:]+):(?P<timeframe>\S+)")
    pending_event: tuple[str, datetime] | None = None
    for line in all_lines:
        match = ingest_re.search(line)
        if match:
            try:
                event_dt = datetime.fromisoformat(match.group("ts"))
            except Exception:
                event_dt = datetime.now(UTC)
            key = f"{match.group('host')}:{match.group('market').upper()}:{match.group('timeframe')}"
            pending_event = (key, event_dt)
            continue
        if "ERROR:" in line:
            pending_event = None
            continue
        if line.startswith("Ingested ") and pending_event is not None:
            key, event_dt = pending_event
            successful_event_times[key] = event_dt
            pending_event = None

    recent_events: list[dict[str, object]] = []
    cutoff = datetime.now(UTC).timestamp() - 24 * 3600
    for host_row in host_rows:
        host = str(host_row.get("host") or "")
        jobs = host_row.get("jobs", [])
        if not isinstance(jobs, list):
            continue
        for job in jobs:
            if not isinstance(job, dict) or not bool(job.get("done")):
                continue
            key = str(job.get("key") or "")
            event_dt = successful_event_times.get(key)
            manifest_time = manifest_event_times.get(key, "")
            if event_dt is not None and event_dt.timestamp() < cutoff:
                continue
            if event_dt is None and manifest_time:
                try:
                    manifest_dt = datetime.fromisoformat(manifest_time.replace("Z", "+00:00"))
                    if manifest_dt.timestamp() < cutoff:
                        continue
                except Exception:
                    pass
            recent_events.append(
                {
                    "time": (
                        _format_local_dt(event_dt)
                        if event_dt
                        else (_format_local_dt(manifest_time) if manifest_time else _format_local_dt(state.get("updated_utc")))
                    ),
                    "host": host,
                    "market": str(job.get("market") or "").upper(),
                    "timeframe": str(job.get("timeframe") or ""),
                    "_sort": (
                        event_dt.timestamp()
                        if event_dt
                        else (
                            datetime.fromisoformat(manifest_time.replace("Z", "+00:00")).timestamp()
                            if manifest_time
                            else 0
                        )
                    ),
                }
            )

    recent_events.sort(key=lambda item: (float(item.get("_sort") or 0), str(item.get("host") or "")), reverse=True)
    for event in recent_events:
        event.pop("_sort", None)

    return {
        "run_id": run_id,
        "scope": _planned_scope_text(plan),
        "host_rows": host_rows,
        "recent_events": recent_events[:30],
        "last_line": last_line,
        "updated_utc": str(state.get("updated_utc") or ""),
    }


# â”€â”€ Cached SSH functions (avoid blocking on every page load) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@st.cache_data(ttl=300)
def _cached_cluster_statuses(remote_root: str = "", hosts: tuple[str, ...] = ()) -> list[dict]:
    return fetch_cluster_live_statuses(hosts=list(hosts) if hosts else None, remote_root=remote_root or None)


@st.cache_data(ttl=300)
def _check_host_alive(host: str) -> bool:
    try:
        result = _ssh_subprocess_run(
            ["ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes", host, "echo 1"],
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


@st.cache_data(ttl=300)
def _check_host_online(host: str) -> bool:
    ping_cmd = (
        ["ping", "-n", "1", "-w", "1000", host]
        if os.name == "nt"
        else ["ping", "-c", "1", "-W", "1", host]
    )
    try:
        result = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            return True
    except Exception:
        pass
    return _check_host_alive(host)


@st.cache_data(ttl=300)
def _cached_remote_job_audit(remote_root: str, plan_json: str) -> dict[str, object]:
    try:
        plan = json.loads(plan_json)
    except Exception:
        return {"rows": [], "skipped": []}
    rows: list[dict[str, object]] = []
    skipped: list[str] = []
    host_entries = plan.get("hosts", [])
    if not isinstance(host_entries, list):
        return {"rows": rows, "skipped": skipped}
    for host_entry in host_entries:
        if not isinstance(host_entry, dict):
            continue
        host = str(host_entry.get("host") or "").strip()
        jobs = host_entry.get("jobs", [])
        if not host or not isinstance(jobs, list):
            continue
        if not _check_host_alive(host):
            skipped.append(f"{host}: reachable, SSH unavailable" if _check_host_online(host) else f"{host}: offline")
            continue
        job_pairs = [
            [str(job.get("market") or "").upper(), str(job.get("timeframe") or "")]
            for job in jobs
            if isinstance(job, dict)
        ]
        script = (
            "python3 - <<'PY'\n"
            "import json\n"
            "from pathlib import Path\n"
            f"root=Path({json.dumps(str(remote_root))})/'Outputs'\n"
            f"jobs=json.loads({json.dumps(json.dumps(job_pairs))})\n"
            "out=[]\n"
            "for market,timeframe in jobs:\n"
            "    run=f'{market.lower()}_{timeframe}_cfd'; ds=f'{market}_{timeframe}'\n"
            "    sp=root/run/ds/'status.json'; lb=root/run/ds/'family_leaderboard_results.csv'\n"
            "    rec={'market':market,'timeframe':timeframe,'status':'NOT_STARTED','pct':0,'family':'','timestamp':'','leaderboard':False}\n"
            "    if sp.exists():\n"
            "        try: data=json.loads(sp.read_text(encoding='utf-8'))\n"
            "        except Exception: data={}\n"
            "        rec.update(status=str(data.get('current_stage') or ''), pct=float(data.get('progress_pct') or 0), family=str(data.get('current_family') or ''), timestamp=str(data.get('timestamp') or ''), leaderboard=lb.exists())\n"
            "    elif (root/run).exists(): rec['status']='DIR_NO_STATUS'\n"
            "    out.append(rec)\n"
            "print(json.dumps(out))\n"
            "PY"
        )
        try:
            proc = _ssh_subprocess_run(
                ["ssh", "-o", "ConnectTimeout=3", "-o", "ConnectionAttempts=1", "-o", "BatchMode=yes", host, script],
                timeout=15,
            )
        except Exception:
            skipped.append(f"{host}: SSH probe failed")
            continue
        if proc.returncode != 0 or not proc.stdout.strip():
            skipped.append(f"{host}: SSH status unavailable")
            continue
        try:
            host_rows = json.loads(proc.stdout)
        except Exception:
            skipped.append(f"{host}: bad status payload")
            continue
        for row in host_rows if isinstance(host_rows, list) else []:
            if not isinstance(row, dict):
                continue
            market = str(row.get("market") or "").upper()
            timeframe = str(row.get("timeframe") or "")
            row["host"] = host
            row["job_key"] = f"{host}:{market}:{timeframe}"
            rows.append(row)
    return {"rows": rows, "skipped": skipped}


# â”€â”€ Data loading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

runtime = dashboard_runtime_metadata()
storage = resolve_console_storage_paths()
run_records = collect_console_run_records(storage=storage, include_legacy_fallback=False)
uploaded_datasets = list_uploaded_datasets(storage)
export_files = list_export_files(storage)
console_run_status = read_console_run_status()
monitor_run = choose_default_run_record(run_records, prefer_running=True)
selected_run = choose_default_run_record(run_records, require_outputs=True) or monitor_run
auto_ingest_plan = _load_auto_ingest_plan()
remote_root = str(auto_ingest_plan.get("remote_root") or "")
st.sidebar.title("Cluster Console")
remote_status_enabled = True
st.sidebar.caption("SSH live checks: on, read-only, cached for 5 minutes.")
status_hosts = tuple(h for h in ["c240", "gen8", "r630", "g9"] if _check_host_alive(h))
cluster_live_statuses = _cached_cluster_statuses(remote_root, status_hosts)
auto_ingest_summary = _load_auto_ingest_summary()
auto_ingest_detail = _load_auto_ingest_detail()
active_backup_outputs_dir = _active_backup_outputs_dir(
    auto_ingest_plan,
    str(auto_ingest_summary.get("run_id") or auto_ingest_plan.get("run_id") or ""),
)
remote_job_audit = _cached_remote_job_audit(remote_root, json.dumps(auto_ingest_plan, sort_keys=True)) if remote_root else {"rows": [], "skipped": []}

# â”€â”€ Sidebar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

st.sidebar.code(
    f"commit: {runtime['commit']}\nhost:   {runtime['hostname']}\nup:     {runtime['started_at']}",
)

with st.sidebar.expander("Cluster Status", expanded=True):
    for h in ["c240", "gen8", "r630", "g9"]:
        alive = _check_host_online(h)
        icon = "✓" if alive else "✕"
        color = "#16a34a" if alive else "#dc2626"
        state_label = "Online" if alive else "Offline"
        # Show active dataset count for this host from cached statuses
        active_on_host = [s for s in cluster_live_statuses if str(s.get("host", "")).lower() == h]
        if alive and active_on_host:
            datasets_str = ", ".join(
                f"{s.get('market','?')} {s.get('timeframe','?')}" for s in active_on_host
            )
            st.markdown(
                f'<span style="color:{color};font-weight:800">{icon}</span> '
                f'<strong>{html.escape(h)}</strong> - {html.escape(datasets_str)}',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span style="color:{color};font-weight:800">{icon}</span> '
                f'<strong>{html.escape(h)}</strong> ({state_label})',
                unsafe_allow_html=True,
            )

st.sidebar.divider()
if cluster_live_statuses:
    st.sidebar.caption(f"Active runs: {len(cluster_live_statuses)} dataset(s) across cluster")
elif auto_ingest_summary.get("active"):
    st.sidebar.caption(
        f"Auto-ingest active: {auto_ingest_summary.get('ingested_count')}/"
        f"{auto_ingest_summary.get('total_jobs')} datasets ingested"
    )
elif monitor_run:
    st.sidebar.caption("Live Monitor follows the active run automatically.")
else:
    st.sidebar.caption("No active runs detected.")

if selected_run:
    selected_status      = selected_run["launcher_status"]
    selected_manifest    = selected_run["run_manifest"]
    selected_run_dir     = selected_run["run_dir"]
    selected_outputs_dir = selected_run["outputs_dir"]
    run_outcome      = str(selected_status.get("run_outcome") or "unknown")
    host_label       = str(selected_manifest.get("host") or "c240")
    run_state        = str(selected_status.get("state") or "unknown")
    operator_summary = operator_action_summary(selected_status)
    run_category     = classify_run_status(selected_status)
else:
    selected_status = {}; selected_manifest = {}
    selected_run_dir = None; selected_outputs_dir = None
    run_outcome = "unknown"
    run_state = "unknown"; operator_summary = "No runs available yet."
    run_category = "unknown"; host_label = "none"

analysis_run            = selected_run
analysis_status         = selected_status
analysis_manifest       = selected_manifest
analysis_run_dir        = selected_run_dir
analysis_outputs_dir    = selected_outputs_dir
analysis_run_outcome    = run_outcome
analysis_run_category   = run_category

if monitor_run:
    monitor_status        = monitor_run["launcher_status"]
    monitor_manifest      = monitor_run["run_manifest"]
    monitor_run_dir       = monitor_run["run_dir"]
    monitor_outputs_dir   = monitor_run["outputs_dir"]
    monitor_run_outcome   = str(monitor_status.get("run_outcome") or "unknown")
    monitor_host          = str(monitor_manifest.get("host") or "c240")
    monitor_run_category  = classify_run_status(monitor_status)
    monitor_run_state     = str(monitor_status.get("state") or "unknown")
else:
    monitor_status = {}; monitor_manifest = {}
    monitor_run_dir = None; monitor_outputs_dir = None
    monitor_run_outcome = "unknown"; monitor_host = "none"
    monitor_run_category = "unknown"; monitor_run_state = "unknown"

is_running       = (monitor_run_category == "running") or bool(cluster_live_statuses) or bool(auto_ingest_summary.get("active"))
display_run_outcome = "running" if is_running else monitor_run_outcome
display_host     = monitor_host

if monitor_run:
    selected_run     = monitor_run
    selected_status  = monitor_status
    selected_manifest = monitor_manifest
    selected_run_dir  = monitor_run_dir
    selected_outputs_dir = monitor_outputs_dir
    run_outcome = monitor_run_outcome
    host_label  = monitor_host
    run_category = monitor_run_category
    run_state    = monitor_run_state

# â”€â”€ Banner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

run_id_display = (
    (auto_ingest_summary.get("run_id") if auto_ingest_summary.get("active") else "")
    or selected_status.get("run_id")
    or (selected_run_dir.name if selected_run_dir else "")
    or ("cluster-active" if cluster_live_statuses else "no run")
)
n_active = len(cluster_live_statuses)
if n_active:
    active_str = f"{n_active} dataset(s) running"
elif auto_ingest_summary.get("active"):
    active_str = (
        f"{auto_ingest_summary.get('ingested_count')}/"
        f"{auto_ingest_summary.get('total_jobs')} datasets ingested"
    )
else:
    active_str = display_run_outcome.upper()
scope_display = str(auto_ingest_detail.get("scope") or "").strip()
st.markdown(f"""
<div class="console-banner">
    <h1>Current Run</h1>
    <p>{active_str} &nbsp;|&nbsp;
       Host: <strong><span style="color:#0ea5e9">{runtime['hostname'].upper()}</span></strong> &nbsp;|&nbsp;
       Run: <strong>{html.escape(str(run_id_display))}</strong></p>
    {f'<p>{html.escape(scope_display)}</p>' if scope_display else ''}
</div>
""", unsafe_allow_html=True)

# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def render_table(df: pd.DataFrame) -> None:
    try:
        st.dataframe(df, use_container_width=True)
    except Exception:
        st.code(df.to_string(index=False))


def format_current_leaders(leaders_df: pd.DataFrame | None) -> pd.DataFrame | None:
    if leaders_df is None or leaders_df.empty:
        return None
    display = leaders_df.copy()
    rename_map = {
        "strategy_name": "Strategy", "leader_strategy_name": "Strategy",
        "strategy_type": "Family", "dataset": "Dataset",
        "market": "Market", "timeframe": "Timeframe",
        "profit_factor": "PF", "leader_pf": "PF",
        "net_pnl": "Net Profit", "leader_net_pnl": "Net Profit",
        "max_drawdown": "Drawdown", "leader_max_drawdown": "Drawdown",
        "total_trades": "Trades", "leader_trades": "Trades",
        "quality_flag": "Quality",
    }
    existing = [c for c in rename_map if c in display.columns]
    if not existing:
        return display
    display = display[existing].copy()
    display.columns = [rename_map[c] for c in existing]
    display = display.loc[:, ~display.columns.duplicated()]
    for nc in ("PF", "Trades"):
        if nc in display.columns:
            display[nc] = pd.to_numeric(display[nc], errors="coerce").round(2)
    for mc in ("Net Profit", "Drawdown"):
        if mc in display.columns:
            display[mc] = pd.to_numeric(display[mc], errors="coerce").apply(
                lambda v: f"${v:,.0f}" if pd.notna(v) else "â€”"
            )
    return display


# â”€â”€ Live Monitor rendering â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _dataset_card_html(status: dict) -> str:
    host = str(status.get("host", "?")).lower()
    market = html.escape(str(status.get("market", "?")))
    timeframe = html.escape(str(status.get("timeframe", "?")))
    current_family = str(status.get("current_family", "")).strip()
    current_stage = str(status.get("current_stage", "?"))
    pct = float(status.get("progress_pct", 0) or 0)
    elapsed = float(status.get("elapsed_seconds", 0) or 0)
    completed = list(status.get("families_completed", []) or [])
    remaining = list(status.get("families_remaining", []) or [])
    is_done = (
        current_stage.upper() in {"DONE", "COMPLETE", "COMPLETED"}
        and not remaining
    ) or (pct >= 100 and not remaining)

    # ETA: show whole-dataset projection (current family + remaining families).
    total_eta = estimate_total_eta_seconds(status)
    n_completed = len(completed)
    n_remaining = len(remaining)
    total_families = n_completed + 1 + n_remaining if not is_done else max(n_completed, 1)
    if is_done:
        total_pct = 100.0
    else:
        total_pct = ((n_completed + (pct / 100.0)) / total_families) * 100.0
    total_pct = max(0.0, min(100.0, total_pct))

    if is_done:
        eta_html = f'<div class="eta-done">Done</div>'
        stage_html = f'<div class="stage-line">Elapsed: {format_duration_short(elapsed)}</div>'
    elif total_eta and total_eta > 0:
        eta_html = f'<div class="eta-value">{format_duration_short(total_eta)}</div>'
        fam_clean = current_family.replace("_", " ") or "starting"
        stage_html = f'<div class="stage-line">ETA whole timeframe &bull; on {html.escape(fam_clean)} ({n_completed}/{total_families} families)</div>'
    else:
        eta_html = '<div class="eta-unknown">calculating...</div>'
        fam_clean = current_family.replace("_", " ") or "starting"
        stage_html = f'<div class="stage-line">{html.escape(current_stage)} &bull; {html.escape(fam_clean)} ({n_completed}/{total_families} families)</div>'

    # Progress bar = total dataset progress (all families)
    bar_cls = "prog-done" if is_done else ("prog-waiting" if total_pct < 1 else "prog-active")
    prog_html = (
        f'<div class="prog-outer">'
        f'<div class="prog-inner {bar_cls}" style="width:{total_pct:.1f}%"></div>'
        f'</div>'
        f'<div class="prog-pct">{total_pct:.0f}% complete</div>'
    )

    # Host badge
    host_cls = f"host-{host}" if host in ("c240", "r630", "gen8", "g9") else "host-unknown"
    badge_html = f'<span class="host-badge {host_cls}">{host}</span>'

    # Family group mini bars
    completed_set = set(completed)
    fam_html = '<div class="fam-groups">'
    for group_label, families in FAMILY_GROUPS:
        n_total = len(families)
        n_done = sum(1 for f in families if f in completed_set)
        is_active_grp = not is_done and any(
            current_family == f or current_family.startswith(f + "_") for f in families
        )
        if n_done == n_total:
            fill_cls = "fg-done"
            fill_pct = 100
        elif is_active_grp:
            fill_cls = "fg-active"
            fill_pct = max(int(n_done / n_total * 100), 5)
        else:
            fill_cls = "fg-wait"
            fill_pct = int(n_done / n_total * 100)
        fam_html += (
            f'<div class="fam-row">'
            f'<div class="fam-label">{html.escape(group_label)}</div>'
            f'<div class="fam-bar"><div class="fam-fill {fill_cls}" style="width:{fill_pct}%"></div></div>'
            f'<div class="fam-count">{n_done}/{n_total}</div>'
            f'</div>'
        )
    fam_html += "</div>"

    return (
        f'<div class="ds-card">'
        f'<div class="ds-card-header">'
        f'<div>'
        f'<div><span class="ds-title">{market}</span><span class="ds-tf">{timeframe}</span></div>'
        f'<div class="ds-elapsed">Elapsed: {format_duration_short(elapsed)}</div>'
        f'</div>'
        f'{badge_html}'
        f'</div>'
        f'{prog_html}'
        f'{eta_html}'
        f'{stage_html}'
        f'{fam_html}'
        f'</div>'
    )


def render_live_monitor(statuses: list[dict]) -> None:
    if not statuses:
        if auto_ingest_summary.get("active"):
            total = int(auto_ingest_summary.get("total_jobs") or 0)
            done = int(auto_ingest_summary.get("ingested_count") or 0)
            remaining = max(total - done, 0)
            pct = (done / total * 100.0) if total else 0.0
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Published", f"{done}/{total}")
            k2.metric("Remaining", remaining)
            k3.metric("Overall", f"{pct:.0f}%")
            k4.metric("Remote SSH", "On")
            st.progress(min(max(pct / 100.0, 0.0), 1.0))

            host_rows = auto_ingest_detail.get("host_rows", [])
            if host_rows:
                st.subheader("Server Progress")
                for row in host_rows:
                    host = str(row.get("host") or "unknown")
                    host_done = int(row.get("done") or 0)
                    host_total = int(row.get("total") or 0)
                    host_pct = float(row.get("pct") or 0.0)
                    st.markdown(f"**{host}** - {host_done}/{host_total} datasets published ({host_pct:.0f}%)")
                    st.progress(min(max(host_pct / 100.0, 0.0), 1.0))
                    jobs = row.get("jobs", [])
                    if isinstance(jobs, list):
                        recent_done = [
                            f"{job.get('market')} {job.get('timeframe')}"
                            for job in jobs
                            if isinstance(job, dict) and bool(job.get("done"))
                        ][-6:]
                        remaining_jobs = [
                            f"{job.get('market')} {job.get('timeframe')}"
                            for job in jobs
                            if isinstance(job, dict) and not bool(job.get("done"))
                        ][:8]
                        c_done, c_wait = st.columns(2)
                        c_done.caption("Recent published: " + (", ".join(recent_done) if recent_done else "none yet"))
                        c_wait.caption("Next/remaining: " + (", ".join(remaining_jobs) if remaining_jobs else "none"))

            recent_events = auto_ingest_detail.get("recent_events", [])
            if recent_events:
                st.subheader("Completed / Published In Last 24 Hours")
                recent_df = pd.DataFrame(recent_events)
                st.dataframe(
                    recent_df.rename(
                        columns={
                            "time": "Time",
                            "host": "Host",
                            "market": "Market",
                            "timeframe": "Timeframe",
                        }
                    ),
                    use_container_width=True,
                    height=min(380, 36 + len(recent_events) * 35),
                )

            last_line = auto_ingest_detail.get("last_line") or auto_ingest_summary.get("last_line") or ""
            if last_line:
                st.caption(f"Watcher: {last_line}")
            return
        st.info(
            "No active sweep detected on c240, gen8, r630, or g9.  "
            "Start a run with: python run_cluster_sweep.py --jobs ES:daily --workers 72"
        )
        return

    # KPI strip
    reporting_hosts = len({str(s.get("host", "")).lower() for s in statuses if s.get("host")})
    reachable_hosts = sum(1 for h in ["c240", "gen8", "r630", "g9"] if _check_host_online(h))
    n_fam_done = sum(len(s.get("families_completed", []) or []) for s in statuses)
    n_fam_remaining = sum(len(s.get("families_remaining", []) or []) for s in statuses)
    n_fam_total = n_fam_done + n_fam_remaining or len(statuses)
    etas = [float(s.get("eta_seconds", 0) or 0) for s in statuses]
    max_eta = max((e for e in etas if e > 0), default=None)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Reachable Hosts", f"{reachable_hosts}/4")
    k2.metric("Reporting Datasets", len(statuses))
    k3.metric("Live Families Done", f"{n_fam_done} / {n_fam_total}")
    k4.metric("Max Current ETA", format_duration_short(max_eta) if max_eta else "â€”")

    # Dataset cards
    cards = "".join(_dataset_card_html(s) for s in statuses)
    st.markdown(f'<div class="dataset-grid">{cards}</div>', unsafe_allow_html=True)
    status_hosts = {str(s.get("host", "")).lower() for s in statuses if s.get("host")}
    missing_hosts = []
    for host in ["c240", "gen8", "r630", "g9"]:
        if host in status_hosts:
            continue
        if _check_host_online(host):
            ssh_note = "reachable; SSH status unavailable" if not _check_host_alive(host) else "online; no active status file"
            missing_hosts.append(f"{host}: {ssh_note}")
    if missing_hosts:
        st.caption("Other hosts: " + " | ".join(missing_hosts))

    published_keys = {
        str(job.get("key") or "")
        for row in auto_ingest_detail.get("host_rows", [])
        if isinstance(row, dict)
        for job in (row.get("jobs", []) if isinstance(row.get("jobs"), list) else [])
        if isinstance(job, dict) and bool(job.get("done"))
    }
    audit_rows = remote_job_audit.get("rows", []) if isinstance(remote_job_audit, dict) else []
    completed_unpublished = []
    for row in audit_rows if isinstance(audit_rows, list) else []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").upper()
        job_key = str(row.get("job_key") or "")
        if status in {"DONE", "COMPLETE", "COMPLETED"} and job_key not in published_keys:
            completed_unpublished.append(
                {
                    "Completed": _format_local_dt(str(row.get("timestamp") or "")),
                    "Host": str(row.get("host") or ""),
                    "Dataset": f"{row.get('market')} {row.get('timeframe')}",
                    "Publish": "waiting for ingest",
                    "_sort": str(row.get("timestamp") or ""),
                }
            )
    completed_unpublished.sort(key=lambda item: str(item.get("_sort") or ""), reverse=True)
    if completed_unpublished:
        st.subheader("Completed On Servers, Not Yet Published")
        table = pd.DataFrame([{k: v for k, v in row.items() if k != "_sort"} for row in completed_unpublished])
        st.dataframe(table, use_container_width=True, height=min(300, 36 + len(table) * 35))
    skipped = remote_job_audit.get("skipped", []) if isinstance(remote_job_audit, dict) else []
    if skipped:
        st.caption("Audit gaps: " + " | ".join(str(item) for item in skipped))


# â”€â”€ Secondary: console-run monitor (old pipeline) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def render_monitor_progress(summary: dict) -> None:
    rows = summary.get("rows", [])
    if not rows:
        st.info("No dataset progress available yet.")
        return
    completed = int(summary.get("completed_items", 0) or 0)
    total = int(summary.get("total_items", 0) or 0)
    pct = (completed / total * 100.0) if total else 0.0
    st.markdown(
        f'<div class="monitor-card">'
        f'<h3>Run Checklist</h3>'
        f'<div class="subtle">Completed: <strong>{completed}</strong> / <strong>{total}</strong> ({pct:.0f}%)</div>'
        f'<div class="monitor-grid">',
        unsafe_allow_html=True,
    )
    cards: list[str] = []
    for row in rows:
        items_html: list[str] = []
        for item in row["items"]:
            icon = {"complete": "v", "active": ">", "failed": "!", "pending": "o"}.get(item["status"], "o")
            detail = item["stage"] if item["status"] == "active" and item["stage"] else ""
            prog_pct = item.get("progress_pct", 100 if item["status"] == "complete" else 0)
            bar_html = (
                f'<div class="progress-bar-bg">'
                f'<div class="progress-bar-fill" style="width:{prog_pct}%"></div>'
                f'</div>'
            )
            items_html.append(
                f'<div class="family-pill {item["status"]}">'
                f'<span>{icon} {html.escape(item["family_label"])}</span>'
                f'{bar_html}'
                f'<span>{html.escape(detail)}</span>'
                f'</div>'
            )
        cards.append(
            f'<div class="dataset-card">'
            f'<div class="dataset-head">'
            f'<div class="dataset-title">{html.escape(row["label"])}</div>'
            f'<div class="dataset-meta">{row["progress_pct"]:.0f}%</div>'
            f'</div>'
            f'<div class="family-list">{"".join(items_html)}</div>'
            f'</div>'
        )
    st.markdown("".join(cards) + "</div></div>", unsafe_allow_html=True)


# â”€â”€ TABS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

tab_monitor, tab_results, tab_history, tab_system, tab_ultimate = st.tabs(
    ["Live Monitor", "Results", "Run History", "System", "Ultimate Leaderboard"]
)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 1 â€” LIVE MONITOR
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

with tab_monitor:

    if is_running:
        st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)

    # â”€â”€ Primary: direct cluster activity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    render_live_monitor(cluster_live_statuses)

    # â”€â”€ Secondary: console-storage run progress â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if selected_run_dir or monitor_run:
        with st.expander("Console Run Records", expanded=False):
            dataset_statuses = fetch_live_dataset_statuses(selected_run_dir) if selected_run_dir else []
            monitor_summary = build_monitor_progress_rows(dataset_statuses, selected_manifest)
            log_tail = load_log_tail(selected_run_dir) if selected_run_dir else ""
            preemption_warning = detect_preemption_warning(selected_status, log_tail)
            run_scope = format_run_scope(selected_manifest)
            focus = monitor_summary.get("active_focus") or monitor_summary.get("recent_focus") or {}

            if preemption_warning:
                st.markdown(f'<div class="hero-banner">{html.escape(preemption_warning)}</div>', unsafe_allow_html=True)

            st.markdown(
                f'<div class="live-scope-card">'
                f'<h2>Console run scope</h2>'
                f'<div class="scope-line">{html.escape(run_scope)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            overview_col, leader_col = st.columns([1.7, 1.0], gap="large")
            with overview_col:
                render_monitor_progress(monitor_summary)
            with leader_col:
                focus_value = focus.get("label") or "Awaiting first active bucket"
                focus_detail = (
                    focus.get("stage")
                    or ("Most recently completed" if monitor_summary.get("recent_focus") else "Not yet available")
                )
                st.markdown(
                    f'<div class="focus-card">'
                    f'<div class="eyebrow">Current Focus</div>'
                    f'<div class="value">{html.escape(str(focus_value))}</div>'
                    f'<div class="detail">{html.escape(str(focus_detail))}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                current_leaders = format_current_leaders(
                    load_current_leader_snapshot(selected_outputs_dir, monitor_summary)
                )
                st.markdown(
                    '<div class="monitor-card"><h3>Current Leaders</h3>'
                    '<div class="subtle">Best available leaders for the active bucket.</div></div>',
                    unsafe_allow_html=True,
                )
                if current_leaders is not None and not current_leaders.empty:
                    st.dataframe(current_leaders, use_container_width=True, height=min(380, 36 + len(current_leaders) * 35))
                else:
                    st.info("No leaders yet for this focus.")

    # â”€â”€ Promoted candidates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    promoted_outputs_dir = active_backup_outputs_dir or selected_outputs_dir
    if promoted_outputs_dir:
        st.divider()
        st.subheader("Promoted Candidates")
        st.caption(f"Strategies that passed the promotion gate. Source: {promoted_outputs_dir}")
        candidates_df = load_promoted_candidates(promoted_outputs_dir)
        if candidates_df is not None and not candidates_df.empty:
            col_map = {
                "completed_at": "Completed",
                "dataset": "Dataset",
                "strategy_name": "Strategy", "strategy_type": "Family",
                "profit_factor": "PF", "is_pf": "IS PF", "oos_pf": "OOS PF",
                "net_pnl": "Net PnL ($)", "total_trades": "Trades",
                "trades_per_year": "Trades/yr", "quality_flag": "Quality",
            }
            existing = {k: v for k, v in col_map.items() if k in candidates_df.columns}
            if existing:
                disp = candidates_df[list(existing.keys())].copy()
                disp.columns = list(existing.values())
                for col in ["PF", "IS PF", "OOS PF", "Trades/yr"]:
                    if col in disp.columns:
                        disp[col] = pd.to_numeric(disp[col], errors="coerce").round(2)
                if "Completed" in disp.columns:
                    completed = pd.to_datetime(disp["Completed"], errors="coerce", utc=True).dt.tz_convert(
                        datetime.now().astimezone().tzinfo
                    )
                    disp["Completed"] = completed.dt.strftime("%d %b %Y %H:%M").fillna("")
                if "Net PnL ($)" in disp.columns:
                    disp["Net PnL ($)"] = pd.to_numeric(disp["Net PnL ($)"], errors="coerce").apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "â€”"
                    )
                st.dataframe(disp, use_container_width=True, height=min(400, 36 + len(disp) * 35))
                st.caption(f"{len(candidates_df)} candidates promoted")
            else:
                render_table(candidates_df.head(20))
        elif is_running:
            st.info("No candidates yet â€” families still running.")
        else:
            st.info("No promoted candidates file found for this run.")

    # â”€â”€ Engine log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with st.expander("Engine log (last 40 lines)", expanded=False):
        log_tail_text = load_log_tail(selected_run_dir) if selected_run_dir else ""
        if log_tail_text:
            st.code("\n".join(log_tail_text.splitlines()[-40:]), language="text")
        else:
            st.info("No engine log found.")

    if is_running:
        st.caption("Auto-refreshes every 5 minutes while runs are active.")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 2 â€” RESULTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

with tab_results:

    if not analysis_run or not analysis_outputs_dir:
        st.info("No completed run with local outputs is available yet.")
    else:
        results = load_strategy_results(analysis_outputs_dir)
        run_id  = analysis_status.get("run_id", analysis_run_dir.name if analysis_run_dir else "?")
        st.caption(f"Results from: `{run_id}` -> `{analysis_outputs_dir}`")

        st.subheader("Strategy Leaderboard")
        if results["leaderboard"] is not None:
            lb = results["leaderboard"]
            col_map = {
                "strategy_name": "Strategy", "leader_strategy_name": "Strategy",
                "strategy_type": "Family", "quality_flag": "Quality",
                "accepted_final": "Accepted", "profit_factor": "PF", "leader_pf": "PF",
                "is_pf": "IS PF", "oos_pf": "OOS PF", "recent_12m_pf": "R12m PF",
                "net_pnl": "Net PnL", "leader_net_pnl": "Net PnL",
                "total_trades": "Trades", "leader_trades": "Trades",
                "leader_trades_per_year": "Trades/Yr", "calmar_ratio": "Calmar",
                "oos_is_pf_ratio": "OOS/IS", "leader_win_rate": "Win%",
                "leader_max_drawdown": "Max DD", "leader_pct_profitable_years": "Prof Yrs%",
                "timeframe": "TF", "market": "Market", "dataset": "Dataset",
            }
            existing = {k: v for k, v in col_map.items() if k in lb.columns}
            if existing:
                disp = lb[list(existing.keys())].copy()
                disp.columns = list(existing.values())
                seen: dict[str, int] = {}
                new_cols = []
                for c in disp.columns:
                    if c in seen:
                        seen[c] += 1; new_cols.append(f"{c}.{seen[c]}")
                    else:
                        seen[c] = 0; new_cols.append(c)
                disp.columns = new_cols
                for mc in ["Net PnL", "Max DD"]:
                    if mc in disp.columns:
                        disp[mc] = pd.to_numeric(disp[mc], errors="coerce").apply(
                            lambda x: f"${x:,.0f}" if pd.notna(x) else "â€”"
                        )
                for rc in ["PF", "IS PF", "OOS PF", "R12m PF", "Calmar", "Win%", "Prof Yrs%", "Trades/Yr"]:
                    if rc in disp.columns:
                        disp[rc] = pd.to_numeric(disp[rc], errors="coerce").round(2)
                col_config: dict = {}
                if "Quality" in disp.columns:
                    col_config["Quality"] = st.column_config.TextColumn(
                        "Quality",
                        help="ROBUST=strong both periods, STABLE=acceptable, MARGINAL=weak, BROKEN=overfit",
                    )
                st.dataframe(disp, column_config=col_config, use_container_width=True)
            else:
                render_table(lb.head(20))
            st.caption(f"{len(lb)} strategies")
        else:
            st.info("No leaderboard file found.")

        if results["portfolio"] is not None:
            st.divider()
            st.subheader("Portfolio Review")
            render_table(results["portfolio"])

        if results["returns"] is not None:
            st.divider()
            st.subheader("Equity Curves")
            returns_df = results["returns"]
            try:
                import plotly.graph_objects as go
                date_col   = next((c for c in returns_df.columns if "date" in c.lower() or "time" in c.lower()), None)
                strat_cols = [c for c in returns_df.columns if c != date_col] if date_col else []
                if date_col and strat_cols:
                    fig = go.Figure()
                    for col in strat_cols:
                        cumsum = pd.to_numeric(returns_df[col], errors="coerce").fillna(0).cumsum()
                        fig.add_trace(go.Scatter(x=returns_df[date_col], y=cumsum,
                                                  mode="lines", name=col.split("_")[-1], line=dict(width=2)))
                    fig.add_vline(x="2019-01-01", line_dash="dash", line_color="orange",
                                  annotation_text="OOS start")
                    fig.update_layout(title="Cumulative PnL", template="plotly_dark", height=400,
                                      legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                      margin=dict(l=40, r=20, t=60, b=40))
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                render_table(returns_df.head(50))
                st.caption(f"Chart error: {e}")

        if results["yearly"] is not None:
            st.divider()
            st.subheader("Annual PnL by Strategy")
            yearly_df = results["yearly"]
            try:
                import plotly.express as px
                year_col = next((c for c in yearly_df.columns if "year" in c.lower()), yearly_df.columns[0])
                pnl_col  = next((c for c in yearly_df.columns if "pnl" in c.lower()), None)
                name_col = next((c for c in yearly_df.columns if "name" in c.lower() or "strategy" in c.lower()), None)
                if pnl_col and name_col:
                    yearly_df = yearly_df.copy()
                    yearly_df["_color"] = pd.to_numeric(yearly_df[pnl_col], errors="coerce").apply(
                        lambda x: "Profit" if x >= 0 else "Loss"
                    )
                    fig = px.bar(yearly_df, x=year_col, y=pnl_col, color="_color",
                                 facet_col=name_col if yearly_df[name_col].nunique() > 1 else None,
                                 color_discrete_map={"Profit": "#10b981", "Loss": "#ef4444"},
                                 template="plotly_dark", title="Annual PnL",
                                 labels={pnl_col: "PnL ($)", year_col: "Year"})
                    fig.add_vline(x=2018.5, line_dash="dash", line_color="orange",
                                  annotation_text="OOS ->", annotation_position="top left")
                    fig.update_layout(height=350, showlegend=False, margin=dict(l=40, r=20, t=60, b=40))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    render_table(yearly_df)
            except Exception:
                render_table(yearly_df)

        if results.get("cross_correlation") is not None:
            st.divider()
            st.subheader("Cross-Timeframe Correlations")
            st.caption("All accepted strategies across all timeframes")
            try:
                import plotly.express as px
                ctf_df = results["cross_correlation"].copy()
                idx_col = ctf_df.columns[0]
                ctf_df = ctf_df.set_index(idx_col)
                def _shorten(s: str) -> str:
                    s = str(s)
                    if "_Refined" in s:
                        parts = s.split("_Refined", 1)
                        return parts[0].split("_")[-1] + "_R" + parts[1][:8]
                    if "_ES_" in s:
                        return s.split("_ES_")[-1][-25:]
                    return s[-25:]
                ctf_df.index = [_shorten(i) for i in ctf_df.index]
                ctf_df.columns = [_shorten(c) for c in ctf_df.columns]
                n = len(ctf_df)
                fig = px.imshow(ctf_df, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                                text_auto=".2f", template="plotly_dark",
                                title=f"Cross-Timeframe Correlation ({n}x{n})")
                fig.update_layout(height=max(350, n * 40 + 80), margin=dict(l=40, r=20, t=60, b=40))
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                render_table(results["cross_correlation"])
                st.caption(f"Heatmap error: {e}")
            if results.get("cross_portfolio") is not None:
                with st.expander("Cross-timeframe portfolio review", expanded=False):
                    render_table(results["cross_portfolio"])

        if results["correlation"] is not None:
            st.divider()
            st.subheader("Per-Dataset Correlations")
            try:
                import plotly.express as px
                corr_df = results["correlation"].copy()
                idx_col = corr_df.columns[0]
                corr_df = corr_df.set_index(idx_col)
                corr_df.index   = [i.split("_ES_")[-1] if "_ES_" in str(i) else str(i)[-30:] for i in corr_df.index]
                corr_df.columns = [c.split("_ES_")[-1] if "_ES_" in str(c) else str(c)[-30:] for c in corr_df.columns]
                fig = px.imshow(corr_df, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                                text_auto=".2f", template="plotly_dark")
                fig.update_layout(height=350, margin=dict(l=40, r=20, t=40, b=40))
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                render_table(results["correlation"])
                st.caption(f"Heatmap error: {e}")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 3 â€” RUN HISTORY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

with tab_history:

    st.subheader("All Console Runs")
    if run_records:
        rows = []
        for record in run_records:
            status   = record["launcher_status"]
            manifest = record["run_manifest"]
            cost_i   = estimate_run_cost(record)
            cat      = classify_run_status(status)
            datasets = manifest.get("datasets", [])
            ds_str   = (
                ", ".join(f"{d.get('market','?')} {d.get('timeframe','?')}" for d in datasets)
                if datasets else "â€”"
            )
            rows.append({
                "Run ID":   status.get("run_id", record["run_dir"].name),
                "Updated":  status.get("updated_utc", "unknown"),
                "Status":   cat.upper(),
                "Outcome":  badge_for_value(status.get("run_outcome")),
                "Host":     manifest.get("host", "local"),
                "Datasets": ds_str,
                "Runtime":  format_duration_short(cost_i.get("elapsed_seconds", 0)),
            })
        render_table(pd.DataFrame(rows))
    else:
        st.warning(f"No runs found in: `{canonical_runs_root(storage)}`")

    if analysis_run:
        with st.expander("Selected Run Detail", expanded=False):
            rid = analysis_status.get("run_id", analysis_run_dir.name if analysis_run_dir else "?")
            st.markdown(
                f"**Run ID**: `{rid}`  \n"
                f"**Path**: `{analysis_run_dir}`  \n"
                f"**Updated**: `{analysis_status.get('updated_utc', 'unknown')}`  \n"
                f"**Host**: `{analysis_manifest.get('host','?')}`  \n"
                f"**State**: `{analysis_status.get('state','unknown')}`  \n"
                f"**Bundle size**: `{format_bytes(analysis_status.get('bundle_size_bytes'))}`"
            )
            recovery = analysis_status.get("recovery_commands") or []
            if recovery:
                st.caption("Recovery commands")
                st.code("\n".join(recovery), language="bash")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 4 â€” SYSTEM
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

with tab_system:

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Uploads", str(len(uploaded_datasets)))
    s2.metric("Runs",    str(len(run_records)))
    s3.metric("Exports", str(len(export_files)))
    s4.metric("Host",    runtime["hostname"])

    st.subheader("Uploaded Datasets")
    if uploaded_datasets:
        rows = []
        for entry in uploaded_datasets:
            info = parse_dataset_filename(entry.name)
            rows.append({"Filename": entry.name, "Size": format_bytes(entry.size_bytes),
                         "Market": info["market"], "Timeframe": info["timeframe"],
                         "Modified": format_datetime(entry.modified_at)})
        render_table(pd.DataFrame(rows))
    else:
        st.info(f"No datasets in `{storage.uploads}`")

    st.divider()
    st.subheader("System Health")
    render_table(pd.DataFrame([
        {"Check": "Uploads directory",  "Status": "OK" if UPLOADS_DIR.exists() else "Missing"},
        {"Check": "Runs directory",     "Status": "OK" if RUNS_DIR.exists() else "Missing"},
        {"Check": "Exports directory",  "Status": "OK" if EXPORTS_DIR.exists() else "Missing"},
        {"Check": "Datasets uploaded",  "Status": f"{len(uploaded_datasets)}" if uploaded_datasets else "None"},
        {"Check": "Latest run state",   "Status": console_run_status.get("run_state", "unknown")},
        {"Check": "Dashboard commit",   "Status": runtime["commit"]},
        {"Check": "Active cluster jobs", "Status": str(len(cluster_live_statuses))},
    ]))

    st.divider()
    st.subheader("Storage Paths")
    st.code(
        f"root:    {storage.root}\n"
        f"uploads: {storage.uploads}\n"
        f"runs:    {canonical_runs_root(storage)}\n"
        f"exports: {storage.exports}",
        language="text",
    )

    st.divider()
    st.subheader("Quick Commands")
    st.markdown("**Plan a distributed batch (10-market The5ers-first):**")
    st.code(
        "python run_cluster_sweep.py --distributed-plan \\\n"
        "  --hosts c240:80 gen8:48 r630:88 g9:48 \\\n"
        "  --markets ES NQ YM RTY DAX N225 FTSE STOXX CAC GC \\\n"
        "  --timeframes daily 60m 30m 15m \\\n"
        "  --remote-root /tmp/psc",
        language="bash",
    )
    st.markdown("**Run a local batch on c240:**")
    st.code(
        "python run_cluster_sweep.py \\\n"
        "  --markets ES NQ YM GC \\\n"
        "  --timeframes daily 60m 30m 15m \\\n"
        "  --data-dir /data/market_data/cfds/ohlc_engine",
        language="bash",
    )
    st.markdown("**Check live status files on r630:**")
    st.code(
        "ssh r630 \"find /tmp -maxdepth 4 -path '*/Outputs/*/status.json' | sort\"",
        language="bash",
    )
    st.markdown("**Ingest + finalize canonical results:**")
    st.code("python run_cluster_results.py finalize", language="bash")
    st.markdown("**Mirror to Google Drive backup:**")
    st.code(
        "python run_cluster_results.py mirror-backup \\\n"
        "  --storage-root /data/sweep_results \\\n"
        "  --backup-root \"/mnt/gdrive/strategy-data-backup\"",
        language="bash",
    )
    st.markdown("**Restart dashboard:**")
    st.code("sudo systemctl restart strategy-dashboard", language="bash")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 5 â€” ULTIMATE LEADERBOARD
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

with tab_ultimate:

    @st.cache_data(ttl=300)
    def _load_ultimate_leaderboard(use_gated: bool = False) -> pd.DataFrame:
        try:
            from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard
            df = aggregate_ultimate_leaderboard()
            if use_gated and "gate_fragility_status" in df.columns:
                df = df[df["gate_fragility_status"].str.upper() != "FAIL"].copy()
            return df
        except Exception as exc:
            return pd.DataFrame({"error": [str(exc)]})

    col_refresh, col_spacer, col_view = st.columns([1, 3, 2])
    with col_refresh:
        if st.button("Refresh", key="ul_refresh"):
            _load_ultimate_leaderboard.clear()
    with col_view:
        view_mode = st.radio(
            "Pool",
            ["All (raw)", "Gated (survivors only)"],
            horizontal=True,
            key="ul_view_mode",
        )

    use_gated = view_mode == "Gated (survivors only)"
    ul_df = _load_ultimate_leaderboard(use_gated=use_gated)

    if ul_df.empty or "error" in ul_df.columns:
        if "error" in ul_df.columns:
            st.error(f"Error: {ul_df['error'].iloc[0]}")
        else:
            st.info("No accepted strategies found. Run a sweep first.")
    else:
        total_strats   = len(ul_df)
        robust_count   = int((ul_df.get("quality_flag", pd.Series()) == "ROBUST").sum()) if "quality_flag" in ul_df.columns else 0
        stable_count   = int(ul_df["quality_flag"].str.startswith("STABLE").sum()) if "quality_flag" in ul_df.columns else 0
        unique_markets = ul_df["market"].nunique() if "market" in ul_df.columns else "â€”"
        unique_tfs     = ul_df["timeframe"].nunique() if "timeframe" in ul_df.columns else (
            ul_df["dataset"].nunique() if "dataset" in ul_df.columns else 0
        )
        runs_scanned   = ul_df["run_id"].nunique() if "run_id" in ul_df.columns else 0

        u1, u2, u3, u4, u5 = st.columns(5)
        u1.metric("Total Strategies", total_strats)
        u2.metric("ROBUST", robust_count)
        u3.metric("STABLE", stable_count)
        u4.metric("Markets", unique_markets)
        u5.metric("Timeframes", unique_tfs)

        st.divider()

        # Filters
        filtered = ul_df.copy()
        f1, f2, f3, f4, f5 = st.columns(5)
        with f1:
            if "market" in filtered.columns:
                mkt_all = sorted(filtered["market"].dropna().unique().tolist())
                sel_mkt = st.multiselect("Market", mkt_all, default=mkt_all, key="ul_mkt")
                if sel_mkt:
                    filtered = filtered[filtered["market"].isin(sel_mkt)]
        with f2:
            if "strategy_type" in filtered.columns:
                types_all = sorted(filtered["strategy_type"].dropna().unique().tolist())
                sel_types = st.multiselect("Family", types_all, default=types_all, key="ul_types")
                if sel_types:
                    filtered = filtered[filtered["strategy_type"].isin(sel_types)]
        with f3:
            if "quality_flag" in filtered.columns:
                qf_all = sorted(filtered["quality_flag"].dropna().unique().tolist())
                sel_qf = st.multiselect("Quality", qf_all, default=qf_all, key="ul_qf")
                if sel_qf:
                    filtered = filtered[filtered["quality_flag"].isin(sel_qf)]
        with f4:
            pf_col = "leader_pf" if "leader_pf" in filtered.columns else (
                "profit_factor" if "profit_factor" in filtered.columns else None
            )
            if pf_col:
                max_pf = float(pd.to_numeric(filtered[pf_col], errors="coerce").max() or 5.0)
                min_pf_filter = st.slider("Min PF", 0.0, max_pf, 1.0, 0.05, key="ul_pf")
                filtered = filtered[pd.to_numeric(filtered[pf_col], errors="coerce").fillna(0) >= min_pf_filter]
        with f5:
            if "leader_max_drawdown" in filtered.columns:
                dd_vals = pd.to_numeric(filtered["leader_max_drawdown"], errors="coerce").abs()
                max_dd_val = float(dd_vals.max() or 50000)
                max_dd_filter = st.slider("Max DD ($)", 0, int(max_dd_val), int(max_dd_val), 1000, key="ul_dd")
                filtered = filtered[dd_vals.fillna(max_dd_val) <= max_dd_filter]

        st.caption(f"Showing {len(filtered)} of {total_strats} strategies")

        # Main table
        display_cols = [c for c in [
            "rank", "market", "timeframe", "strategy_type", "quality_flag",
            "leader_pf", "leader_max_drawdown", "is_pf", "oos_pf",
            "leader_trades", "leader_exit_type", "leader_net_pnl",
            "recent_12m_pf", "calmar_ratio", "deflated_sharpe_ratio",
            "gate_fragility_status", "run_id",
        ] if c in filtered.columns]

        if display_cols:
            disp = filtered[display_cols].copy()
            rename_map = {
                "leader_pf": "PF", "is_pf": "IS PF", "oos_pf": "OOS PF",
                "leader_max_drawdown": "Max DD", "leader_trades": "Trades",
                "leader_net_pnl": "Net PnL", "leader_exit_type": "Exit",
                "recent_12m_pf": "R12m PF", "calmar_ratio": "Calmar",
                "deflated_sharpe_ratio": "DSR", "gate_fragility_status": "Gate",
                "quality_flag": "Quality", "strategy_type": "Family",
                "timeframe": "TF", "market": "Mkt", "run_id": "Run", "rank": "#",
            }
            disp.columns = [rename_map.get(c, c) for c in disp.columns]
            for nc in ["PF", "IS PF", "OOS PF", "R12m PF", "Calmar", "DSR"]:
                if nc in disp.columns:
                    disp[nc] = pd.to_numeric(disp[nc], errors="coerce").round(2)
            for mc in ["Net PnL", "Max DD"]:
                if mc in disp.columns:
                    disp[mc] = pd.to_numeric(disp[mc], errors="coerce").apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "â€”"
                    )
            st.dataframe(disp, use_container_width=True)
        else:
            render_table(filtered.head(50))

        with st.expander("Strategy details", expanded=False):
            rank_options = filtered["rank"].tolist() if "rank" in filtered.columns else []
            if rank_options:
                sel_rank = st.selectbox("Select rank", rank_options, key="ul_detail_rank")
                row = filtered[filtered["rank"] == sel_rank]
                if not row.empty:
                    r = row.iloc[0]
                    st.markdown(f"**Strategy**: `{r.get('leader_strategy_name', 'â€”')}`")
                    st.markdown(f"**Type / Dataset**: `{r.get('strategy_type', 'â€”')}` / `{r.get('dataset', 'â€”')}`")
                    st.markdown(f"**Quality flag**: `{r.get('quality_flag', 'â€”')}`")
                    st.markdown(f"**Filter combination**: `{r.get('best_combo_filter_class_names', 'â€”')}`")
                    st.markdown(f"**Discovered in run**: `{r.get('run_id', 'â€”')}`")
                    st.markdown(f"**Source file**: `{r.get('source_file', 'â€”')}`")
            else:
                st.info("No strategies match the current filters.")
