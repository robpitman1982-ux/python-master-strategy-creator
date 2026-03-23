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
    fetch_live_dataset_statuses,
    format_bytes,
    format_currency,
    format_datetime,
    format_duration,
    format_duration_short,
    list_export_files,
    list_uploaded_datasets,
    load_log_tail,
    load_promoted_candidates,
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
run_options = {build_run_choice_label(record): record for record in run_records}

# ─── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.markdown("## Strategy Console")
st.sidebar.code(
    f"commit: {runtime['commit']}\nhost:   {runtime['hostname']}\nup:     {runtime['started_at']}",
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
    default=[n for n in read_console_selection() if n in dataset_options] or list(dataset_options)[:1],
)
write_console_selection(selected_dataset_names)

selected_run = run_options.get(selected_run_label)

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

is_running = (run_category == "running")

# ─── Banner ────────────────────────────────────────────────────────────────────

run_id_display = selected_status.get("run_id", selected_run_dir.name if selected_run_dir else "—")
st.markdown(f"""
<div class="console-banner">
    <h1>📈 Strategy Console</h1>
    <p>Run: <strong>{run_id_display}</strong> &nbsp;|&nbsp;
       Outcome: <strong>{badge_for_value(run_outcome)}</strong> &nbsp;|&nbsp;
       VM: <strong>{badge_for_value(vm_outcome)}</strong> &nbsp;|&nbsp;
       Billing: <strong>{billing_status}</strong></p>
</div>
""", unsafe_allow_html=True)

# ─── Helpers ───────────────────────────────────────────────────────────────────

def render_table(df: pd.DataFrame) -> None:
    try:
        st.dataframe(df, use_container_width=True)
    except Exception:
        st.code(df.to_string(index=False))

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

    cost_info    = estimate_run_cost(selected_run) if selected_run else {}
    elapsed_sec  = float(cost_info.get("elapsed_seconds") or 0)
    hourly_rate  = cost_info.get("hourly_rate")
    total_cost   = cost_info.get("estimated_total_cost")
    machine_type = cost_info.get("machine_type", "unknown")

    if is_running and selected_status.get("created_utc"):
        try:
            from datetime import timezone
            created = datetime.fromisoformat(str(selected_status["created_utc"]).replace("Z", "+00:00"))
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

    if selected_run and selected_run_dir:
        dataset_statuses = fetch_live_dataset_statuses(selected_run_dir)
    else:
        dataset_statuses = []

    if dataset_statuses:
        st.subheader("Dataset Progress")
        all_families = ["trend", "mean_reversion", "breakout"]
        fam_emoji    = {"trend": "📈", "mean_reversion": "↩️", "breakout": "💥"}

        total_families = len(dataset_statuses) * len(all_families)
        done_families  = sum(len(ds.get("families_completed", [])) for ds in dataset_statuses)
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
            eta_sec   = float(ds.get("eta_seconds", 0) or 0)
            el_sec    = float(ds.get("elapsed_seconds", 0) or 0)
            is_done   = pct >= 100 or cur_stage == "DONE"
            is_active = not is_done and pct > 0

            col_a, col_b = st.columns([3, 1])
            with col_a:
                icon = "✅" if is_done else ("🔵" if is_active else "⏳")
                st.markdown(f"**{icon} {market} {timeframe}**")
                st.progress(min(pct / 100.0, 1.0))
                pill_html = ""
                for fam in all_families:
                    e = fam_emoji.get(fam, "•")
                    if fam in completed:
                        pill_html += (f'<span style="background:#1b5e20;color:#a5d6a7;'
                                      f'padding:2px 10px;border-radius:20px;font-size:0.78rem;margin-right:6px">'
                                      f'{e} {fam} ✓</span>')
                    elif fam == cur_fam and not is_done:
                        pill_html += (f'<span style="background:#0d47a1;color:#90caf9;'
                                      f'padding:2px 10px;border-radius:20px;font-size:0.78rem;margin-right:6px">'
                                      f'⚙️ {fam} ({cur_stage})</span>')
                    else:
                        pill_html += (f'<span style="background:#1a2634;color:#546e7a;'
                                      f'padding:2px 10px;border-radius:20px;font-size:0.78rem;margin-right:6px">'
                                      f'{e} {fam}</span>')
                st.markdown(pill_html, unsafe_allow_html=True)
            with col_b:
                if is_done:
                    st.markdown("**Done ✅**")
                elif is_active:
                    st.markdown(f"**ETA** {format_duration_short(eta_sec)}")
                    st.caption(f"Elapsed {format_duration_short(el_sec)}")
                else:
                    st.markdown("*Queued*")
            st.markdown("")

    elif is_running:
        st.info("Run is active — waiting for first status update.")
    else:
        st.info("No active run. Select a run from the sidebar or start a new sweep.")

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
        st.info("Select a run with results to see promoted candidates.")

    with st.expander("Engine log (last 30 lines)", expanded=False):
        log_tail = load_log_tail(selected_run_dir) if selected_run_dir else ""
        if log_tail:
            st.code("\n".join(log_tail.splitlines()[-30:]), language="text")
        else:
            st.info("No engine log found yet.")

    if is_running:
        st.caption("🔄 Auto-refreshes every 30 seconds while run is active.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RESULTS
# ══════════════════════════════════════════════════════════════════════════════

with tab_results:

    if not selected_run or not selected_outputs_dir:
        st.info("Select a completed run from the sidebar to view results.")
    else:
        results = load_strategy_results(selected_outputs_dir)
        run_id  = selected_status.get("run_id", selected_run_dir.name if selected_run_dir else "?")
        st.caption(f"Results from: `{run_id}` → `{selected_outputs_dir}`")

        st.subheader("Strategy Leaderboard")
        if results["leaderboard"] is not None:
            lb = results["leaderboard"]
            col_map = {
                "strategy_name": "Strategy", "leader_strategy_name": "Strategy",
                "strategy_type": "Family",
                "profit_factor": "PF", "leader_pf": "PF",
                "is_pf": "IS PF", "oos_pf": "OOS PF",
                "net_pnl": "Net PnL", "leader_net_pnl": "Net PnL",
                "total_trades": "Trades", "leader_trades": "Trades",
                "quality_flag": "Quality", "accepted_final": "Accepted",
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

        if results["correlation"] is not None:
            st.divider()
            st.subheader("Strategy Correlation")
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
    def _load_ultimate_leaderboard() -> pd.DataFrame:
        try:
            from modules.ultimate_leaderboard import aggregate_ultimate_leaderboard
            return aggregate_ultimate_leaderboard()
        except Exception as exc:
            return pd.DataFrame({"error": [str(exc)]})

    col_refresh, col_spacer = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh", key="ul_refresh"):
            _load_ultimate_leaderboard.clear()

    ul_df = _load_ultimate_leaderboard()

    if ul_df.empty or "error" in ul_df.columns:
        if "error" in ul_df.columns:
            st.error(f"Error loading ultimate leaderboard: {ul_df['error'].iloc[0]}")
        else:
            st.info("No accepted strategies found across any runs. Run a sweep first.")
    else:
        # ── KPI strip ────────────────────────────────────────────────────────
        total_strats  = len(ul_df)
        robust_count  = int((ul_df.get("quality_flag", pd.Series()) == "ROBUST").sum()) if "quality_flag" in ul_df.columns else 0
        unique_datasets = ul_df["dataset"].nunique() if "dataset" in ul_df.columns else 0
        runs_scanned  = ul_df["run_id"].nunique() if "run_id" in ul_df.columns else 0

        u1, u2, u3, u4 = st.columns(4)
        u1.metric("Total Strategies", total_strats)
        u2.metric("ROBUST", robust_count)
        u3.metric("Unique Datasets", unique_datasets)
        u4.metric("Runs Scanned", runs_scanned)

        st.divider()

        # ── Filters ──────────────────────────────────────────────────────────
        filtered = ul_df.copy()

        f1, f2, f3, f4 = st.columns(4)
        with f1:
            if "strategy_type" in filtered.columns:
                types_all = sorted(filtered["strategy_type"].dropna().unique().tolist())
                sel_types = st.multiselect("Strategy type", types_all, default=types_all, key="ul_types")
                if sel_types:
                    filtered = filtered[filtered["strategy_type"].isin(sel_types)]
        with f2:
            if "dataset" in filtered.columns:
                ds_all = sorted(filtered["dataset"].dropna().unique().tolist())
                sel_ds = st.multiselect("Dataset", ds_all, default=ds_all, key="ul_ds")
                if sel_ds:
                    filtered = filtered[filtered["dataset"].isin(sel_ds)]
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

        st.caption(f"Showing {len(filtered)} of {total_strats} strategies")

        # ── Main table ───────────────────────────────────────────────────────
        display_cols = [c for c in [
            "rank", "strategy_type", "dataset", "leader_strategy_name", "quality_flag",
            "leader_pf", "is_pf", "oos_pf", "leader_net_pnl", "leader_trades",
            "recent_12m_pf", "run_id",
        ] if c in filtered.columns]

        if display_cols:
            disp = filtered[display_cols].copy()
            for num_col in ["leader_pf", "is_pf", "oos_pf", "recent_12m_pf"]:
                if num_col in disp.columns:
                    disp[num_col] = pd.to_numeric(disp[num_col], errors="coerce").round(2)
            if "leader_net_pnl" in disp.columns:
                disp["leader_net_pnl"] = pd.to_numeric(disp["leader_net_pnl"], errors="coerce").apply(
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

    if selected_run:
        with st.expander("Selected Run Detail", expanded=False):
            rid = selected_status.get("run_id", selected_run_dir.name if selected_run_dir else "?")
            st.markdown(
                f"**Run ID**: `{rid}`  \n"
                f"**Path**: `{selected_run_dir}`  \n"
                f"**Updated**: `{selected_status.get('updated_utc', 'unknown')}`  \n"
                f"**Machine**: `{selected_manifest.get('machine_type','?')}` in `{selected_manifest.get('zone','?')}`  \n"
                f"**Destroy reason**: `{selected_status.get('destroy_reason','unknown')}`  \n"
                f"**Bundle size**: `{format_bytes(selected_status.get('bundle_size_bytes'))}`"
            )
            recovery = selected_status.get("recovery_commands") or []
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
