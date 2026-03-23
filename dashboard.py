from __future__ import annotations

import socket
import subprocess
from datetime import UTC, datetime
import pandas as pd
import streamlit as st

from dashboard_utils import (
    badge_for_value,
    billing_status_for_launcher,
    build_run_choice_label,
    canonical_runs_root,
    classify_run_status,
    collect_console_run_records,
    detect_result_files,
    estimate_run_cost,
    format_bytes,
    format_currency,
    format_datetime,
    format_duration,
    format_duration_short,
    list_export_files,
    list_uploaded_datasets,
    load_log_tail,
    load_strategy_results,
    operator_action_summary,
    parse_dataset_filename,
    pick_best_candidate_file,
    read_console_run_status,
    read_console_selection,
    resolve_console_storage_paths,
    status_color,
    write_console_selection,
)
from paths import EXPORTS_DIR, LEGACY_RESULTS_DIR, RUNS_DIR, UPLOADS_DIR

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="Strategy Console", layout="wide", page_icon="📈")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}

    /* Banner */
    .console-banner {
        padding: 1.25rem 1.5rem;
        border-radius: 16px;
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        color: #f8fafc;
        margin-bottom: 1.5rem;
        box-shadow: 0 20px 40px rgba(0,0,0,0.3);
    }
    .console-banner h1 { margin: 0; font-size: 2rem; letter-spacing: -0.5px; }
    .console-banner p { margin: 0.4rem 0 0 0; opacity: 0.85; font-size: 1rem; }

    /* Status badges */
    .status-success { color: #00e676; font-weight: bold; }
    .status-warning { color: #ffab00; font-weight: bold; }
    .status-error { color: #ff1744; font-weight: bold; }
    .status-info { color: #448aff; font-weight: bold; }
    .status-neutral { color: #90a4ae; font-weight: bold; }

    /* Quality flag chips */
    .flag-robust { background: #1b5e20; color: #a5d6a7; padding: 2px 8px; border-radius: 8px; font-size: 0.8rem; }
    .flag-stable { background: #0d47a1; color: #90caf9; padding: 2px 8px; border-radius: 8px; font-size: 0.8rem; }
    .flag-marginal { background: #e65100; color: #ffcc80; padding: 2px 8px; border-radius: 8px; font-size: 0.8rem; }
    .flag-broken { background: #b71c1c; color: #ef9a9a; padding: 2px 8px; border-radius: 8px; font-size: 0.8rem; }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #2a2a4a;
        border-radius: 12px;
        padding: 0.75rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }

    /* Sidebar */
    [data-testid="stSidebar"] { background: #0f1923; }

    /* Tabs */
    .stTabs [data-baseweb="tab"] { font-size: 1rem; font-weight: 600; }

    /* Table */
    .dataframe { font-size: 0.82rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Runtime metadata ─────────────────────────────────────────────────────────

@st.cache_resource
def dashboard_runtime_metadata() -> dict[str, str]:
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        commit = "unknown"
    return {
        "commit": commit,
        "hostname": socket.gethostname(),
        "started_at": started_at,
    }


# ─── Data loading ─────────────────────────────────────────────────────────────

runtime = dashboard_runtime_metadata()
storage = resolve_console_storage_paths()
run_records = collect_console_run_records(
    storage=storage,
    repo_results_root=LEGACY_RESULTS_DIR,
    include_legacy_fallback=False,
)
uploaded_datasets = list_uploaded_datasets(storage)
export_files = list_export_files(storage)
console_run_status = read_console_run_status()

run_options = {build_run_choice_label(record): record for record in run_records}


# ─── Sidebar ─────────────────────────────────────────────────────────────────

st.sidebar.markdown("## Strategy Console")
st.sidebar.code(
    f"commit: {runtime['commit']}\n"
    f"host:   {runtime['hostname']}\n"
    f"up:     {runtime['started_at']}",
)
st.sidebar.divider()

selected_run_label = st.sidebar.selectbox(
    "Selected run",
    list(run_options) or ["No runs found"],
    help="Select a completed or active run to inspect.",
)
dataset_options = {entry.name: entry for entry in uploaded_datasets}
selected_dataset_names = st.sidebar.multiselect(
    "Datasets for run",
    list(dataset_options),
    default=[name for name in read_console_selection() if name in dataset_options] or list(dataset_options)[:1],
)
write_console_selection(selected_dataset_names)

selected_run = run_options.get(selected_run_label)

if selected_run:
    selected_status = selected_run["launcher_status"]
    selected_manifest = selected_run["run_manifest"]
    selected_run_dir = selected_run["run_dir"]
    selected_outputs_dir = selected_run["outputs_dir"]
    run_outcome = str(selected_status.get("run_outcome") or "unknown")
    vm_outcome = str(selected_status.get("vm_outcome") or "unknown")
    billing_status = billing_status_for_launcher(selected_status)
    operator_summary = operator_action_summary(selected_status)
    run_category = classify_run_status(selected_status)
else:
    selected_status = {}
    selected_manifest = {}
    selected_run_dir = None
    selected_outputs_dir = None
    run_outcome = "unknown"
    vm_outcome = "unknown"
    billing_status = "unknown"
    operator_summary = "No runs available yet."
    run_category = "unknown"


# ─── Banner ───────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <div class="console-banner">
        <h1>📈 Strategy Console</h1>
        <p>Latest: <strong>{badge_for_value(run_outcome)}</strong> &nbsp;|&nbsp;
           VM: <strong>{badge_for_value(vm_outcome)}</strong> &nbsp;|&nbsp;
           Billing: <strong>{billing_status}</strong> &nbsp;|&nbsp;
           {operator_summary}</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─── Helper renderers ─────────────────────────────────────────────────────────

def render_table(df: pd.DataFrame) -> None:
    try:
        st.dataframe(df, use_container_width=True)
    except Exception:
        st.code(df.to_string(index=False))


def _records_table(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        status = record["launcher_status"]
        cost_info = estimate_run_cost(record)
        cost_str = format_currency(cost_info["estimated_total_cost"]) if cost_info["estimated_total_cost"] is not None else "—"
        cat = classify_run_status(status)
        rows.append({
            "Run ID": status.get("run_id", record["run_dir"].name),
            "Updated (UTC)": status.get("updated_utc", "unknown"),
            "Status": cat.upper(),
            "Run Outcome": badge_for_value(status.get("run_outcome")),
            "VM Outcome": badge_for_value(status.get("vm_outcome")),
            "Est. Cost": cost_str,
        })
    return pd.DataFrame(rows)


def _storage_files_table(entries: list) -> pd.DataFrame:
    rows = []
    for entry in entries:
        info = parse_dataset_filename(entry.name)
        rows.append({
            "Filename": entry.name,
            "Size": format_bytes(entry.size_bytes),
            "Market": info["market"],
            "Timeframe": info["timeframe"],
            "Modified (UTC)": format_datetime(entry.modified_at),
        })
    return pd.DataFrame(rows)


def _leaderboard_table(df: pd.DataFrame) -> pd.DataFrame:
    """Select and rename key columns for display."""
    keep = []
    col_map = {
        "strategy_name": "Strategy", "family": "Family",
        "profit_factor": "PF", "is_profit_factor": "IS PF", "oos_profit_factor": "OOS PF",
        "net_pnl": "Net PnL", "total_trades": "Trades",
        "quality_flag": "Quality", "consistency_flag": "Consistency",
    }
    for src, dst in col_map.items():
        if src in df.columns:
            keep.append((src, dst))
    if not keep:
        return df.head(20)
    out = df[[src for src, _ in keep]].copy()
    out.columns = [dst for _, dst in keep]
    return out.head(20)


# ─── TABS ─────────────────────────────────────────────────────────────────────

tab_control, tab_results, tab_system = st.tabs(["🖥️ Control Panel", "📊 Results Explorer", "⚙️ System"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Control Panel
# ══════════════════════════════════════════════════════════════════════════════

with tab_control:

    # Top status cards
    cost_info = estimate_run_cost(selected_run) if selected_run else {}
    cost_display = format_currency(cost_info.get("estimated_total_cost")) if cost_info.get("estimated_total_cost") is not None else "—"

    # Count accepted strategies from best candidate file
    strat_count = "—"
    if selected_run and selected_outputs_dir:
        try:
            best = pick_best_candidate_file(selected_outputs_dir)
            if best and best.exists():
                strat_count = str(len(pd.read_csv(best)))
        except Exception:
            pass

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest Run", badge_for_value(run_outcome))
    c2.metric("VM Status", badge_for_value(vm_outcome))
    c3.metric("Est. Cost", cost_display)
    c4.metric("Strategies Found", strat_count)

    # Active run section
    if run_category == "running":
        st.divider()
        st.subheader("Active Run")
        dataset_statuses = selected_run.get("dataset_statuses", []) if selected_run else []
        if dataset_statuses:
            for ds in dataset_statuses:
                pct = float(ds.get("progress_pct", 0) or 0)
                st.write(f"**{ds.get('market','?')} {ds.get('timeframe','?')}** — {ds.get('current_family','?')} / {ds.get('current_stage','?')}")
                st.progress(min(pct / 100.0, 1.0))
                eta = ds.get("eta_seconds", 0)
                elapsed = ds.get("elapsed_seconds", 0)
                st.caption(f"Elapsed: {format_duration_short(elapsed)} | ETA: {format_duration_short(eta)}")
        else:
            st.info("Run is active — waiting for first status update.")
        machine = str(selected_manifest.get("machine_type") or selected_status.get("machine_type") or "unknown")
        zone = str(selected_manifest.get("zone") or selected_status.get("zone") or "unknown")
        st.caption(f"Machine: `{machine}` in `{zone}`")

    # Run history
    st.divider()
    st.subheader("Run History")
    if run_records:
        render_table(_records_table(run_records))
    else:
        st.warning(f"No launcher-managed runs found in: `{canonical_runs_root(storage)}`")

    # Selected run detail
    if selected_run:
        with st.expander("Selected Run Detail", expanded=(run_category in {"failed", "preserved"})):
            run_id = selected_status.get("run_id", selected_run_dir.name if selected_run_dir else "?")
            st.markdown(
                f"**Run ID**: `{run_id}`  \n"
                f"**Path**: `{selected_run_dir}`  \n"
                f"**Updated**: `{selected_status.get('updated_utc', 'unknown')}`  \n"
                f"**Destroy Reason**: `{selected_status.get('destroy_reason', 'unknown')}`  \n"
                f"**Operator Action**: `{selected_status.get('operator_action', 'unknown')}`  \n"
                f"**Bundle Size**: `{format_bytes(selected_status.get('bundle_size_bytes'))}`  \n"
                f"**Machine**: `{selected_manifest.get('machine_type') or 'unknown'}` in `{selected_manifest.get('zone') or 'unknown'}`"
            )

            recovery_commands = selected_status.get("recovery_commands") or []
            if recovery_commands:
                st.caption("Recovery commands")
                st.code("\n".join(recovery_commands), language="bash")

            log_tail = load_log_tail(selected_run_dir) if selected_run_dir else ""
            st.caption("Engine log (last 20 lines)")
            if log_tail:
                lines = log_tail.splitlines()
                st.code("\n".join(lines[-20:]), language="text")
            else:
                st.info("No engine log found for this run yet.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Results Explorer
# ══════════════════════════════════════════════════════════════════════════════

with tab_results:

    if not selected_run or not selected_outputs_dir:
        st.info("Select a completed run from the sidebar to view its results.")
    else:
        results = load_strategy_results(selected_outputs_dir)
        run_id = selected_status.get("run_id", selected_run_dir.name if selected_run_dir else "?")
        st.caption(f"Results from: `{run_id}` → `{selected_outputs_dir}`")

        # Leaderboard
        st.subheader("Strategy Leaderboard")
        if results["leaderboard"] is not None:
            lb = results["leaderboard"]
            render_table(_leaderboard_table(lb))
            st.caption(f"{len(lb)} strategies in leaderboard")
        else:
            st.info("No leaderboard file found for this run.")

        # Portfolio review
        if results["portfolio"] is not None:
            st.divider()
            st.subheader("Portfolio Review")
            render_table(results["portfolio"])

        # Correlation matrix heatmap
        if results["correlation"] is not None:
            st.divider()
            st.subheader("Correlation Matrix")
            try:
                import plotly.express as px
                corr_df = results["correlation"].set_index(results["correlation"].columns[0]) if results["correlation"].columns[0] not in ["", "Unnamed: 0"] else results["correlation"].set_index(results["correlation"].columns[0])
                fig = px.imshow(
                    corr_df,
                    color_continuous_scale="RdBu_r",
                    zmin=-1, zmax=1,
                    text_auto=".2f",
                    title="Strategy Return Correlations",
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                render_table(results["correlation"])
                st.caption(f"Could not render heatmap: {e}")

        # Yearly performance
        if results["yearly"] is not None:
            st.divider()
            st.subheader("Yearly Performance")
            yearly_df = results["yearly"]
            try:
                import plotly.express as px
                year_col = next((c for c in yearly_df.columns if "year" in c.lower()), yearly_df.columns[0])
                value_cols = [c for c in yearly_df.columns if c != year_col]
                fig = px.bar(
                    yearly_df.melt(id_vars=year_col, value_vars=value_cols, var_name="Strategy", value_name="PnL"),
                    x=year_col, y="PnL", color="Strategy", barmode="group",
                    title="Annual PnL by Strategy",
                )
                oos_year = 2019
                fig.add_vline(x=str(oos_year), line_dash="dash", line_color="orange",
                              annotation_text="OOS start", annotation_position="top right")
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                render_table(yearly_df)

        # Equity curves
        if results["returns"] is not None:
            st.divider()
            st.subheader("Equity Curves")
            returns_df = results["returns"]
            try:
                import plotly.express as px
                date_col = next((c for c in returns_df.columns if "date" in c.lower() or "time" in c.lower()), None)
                strat_cols = [c for c in returns_df.columns if c != date_col] if date_col else returns_df.columns.tolist()
                if date_col:
                    cumulative = returns_df[[date_col] + strat_cols].copy()
                    for col in strat_cols:
                        cumulative[col] = pd.to_numeric(cumulative[col], errors="coerce").fillna(0).cumsum()
                    fig = px.line(
                        cumulative.melt(id_vars=date_col, value_vars=strat_cols, var_name="Strategy", value_name="Cumulative PnL"),
                        x=date_col, y="Cumulative PnL", color="Strategy",
                        title="Cumulative PnL Over Time",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    render_table(returns_df.head(100))
            except Exception as e:
                render_table(returns_df.head(50))
                st.caption(f"Chart error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — System
# ══════════════════════════════════════════════════════════════════════════════

with tab_system:

    # Storage overview
    st.subheader("Storage Overview")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Uploads", str(len(uploaded_datasets)))
    s2.metric("Runs", str(len(run_records)))
    s3.metric("Exports", str(len(export_files)))
    s4.metric("Storage Root", storage.root.name)

    st.subheader("Uploaded Datasets")
    if uploaded_datasets:
        render_table(_storage_files_table(uploaded_datasets))
    else:
        st.info(f"No datasets in `{storage.uploads}`")

    if export_files:
        st.subheader("Exports")
        render_table(_storage_files_table(export_files))

    # System health
    st.divider()
    st.subheader("System Health")
    health_rows = pd.DataFrame([
        {"Check": "Uploads directory", "Status": "✅ OK" if UPLOADS_DIR.exists() else "❌ Missing"},
        {"Check": "Runs directory", "Status": "✅ OK" if RUNS_DIR.exists() else "❌ Missing"},
        {"Check": "Exports directory", "Status": "✅ OK" if EXPORTS_DIR.exists() else "❌ Missing"},
        {"Check": "Datasets uploaded", "Status": f"✅ {len(uploaded_datasets)}" if uploaded_datasets else "⚠️ None"},
        {"Check": "Latest run state", "Status": console_run_status.get("run_state", "unknown")},
        {"Check": "Dashboard commit", "Status": runtime["commit"]},
        {"Check": "Dashboard host", "Status": runtime["hostname"]},
    ])
    render_table(health_rows)

    # Storage paths
    st.divider()
    st.subheader("Storage Paths")
    st.code(
        f"root:    {storage.root}\n"
        f"uploads: {storage.uploads}\n"
        f"runs:    {canonical_runs_root(storage)}\n"
        f"exports: {storage.exports}\n"
        f"backups: {storage.backups}",
        language="text",
    )

    # Quick actions
    st.divider()
    st.subheader("Quick Actions")
    st.markdown("**Start a full ES 60m sweep** (run on strategy-console):")
    st.code("python3 run_cloud_sweep.py --config cloud/config_es_60m_full_sweep.yaml", language="bash")
    st.markdown("**Quick test run** (fast validation, 8-core):")
    st.code("python3 run_cloud_sweep.py --config cloud/config_quick_test.yaml --dry-run", language="bash")
    st.markdown("**Restart dashboard service**:")
    st.code("sudo systemctl restart strategy-dashboard", language="bash")

    # Available configs
    st.divider()
    st.subheader("Available Sweep Configs")
    try:
        import glob
        configs = sorted(glob.glob("cloud/config_*.yaml"))
        for cfg in configs:
            st.code(cfg)
    except Exception:
        st.info("Could not list configs.")
