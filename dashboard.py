from __future__ import annotations

import html
import socket
import subprocess
from datetime import UTC, datetime
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
    fetch_live_dataset_statuses,
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
)
from paths import EXPORTS_DIR, LEGACY_RESULTS_DIR, RUNS_DIR, UPLOADS_DIR

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Strategy Console", layout="wide", page_icon="📈")

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 3rem;}

.console-banner {
    padding: 1rem 1.5rem;
    border-radius: 12px;
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
    color: #f8fafc;
    margin-bottom: 1.2rem;
}
.console-banner h1 { margin: 0; font-size: 1.7rem; letter-spacing: -0.5px; }
.console-banner p  { margin: 0.3rem 0 0 0; opacity: 0.8; font-size: 0.9rem; }

.status-success { color: #00e676; font-weight: bold; }
.status-warning { color: #ffab00; font-weight: bold; }
.status-error   { color: #ff1744; font-weight: bold; }
.status-info    { color: #448aff; font-weight: bold; }
.status-neutral { color: #90a4ae; font-weight: bold; }

.flag-robust   { background:#1b5e20; color:#a5d6a7; padding:2px 8px; border-radius:8px; font-size:0.78rem; }
.flag-stable   { background:#0d47a1; color:#90caf9; padding:2px 8px; border-radius:8px; font-size:0.78rem; }
.flag-marginal { background:#e65100; color:#ffcc80; padding:2px 8px; border-radius:8px; font-size:0.78rem; }
.flag-broken   { background:#b71c1c; color:#ef9a9a; padding:2px 8px; border-radius:8px; font-size:0.78rem; }

div[data-testid="metric-container"] {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 0.75rem;
}

[data-testid="stSidebar"] { background: #0f1923; }
.stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; }
.dataframe { font-size: 0.82rem; }

.live-scope-card {
    background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
    border: 1px solid #d7e8ff;
    border-radius: 18px;
    padding: 1.35rem 1.5rem;
    margin-bottom: 1.1rem;
    text-align: center;
}
.live-scope-card h2 { margin: 0; font-size: 1.35rem; color: #163b66; letter-spacing: -0.02em; }
.live-scope-card .scope-line { margin-top: 0.55rem; font-size: 1.5rem; font-weight: 700; color: #10253b; }
.monitor-card {
    background: #ffffff;
    border: 1px solid #e6edf5;
    border-radius: 18px;
    padding: 1rem 1.1rem 0.9rem;
    box-shadow: 0 10px 28px rgba(15, 25, 35, 0.05);
    margin-bottom: 1rem;
}
.monitor-card h3 { margin: 0 0 0.3rem 0; color: #10253b; font-size: 1.05rem; }
.monitor-card .subtle { color: #5f7286; font-size: 0.86rem; }
.monitor-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 0.9rem;
    margin-top: 0.9rem;
}
.dataset-card {
    border: 1px solid #ebf0f5;
    border-radius: 16px;
    padding: 0.95rem 1rem;
    background: linear-gradient(180deg, #ffffff 0%, #fafcff 100%);
}
.dataset-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.75rem;
    margin-bottom: 0.6rem;
}
.dataset-title { font-size: 1.02rem; font-weight: 700; color: #10253b; }
.dataset-meta { font-size: 0.78rem; color: #5f7286; }
.family-list { display: flex; flex-direction: column; gap: 0.45rem; }
.family-pill {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-radius: 999px;
    padding: 0.5rem 0.78rem;
    font-size: 0.85rem;
    font-weight: 600;
}
.family-pill.complete { background: #e9f8ef; color: #0d6b35; border: 1px solid #c6ecd4; }
.family-pill.active { background: #e7f1ff; color: #175ea6; border: 1px solid #c9dcff; }
.family-pill.pending { background: #f2f5f8; color: #758597; border: 1px solid #e2e8ef; }
.family-pill.failed { background: #ffe9ee; color: #b4233d; border: 1px solid #ffc9d5; }
.hero-banner {
    background: linear-gradient(135deg, #fef2f2 0%, #ffe5e7 100%);
    color: #991b1b;
    border: 2px solid #ef4444;
    border-radius: 18px;
    padding: 1rem 1.15rem;
    font-size: 1.2rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    text-align: center;
    margin-bottom: 1rem;
}
.focus-card {
    background: linear-gradient(135deg, #10253b 0%, #1d4562 100%);
    color: #f8fbff;
    border-radius: 18px;
    padding: 1rem 1.1rem;
    margin-bottom: 0.95rem;
}
.focus-card .eyebrow { color: rgba(248, 251, 255, 0.75); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; }
.focus-card .value { margin-top: 0.35rem; font-size: 1.25rem; font-weight: 800; }
.focus-card .detail { margin-top: 0.28rem; font-size: 0.88rem; color: rgba(248, 251, 255, 0.82); }
</style>
""", unsafe_allow_html=True)

# ─── Runtime metadata ──────────────────────────────────────────────────────────

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


# ─── Data loading ──────────────────────────────────────────────────────────────

runtime = dashboard_runtime_metadata()
storage = resolve_console_storage_paths()
run_records = collect_console_run_records(
    storage=storage, repo_results_root=LEGACY_RESULTS_DIR, include_legacy_fallback=False,
)
uploaded_datasets = list_uploaded_datasets(storage)
export_files = list_export_files(storage)
console_run_status = read_console_run_status()
monitor_run = choose_default_run_record(run_records, prefer_running=True)
selected_run = choose_default_run_record(run_records, require_outputs=True) or monitor_run

# ─── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.markdown("## Strategy Console")
st.sidebar.code(
    f"commit: {runtime['commit']}\nhost:   {runtime['hostname']}\nup:     {runtime['started_at']}",
)
st.sidebar.divider()
if monitor_run:
    st.sidebar.caption("Live Monitor follows the active run automatically.")
    st.sidebar.markdown(f"**Monitor Run**  \n`{build_run_choice_label(monitor_run)}`")
    st.sidebar.markdown(f"**Scope**  \n{format_run_scope(monitor_run.get('run_manifest', {}))}")
else:
    st.sidebar.caption("No runs found yet.")

if selected_run:
    selected_status      = selected_run["launcher_status"]
    selected_manifest    = selected_run["run_manifest"]
    selected_run_dir     = selected_run["run_dir"]
    selected_outputs_dir = selected_run["outputs_dir"]
    run_outcome      = str(selected_status.get("run_outcome") or "unknown")
    vm_outcome       = str(selected_status.get("vm_outcome") or "unknown")
    billing_status   = billing_status_for_launcher(selected_status)
    operator_summary = operator_action_summary(selected_status)
    run_category     = classify_run_status(selected_status)
else:
    selected_status = {}; selected_manifest = {}
    selected_run_dir = None; selected_outputs_dir = None
    run_outcome = vm_outcome = "unknown"
    billing_status = "unknown"; operator_summary = "No runs available yet."
    run_category = "unknown"

analysis_run = selected_run
analysis_status = selected_status
analysis_manifest = selected_manifest
analysis_run_dir = selected_run_dir
analysis_outputs_dir = selected_outputs_dir
analysis_run_outcome = run_outcome
analysis_vm_outcome = vm_outcome
analysis_billing_status = billing_status
analysis_run_category = run_category

if monitor_run:
    monitor_status = monitor_run["launcher_status"]
    monitor_manifest = monitor_run["run_manifest"]
    monitor_run_dir = monitor_run["run_dir"]
    monitor_outputs_dir = monitor_run["outputs_dir"]
    monitor_run_outcome = str(monitor_status.get("run_outcome") or "unknown")
    monitor_vm_outcome = str(monitor_status.get("vm_outcome") or "unknown")
    monitor_billing_status = billing_status_for_launcher(monitor_status)
    monitor_run_category = classify_run_status(monitor_status)
else:
    monitor_status = {}
    monitor_manifest = {}
    monitor_run_dir = None
    monitor_outputs_dir = None
    monitor_run_outcome = "unknown"
    monitor_vm_outcome = "unknown"
    monitor_billing_status = "unknown"
    monitor_run_category = "unknown"

is_running = (monitor_run_category == "running")
display_run_outcome = "running" if is_running else monitor_run_outcome
display_vm_outcome = monitor_vm_outcome

if monitor_run:
    selected_run = monitor_run
    selected_status = monitor_status
    selected_manifest = monitor_manifest
    selected_run_dir = monitor_run_dir
    selected_outputs_dir = monitor_outputs_dir
    run_outcome = monitor_run_outcome
    vm_outcome = monitor_vm_outcome
    billing_status = monitor_billing_status
    run_category = monitor_run_category

# ─── Banner ────────────────────────────────────────────────────────────────────

run_id_display = selected_status.get("run_id", selected_run_dir.name if selected_run_dir else "—")
st.markdown(f"""
<div class="console-banner">
    <h1>📈 Strategy Console</h1>
    <p>Run: <strong>{run_id_display}</strong> &nbsp;|&nbsp;
       Outcome: <strong>{badge_for_value(display_run_outcome)}</strong> &nbsp;|&nbsp;
       VM: <strong>{badge_for_value(display_vm_outcome)}</strong> &nbsp;|&nbsp;
       Billing: <strong>{billing_status}</strong></p>
</div>
""", unsafe_allow_html=True)

# ─── Helpers ───────────────────────────────────────────────────────────────────

def render_table(df: pd.DataFrame) -> None:
    try:
        st.dataframe(df, use_container_width=True)
    except Exception:
        st.code(df.to_string(index=False))


def render_monitor_progress(summary: dict[str, object]) -> None:
    rows = summary.get("rows", [])
    if not rows:
        st.info("No live dataset progress available yet.")
        return

    completed = int(summary.get("completed_items", 0) or 0)
    total = int(summary.get("total_items", 0) or 0)
    pct = (completed / total * 100.0) if total else 0.0
    st.markdown(
        f"""
        <div class="monitor-card">
            <h3>Run Checklist</h3>
            <div class="subtle">Completed buckets: <strong>{completed}</strong> / <strong>{total}</strong> ({pct:.0f}%)</div>
            <div class="monitor-grid">
        """,
        unsafe_allow_html=True,
    )
    dataset_cards: list[str] = []
    for row in rows:
        items_html: list[str] = []
        for item in row["items"]:
            icon = {
                "complete": "✓",
                "active": "▶",
                "failed": "!",
                "pending": "○",
            }.get(item["status"], "○")
            detail = item["stage"] if item["status"] == "active" and item["stage"] else ""
            items_html.append(
                f'<div class="family-pill {item["status"]}">'
                f"<span>{icon} {html.escape(item['family_label'])}</span>"
                f"<span>{html.escape(detail)}</span>"
                f"</div>"
            )
        dataset_cards.append(
            f"""
            <div class="dataset-card">
                <div class="dataset-head">
                    <div class="dataset-title">{html.escape(row["label"])}</div>
                    <div class="dataset-meta">{row["progress_pct"]:.0f}% complete</div>
                </div>
                <div class="family-list">
                    {''.join(items_html)}
                </div>
            </div>
            """
        )
    st.markdown("".join(dataset_cards) + "</div></div>", unsafe_allow_html=True)


def format_current_leaders(leaders_df: pd.DataFrame | None) -> pd.DataFrame | None:
    if leaders_df is None or leaders_df.empty:
        return None

    display = leaders_df.copy()
    rename_map = {
        "strategy_name": "Strategy",
        "leader_strategy_name": "Strategy",
        "strategy_type": "Family",
        "dataset": "Dataset",
        "market": "Market",
        "timeframe": "Timeframe",
        "profit_factor": "PF",
        "leader_pf": "PF",
        "net_pnl": "Net Profit",
        "leader_net_pnl": "Net Profit",
        "max_drawdown": "Drawdown",
        "leader_max_drawdown": "Drawdown",
        "total_trades": "Trades",
        "leader_trades": "Trades",
        "quality_flag": "Quality",
    }
    existing = [column for column in rename_map if column in display.columns]
    if not existing:
        return display

    display = display[existing].copy()
    display.columns = [rename_map[column] for column in existing]
    display = display.loc[:, ~display.columns.duplicated()]

    for numeric_column in ("PF", "Trades"):
        if numeric_column in display.columns:
            display[numeric_column] = pd.to_numeric(display[numeric_column], errors="coerce").round(2)
    for money_column in ("Net Profit", "Drawdown"):
        if money_column in display.columns:
            display[money_column] = pd.to_numeric(display[money_column], errors="coerce").apply(
                lambda value: f"${value:,.0f}" if pd.notna(value) else "—"
            )
    return display

# ─── TABS ──────────────────────────────────────────────────────────────────────

tab_monitor, tab_results, tab_ultimate, tab_history, tab_system = st.tabs(
    ["🔴 Live Monitor", "📊 Results", "🏆 Ultimate Leaderboard", "🗂️ Run History", "⚙️ System"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MONITOR
# ══════════════════════════════════════════════════════════════════════════════

with tab_monitor:

    if is_running:
        st.markdown('<meta http-equiv="refresh" content="30">', unsafe_allow_html=True)

    # ── Top KPI row ──────────────────────────────────────────────────────────

    cost_info    = estimate_run_cost(monitor_run) if monitor_run else {}
    elapsed_sec  = float(cost_info.get("elapsed_seconds") or 0)
    hourly_rate  = cost_info.get("hourly_rate")
    total_cost   = cost_info.get("estimated_total_cost")
    machine_type = cost_info.get("machine_type", "unknown")

    if is_running and monitor_status.get("created_utc"):
        try:
            from datetime import timezone
            created = datetime.fromisoformat(str(monitor_status["created_utc"]).replace("Z", "+00:00"))
            elapsed_sec = (datetime.now(timezone.utc) - created).total_seconds()
            if hourly_rate:
                total_cost = hourly_rate * (elapsed_sec / 3600)
        except Exception:
            pass

    cost_str    = f"${total_cost:.2f}" if total_cost is not None else "—"
    elapsed_str = format_duration_short(elapsed_sec)
    rate_str    = f"${hourly_rate:.2f}/hr" if hourly_rate else "—"

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        status_emoji = "🟢" if is_running else ("✅" if run_category == "completed" else "⚪")
        st.metric("Status", f"{status_emoji} {run_category.upper()}")
    with k2:
        st.metric("Elapsed Time", elapsed_str)
    with k3:
        st.metric("Est. SPOT Cost", cost_str,
                  delta=rate_str if is_running else None, delta_color="inverse")
    with k4:
        machine_label = (machine_type.replace("n2-highcpu-", "") + " vCPU"
                         if "highcpu" in machine_type else machine_type)
        st.metric("VM", machine_label)

    st.divider()

    # ── Dataset progress ─────────────────────────────────────────────────────

    dataset_statuses = fetch_live_dataset_statuses(selected_run_dir) if selected_run_dir else []
    monitor_summary = build_monitor_progress_rows(dataset_statuses, selected_manifest)
    log_tail = load_log_tail(selected_run_dir) if selected_run_dir else ""
    preemption_warning = detect_preemption_warning(selected_status, log_tail)
    run_scope = format_run_scope(selected_manifest)
    focus = monitor_summary.get("active_focus") or monitor_summary.get("recent_focus") or {}

    if preemption_warning:
        st.markdown(f'<div class="hero-banner">{html.escape(preemption_warning)}</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="live-scope-card">
            <h2>Market and time frames in current live run</h2>
            <div class="scope-line">{html.escape(run_scope)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    overview_col, leader_col = st.columns([1.7, 1.0], gap="large")
    with overview_col:
        render_monitor_progress(monitor_summary)
    with leader_col:
        focus_value = focus.get("label") or "Awaiting first active bucket"
        focus_detail = focus.get("stage") or ("Most recently completed bucket" if monitor_summary.get("recent_focus") else "Progress signal not available yet")
        st.markdown(
            f"""
            <div class="focus-card">
                <div class="eyebrow">Current Focus</div>
                <div class="value">{html.escape(str(focus_value))}</div>
                <div class="detail">{html.escape(str(focus_detail))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        current_leaders = format_current_leaders(load_current_leader_snapshot(selected_outputs_dir, monitor_summary))
        st.markdown('<div class="monitor-card"><h3>Current Leaders</h3><div class="subtle">Best available leaders for the active or most recently completed bucket.</div></div>', unsafe_allow_html=True)
        if current_leaders is not None and not current_leaders.empty:
            st.dataframe(current_leaders, use_container_width=True, height=min(340, 36 + len(current_leaders) * 35))
        else:
            st.info("No promoted candidates have been written for this focus yet.")

    if selected_run and selected_run_dir:
        dataset_statuses = fetch_live_dataset_statuses(selected_run_dir)
    else:
        dataset_statuses = []

    if dataset_statuses:
        # Build title from manifest datasets if available
        manifest_datasets = selected_manifest.get("datasets", []) if selected_manifest else []
        ds_label = (
            ", ".join(
                f"{d.get('market','?')} {d.get('timeframe','?')}"
                for d in manifest_datasets
                if isinstance(d, dict)
            )
            if manifest_datasets else ""
        )
        progress_title = f"Dataset Progress — {ds_label}" if ds_label else "Dataset Progress"
        st.subheader(progress_title)
        fam_emoji = {"trend": "📈", "mean_reversion": "↩️", "breakout": "💥"}
        parent_families = ["mean_reversion", "trend", "breakout"]

        def _group_families(family_list: list[str]) -> dict[str, list[str]]:
            groups: dict[str, list[str]] = {p: [] for p in parent_families}
            for f in family_list:
                matched = False
                for p in parent_families:
                    if f == p or f.startswith(p + "_"):
                        groups[p].append(f)
                        matched = True
                        break
                if not matched:
                    groups.setdefault(f, []).append(f)
            return groups

        done_families = sum(len(ds.get("families_completed", [])) for ds in dataset_statuses)
        remaining_families = sum(len(ds.get("families_remaining", [])) for ds in dataset_statuses)
        total_families = done_families + remaining_families or len(dataset_statuses) * 3
        overall_pct    = (done_families / total_families * 100) if total_families else 0

        st.markdown(f"**Overall: {done_families} / {total_families} families complete ({overall_pct:.0f}%)**")
        st.progress(min(overall_pct / 100.0, 1.0))
        st.markdown("")

        for ds in dataset_statuses:
            pct       = float(ds.get("progress_pct", 0) or 0)
            market    = ds.get("market", ds.get("dataset", "?"))
            timeframe = ds.get("timeframe", "?")
            cur_fam   = ds.get("current_family", "?")
            cur_stage = ds.get("current_stage", "?")
            completed = ds.get("families_completed", [])
            remaining = ds.get("families_remaining", [])
            eta_sec   = float(ds.get("eta_seconds", 0) or 0)
            el_sec    = float(ds.get("elapsed_seconds", 0) or 0)
            is_waiting = cur_stage == "WAITING"
            is_done   = not is_waiting and (pct >= 100 or cur_stage == "DONE")
            is_active = not is_done and not is_waiting and pct > 0

            completed_groups = _group_families(completed)
            all_fams_for_ds  = _group_families(completed + remaining)

            col_a, col_b = st.columns([3, 1])
            with col_a:
                icon = "✅" if is_done else ("🔵" if is_active else ("⏳" if is_waiting else "⏳"))
                st.markdown(f"**{icon} {market} {timeframe}**")
                st.progress(min(pct / 100.0, 1.0))
                pill_html = ""
                for p in parent_families:
                    e = fam_emoji.get(p, "•")
                    done_in_group  = len(completed_groups.get(p, []))
                    total_in_group = max(len(all_fams_for_ds.get(p, [])), 1)
                    is_cur = cur_fam == p or (cur_fam or "").startswith(p + "_")
                    is_fam_done = done_in_group >= total_in_group
                    label = f"{done_in_group}/{total_in_group}" if total_in_group > 1 else ("✓" if is_fam_done else "")
                    if is_fam_done:
                        pill_html += (f'<span style="background:#1b5e20;color:#a5d6a7;'
                                      f'padding:2px 10px;border-radius:20px;font-size:0.78rem;margin-right:6px">'
                                      f'{e} {p} {label}</span>')
                    elif is_cur and not is_done:
                        pill_html += (f'<span style="background:#0d47a1;color:#90caf9;'
                                      f'padding:2px 10px;border-radius:20px;font-size:0.78rem;margin-right:6px">'
                                      f'⚙️ {p} {label} ({cur_stage})</span>')
                    else:
                        pill_html += (f'<span style="background:#1a2634;color:#546e7a;'
                                      f'padding:2px 10px;border-radius:20px;font-size:0.78rem;margin-right:6px">'
                                      f'{e} {p} {label}</span>')
                st.markdown(pill_html, unsafe_allow_html=True)
            with col_b:
                if is_done:
                    st.markdown("**Done ✅**")
                elif is_waiting:
                    st.markdown("*Waiting...*")
                elif is_active:
                    st.markdown(f"**ETA** {format_duration_short(eta_sec)}")
                    st.caption(f"Elapsed {format_duration_short(el_sec)}")
                else:
                    st.markdown("*Queued*")
            st.markdown("")

    elif is_running:
        st.info("Run is active — waiting for first status update.")
    else:
        st.info("No active run. Start a new sweep to populate the live monitor.")

    # ── Promoted candidates feed ──────────────────────────────────────────────

    st.divider()
    st.subheader("Promoted Candidates")
    st.caption("Strategies that passed the promotion gate — populated as each family completes.")

    if selected_outputs_dir:
        candidates_df = load_promoted_candidates(selected_outputs_dir)
        if candidates_df is not None and not candidates_df.empty:
            col_map = {
                "strategy_name":   "Strategy",
                "strategy_type":   "Family",
                "profit_factor":   "PF",
                "is_pf":           "IS PF",
                "oos_pf":          "OOS PF",
                "net_pnl":         "Net PnL ($)",
                "total_trades":    "Trades",
                "trades_per_year": "Trades/yr",
                "quality_flag":    "Quality",
                "dataset":         "Dataset",
            }
            existing = {k: v for k, v in col_map.items() if k in candidates_df.columns}
            if existing:
                disp = candidates_df[list(existing.keys())].copy()
                disp.columns = list(existing.values())
                for col in ["PF", "IS PF", "OOS PF", "Trades/yr"]:
                    if col in disp.columns:
                        disp[col] = pd.to_numeric(disp[col], errors="coerce").round(2)
                if "Net PnL ($)" in disp.columns:
                    disp["Net PnL ($)"] = pd.to_numeric(disp["Net PnL ($)"], errors="coerce").apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
                    )
                st.dataframe(disp, use_container_width=True, height=min(400, 36 + len(disp) * 35))
                st.caption(f"{len(candidates_df)} candidates promoted across all completed families")
            else:
                render_table(candidates_df.head(20))
        elif is_running:
            st.info("No candidates yet — families still running.")
        else:
            st.info("No promoted candidates file found for this run.")
    else:
        st.info("Promoted candidates will appear here once the live run has written result files.")

    with st.expander("Engine log (last 30 lines)", expanded=False):
        log_tail = load_log_tail(selected_run_dir) if selected_run_dir else ""
        if log_tail:
            st.code("\n".join(log_tail.splitlines()[-30:]), language="text")
        else:
            st.info("No engine log found yet.")
    st.divider()
    st.subheader("Run Trail")
    st.caption("Recent engine progress lines, warnings, and errors.")
    if log_tail:
        st.code(log_tail, language="text")
    elif is_running:
        st.info("Run is active, but the first log lines have not been captured yet.")
    else:
        st.info("No live run trail is available for this run.")

    if is_running:
        st.caption("🔄 Auto-refreshes every 30 seconds while run is active.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RESULTS
# ══════════════════════════════════════════════════════════════════════════════

with tab_results:

    if not analysis_run or not analysis_outputs_dir:
        st.info("No completed run with local outputs is available yet.")
    else:
        results = load_strategy_results(analysis_outputs_dir)
        run_id  = analysis_status.get("run_id", analysis_run_dir.name if analysis_run_dir else "?")
        st.caption(f"Results from: `{run_id}` → `{analysis_outputs_dir}`")

        st.subheader("Strategy Leaderboard")
        if results["leaderboard"] is not None:
            lb = results["leaderboard"]
            col_map = {
                "strategy_name": "Strategy", "leader_strategy_name": "Strategy",
                "strategy_type": "Family",
                "quality_flag": "Quality", "accepted_final": "Accepted",
                "profit_factor": "PF", "leader_pf": "PF",
                "is_pf": "IS PF", "oos_pf": "OOS PF",
                "recent_12m_pf": "R12m PF",
                "net_pnl": "Net PnL", "leader_net_pnl": "Net PnL",
                "total_trades": "Trades", "leader_trades": "Trades",
                "bootcamp_score": "Bootcamp",
                "leader_trades_per_year": "Trades/Yr",
                "calmar_ratio": "Calmar",
                "is_oos_pf_ratio": "IS/OOS",
                "leader_win_rate": "Win%",
                "leader_max_drawdown": "Max DD",
                "leader_pct_profitable_years": "Prof Yrs%",
                "timeframe": "TF",
                "market": "Market",
                "dataset": "Dataset",
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
                # Format monetary columns
                for money_col in ["Net PnL", "Max DD"]:
                    if money_col in disp.columns:
                        disp[money_col] = pd.to_numeric(disp[money_col], errors="coerce").apply(
                            lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
                        )
                # Format ratio/percentage columns
                for ratio_col in ["PF", "IS PF", "OOS PF", "R12m PF", "Calmar", "IS/OOS", "Win%", "Prof Yrs%", "Trades/Yr"]:
                    if ratio_col in disp.columns:
                        disp[ratio_col] = pd.to_numeric(disp[ratio_col], errors="coerce").round(2)
                # Quality flag column config
                col_config: dict = {}
                if "Quality" in disp.columns:
                    col_config["Quality"] = st.column_config.TextColumn(
                        "Quality",
                        help="ROBUST=strong both periods, STABLE=acceptable, MARGINAL=weak, BROKEN=overfit",
                    )
                st.dataframe(disp, column_config=col_config, use_container_width=True)
            else:
                disp = lb.head(20)
                render_table(disp)
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
                date_col  = next((c for c in returns_df.columns if "date" in c.lower() or "time" in c.lower()), None)
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
                                 color_discrete_map={"Profit": "#00e676", "Loss": "#ff1744"},
                                 template="plotly_dark", title="Annual PnL",
                                 labels={pnl_col: "PnL ($)", year_col: "Year"})
                    fig.add_vline(x=2018.5, line_dash="dash", line_color="orange",
                                  annotation_text="OOS →", annotation_position="top left")
                    fig.update_layout(height=350, showlegend=False, margin=dict(l=40, r=20, t=60, b=40))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    render_table(yearly_df)
            except Exception:
                render_table(yearly_df)

        # Cross-timeframe correlation matrix (all accepted strategies across all datasets)
        if results.get("cross_correlation") is not None:
            st.divider()
            st.subheader("Cross-Timeframe Strategy Correlations")
            st.caption("All accepted strategies across all timeframes — correlation of daily PnL")
            try:
                import plotly.express as px
                ctf_df = results["cross_correlation"].copy()
                idx_col = ctf_df.columns[0]
                ctf_df = ctf_df.set_index(idx_col)

                def _shorten_label(s: str) -> str:
                    s = str(s)
                    if "_Refined" in s:
                        parts = s.split("_Refined", 1)
                        return parts[0].split("_")[-1] + "_R" + parts[1][:8]
                    if "_ES_" in s:
                        return s.split("_ES_")[-1][-25:]
                    return s[-25:]

                ctf_df.index   = [_shorten_label(i) for i in ctf_df.index]
                ctf_df.columns = [_shorten_label(c) for c in ctf_df.columns]
                n = len(ctf_df)
                fig_height = max(350, n * 40 + 80)
                fig = px.imshow(ctf_df, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                                text_auto=".2f", template="plotly_dark",
                                title=f"Cross-Timeframe Correlation ({n}×{n})")
                fig.update_layout(height=fig_height, margin=dict(l=40, r=20, t=60, b=40))
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


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ULTIMATE LEADERBOARD
# ══════════════════════════════════════════════════════════════════════════════

with tab_ultimate:

    @st.cache_data(ttl=120)
    def _load_ultimate_leaderboard(bootcamp: bool = False) -> pd.DataFrame:
        filename = "ultimate_leaderboard_bootcamp.csv" if bootcamp else "ultimate_leaderboard.csv"
        try:
            from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard
            df = aggregate_ultimate_leaderboard()
            if bootcamp and "bootcamp_score" in df.columns:
                df = df.sort_values("bootcamp_score", ascending=False).reset_index(drop=True)
                if "rank" in df.columns:
                    df["rank"] = range(1, len(df) + 1)
            return df
        except Exception as exc:
            return pd.DataFrame({"error": [str(exc)]})

    col_refresh, col_spacer, col_view = st.columns([1, 3, 2])
    with col_refresh:
        if st.button("🔄 Refresh", key="ul_refresh"):
            _load_ultimate_leaderboard.clear()
    with col_view:
        view_mode = st.radio(
            "Ranking",
            ["Classic (PF)", "Bootcamp Score"],
            horizontal=True,
            key="ul_view_mode",
        )

    use_bootcamp = view_mode == "Bootcamp Score"
    ul_df = _load_ultimate_leaderboard(bootcamp=use_bootcamp)

    if ul_df.empty or "error" in ul_df.columns:
        if "error" in ul_df.columns:
            st.error(f"Error loading ultimate leaderboard: {ul_df['error'].iloc[0]}")
        else:
            st.info("No accepted strategies found across any runs. Run a sweep first.")
    else:
        # ── KPI strip ────────────────────────────────────────────────────────
        total_strats  = len(ul_df)
        robust_count  = int((ul_df.get("quality_flag", pd.Series()) == "ROBUST").sum()) if "quality_flag" in ul_df.columns else 0
        stable_count  = int(ul_df["quality_flag"].str.startswith("STABLE").sum()) if "quality_flag" in ul_df.columns else 0
        unique_tfs    = ul_df["timeframe"].nunique() if "timeframe" in ul_df.columns else (
            ul_df["dataset"].nunique() if "dataset" in ul_df.columns else 0
        )
        unique_markets = ul_df["market"].nunique() if "market" in ul_df.columns else "—"
        runs_scanned  = ul_df["run_id"].nunique() if "run_id" in ul_df.columns else 0

        u1, u2, u3, u4, u5 = st.columns(5)
        u1.metric("Total Strategies", total_strats)
        u2.metric("ROBUST", robust_count)
        u3.metric("STABLE", stable_count)
        u4.metric("Timeframes", unique_tfs)
        u5.metric("Markets", unique_markets)

        st.divider()

        # ── Filters ──────────────────────────────────────────────────────────
        filtered = ul_df.copy()

        f1, f2, f3, f4, f5 = st.columns(5)
        with f1:
            if "market" in filtered.columns:
                mkt_all = sorted(filtered["market"].dropna().unique().tolist())
                sel_mkt = st.multiselect("Market", mkt_all, default=mkt_all, key="ul_mkt")
                if sel_mkt:
                    filtered = filtered[filtered["market"].isin(sel_mkt)]
            elif "dataset" in filtered.columns:
                ds_all = sorted(filtered["dataset"].dropna().unique().tolist())
                sel_ds = st.multiselect("Dataset", ds_all, default=ds_all, key="ul_ds")
                if sel_ds:
                    filtered = filtered[filtered["dataset"].isin(sel_ds)]
        with f2:
            if "strategy_type" in filtered.columns:
                types_all = sorted(filtered["strategy_type"].dropna().unique().tolist())
                sel_types = st.multiselect("Strategy type", types_all, default=types_all, key="ul_types")
                if sel_types:
                    filtered = filtered[filtered["strategy_type"].isin(sel_types)]
        with f3:
            if "quality_flag" in filtered.columns:
                qf_all = sorted(filtered["quality_flag"].dropna().unique().tolist())
                sel_qf = st.multiselect("Quality flag", qf_all, default=qf_all, key="ul_qf")
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

        # ── Main table ───────────────────────────────────────────────────────
        display_cols = [c for c in [
            "rank", "market", "timeframe", "strategy_type", "quality_flag",
            "leader_pf", "leader_max_drawdown", "is_pf", "oos_pf",
            "leader_trades", "leader_exit_type",
            "leader_net_pnl", "bootcamp_score",
            "recent_12m_pf", "run_id",
        ] if c in filtered.columns]

        if display_cols:
            disp = filtered[display_cols].copy()
            rename_map = {
                "leader_pf": "PF", "is_pf": "IS PF", "oos_pf": "OOS PF",
                "leader_max_drawdown": "Max DD", "leader_trades": "Trades",
                "leader_net_pnl": "Net PnL", "leader_exit_type": "Exit",
                "bootcamp_score": "BCS", "recent_12m_pf": "R12m PF",
                "quality_flag": "Quality", "strategy_type": "Family",
                "timeframe": "TF", "market": "Mkt", "run_id": "Run",
                "rank": "#",
            }
            disp.columns = [rename_map.get(c, c) for c in disp.columns]
            for num_col in ["PF", "IS PF", "OOS PF", "R12m PF", "BCS"]:
                if num_col in disp.columns:
                    disp[num_col] = pd.to_numeric(disp[num_col], errors="coerce").round(2)
            for money_col in ["Net PnL", "Max DD"]:
                if money_col in disp.columns:
                    disp[money_col] = pd.to_numeric(disp[money_col], errors="coerce").apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "—"
                    )
            st.dataframe(disp, use_container_width=True)
        else:
            render_table(filtered.head(50))

        # ── Details expander ─────────────────────────────────────────────────
        with st.expander("Strategy details", expanded=False):
            rank_options = filtered["rank"].tolist() if "rank" in filtered.columns else []
            if rank_options:
                sel_rank = st.selectbox("Select rank", rank_options, key="ul_detail_rank")
                row = filtered[filtered["rank"] == sel_rank]
                if not row.empty:
                    r = row.iloc[0]
                    st.markdown(f"**Strategy**: `{r.get('leader_strategy_name', '—')}`")
                    st.markdown(f"**Type / Dataset**: `{r.get('strategy_type', '—')}` / `{r.get('dataset', '—')}`")
                    st.markdown(f"**Quality flag**: `{r.get('quality_flag', '—')}`")
                    st.markdown(f"**Filter combination**: `{r.get('best_combo_filter_class_names', '—')}`")
                    st.markdown(f"**Discovered in run**: `{r.get('run_id', '—')}`")
                    st.markdown(f"**Source file**: `{r.get('source_file', '—')}`")
                    st.markdown(f"**Discovered at**: `{r.get('discovered_at', '—')}`")
            else:
                st.info("No strategies match the current filters.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RUN HISTORY
# ══════════════════════════════════════════════════════════════════════════════

with tab_history:

    st.subheader("All Runs")
    if run_records:
        rows = []
        for record in run_records:
            status   = record["launcher_status"]
            manifest = record["run_manifest"]
            cost_i   = estimate_run_cost(record)
            cost_s   = (format_currency(cost_i["estimated_total_cost"])
                        if cost_i["estimated_total_cost"] is not None else "—")
            cat      = classify_run_status(status)
            datasets = manifest.get("datasets", [])
            ds_str   = (", ".join(f"{d.get('market','?')} {d.get('timeframe','?')}" for d in datasets)
                        if datasets else "—")
            rows.append({
                "Run ID":    status.get("run_id", record["run_dir"].name),
                "Updated":   status.get("updated_utc", "unknown"),
                "Status":    cat.upper(),
                "Outcome":   badge_for_value(status.get("run_outcome")),
                "VM":        badge_for_value(status.get("vm_outcome")),
                "Datasets":  ds_str,
                "Machine":   manifest.get("machine_type", "—"),
                "Est. Cost": cost_s,
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
                f"**Machine**: `{analysis_manifest.get('machine_type','?')}` in `{analysis_manifest.get('zone','?')}`  \n"
                f"**Destroy reason**: `{analysis_status.get('destroy_reason','unknown')}`  \n"
                f"**Bundle size**: `{format_bytes(analysis_status.get('bundle_size_bytes'))}`"
            )
            recovery = analysis_status.get("recovery_commands") or []
            if recovery:
                st.caption("Recovery commands")
                st.code("\n".join(recovery), language="bash")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

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
        {"Check": "Uploads directory", "Status": "✅ OK" if UPLOADS_DIR.exists() else "❌ Missing"},
        {"Check": "Runs directory",    "Status": "✅ OK" if RUNS_DIR.exists() else "❌ Missing"},
        {"Check": "Exports directory", "Status": "✅ OK" if EXPORTS_DIR.exists() else "❌ Missing"},
        {"Check": "Datasets uploaded", "Status": f"✅ {len(uploaded_datasets)}" if uploaded_datasets else "⚠️ None"},
        {"Check": "Latest run state",  "Status": console_run_status.get("run_state", "unknown")},
        {"Check": "Dashboard commit",  "Status": runtime["commit"]},
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
    st.markdown("**Launch ES all-timeframes sweep (daily, 60m, 30m, 15m):**")
    st.code("python3 run_cloud_sweep.py --config cloud/config_es_all_timeframes_96core.yaml", language="bash")
    st.markdown("**Quick test run (MR only, 8-core, dry run):**")
    st.code("python3 run_cloud_sweep.py --config cloud/config_quick_test.yaml --dry-run", language="bash")
    st.markdown("**Restart dashboard:**")
    st.code("sudo systemctl restart strategy-dashboard", language="bash")
    st.markdown("**Check run status remotely:**")
    st.code(
        "cat ~/strategy_console_storage/runs/"
        "$(cat ~/strategy_console_storage/runs/LATEST_RUN.txt)"
        "/artifacts/Outputs/ES_60m/status.json | python3 -m json.tool",
        language="bash",
    )
    st.markdown("**Recover artifacts for a completed run that never downloaded locally:**")
    st.code("python3 run_cloud_sweep.py --recover-run $(cat ~/strategy_console_storage/runs/LATEST_RUN.txt)", language="bash")
    st.markdown("**Most convenient leaderboard path after recovery/success:**")
    st.code("cat ~/strategy_console_storage/exports/master_leaderboard.csv", language="bash")
