"""
Strategy Discovery Engine — Dashboard
Run: streamlit run dashboard.py
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Strategy Engine Dashboard", layout="wide")

# --- Sidebar ---
st.sidebar.title("Strategy Engine")
tab = st.sidebar.radio("Navigate", ["Cloud Monitor", "Results Explorer", "Prop Firm Simulator"])

# ============================================================
# TAB 1: Cloud Monitor
# ============================================================
if tab == "Cloud Monitor":
    st.title("Cloud Run Monitor")

    col1, col2 = st.columns(2)
    instance = col1.text_input("Instance name", "strategy-sweep")
    zone = col2.text_input("Zone", "australia-southeast2-a")

    auto_refresh = st.checkbox("Auto-refresh every 60s", value=False)

    def run_gcloud_cmd(cmd: str) -> str:
        """Run a gcloud command and return stdout."""
        try:
            result = subprocess.run(
                f"gcloud compute ssh {instance} --zone={zone} --command=\"{cmd}\"",
                shell=True, capture_output=True, text=True, timeout=30,
                env={**__import__('os').environ, "CLOUDSDK_SSH_NATIVE": "1"},
            )
            return result.stdout.strip()
        except Exception as e:
            return f"ERROR: {e}"

    if st.button("Check Status") or auto_refresh:
        with st.spinner("Connecting to VM..."):
            # Get engine status
            status_raw = run_gcloud_cmd("cat /tmp/engine_status 2>/dev/null || echo PENDING")
            st.metric("Engine Status", status_raw)

            # Get all status.json files
            status_json_raw = run_gcloud_cmd(
                "for f in /root/python-master-strategy-creator/Outputs/*/status.json; do echo FILE:$f; sudo cat $f 2>/dev/null; done"
            )

            # Parse each dataset's status
            if "FILE:" in status_json_raw:
                chunks = status_json_raw.split("FILE:")
                for chunk in chunks:
                    if not chunk.strip():
                        continue
                    lines = chunk.strip().split("\n", 1)
                    filepath = lines[0].strip()
                    if len(lines) > 1:
                        try:
                            sj = json.loads(lines[1])
                            dataset = sj.get("dataset", "Unknown")
                            stage = sj.get("current_stage", "?")
                            family = sj.get("current_family", "?")
                            pct = sj.get("progress_pct", 0)
                            eta = sj.get("eta_seconds", 0)
                            elapsed = sj.get("elapsed_seconds", 0)

                            st.subheader(f"Dataset: {dataset}")
                            cols = st.columns(4)
                            cols[0].metric("Family", family)
                            cols[1].metric("Stage", stage)
                            cols[2].metric("Progress", f"{pct:.0f}%")
                            cols[3].metric("ETA", f"{eta/60:.1f} min" if eta > 0 else "—")
                            st.progress(min(pct / 100, 1.0))

                            completed = sj.get("families_completed", [])
                            remaining = sj.get("families_remaining", [])
                            st.caption(f"Completed: {completed} | Remaining: {remaining} | Elapsed: {elapsed/60:.0f} min")
                        except json.JSONDecodeError:
                            st.text(f"Could not parse status for {filepath}")

            # Engine log tail
            with st.expander("Engine Log (last 20 lines)"):
                log_tail = run_gcloud_cmd("sudo tail -20 /tmp/engine_run.log 2>/dev/null")
                st.code(log_tail)

        if auto_refresh:
            time.sleep(60)
            st.rerun()

    st.divider()

    # Destroy VM button
    with st.expander("Danger Zone"):
        st.warning("Destroying the VM will stop all billing but also stop any running engine.")
        confirm = st.checkbox("I confirm I want to destroy the VM and stop all billing")
        if st.button("Destroy VM", type="primary", disabled=not confirm):
            result = subprocess.run(
                f"gcloud compute instances delete {instance} --zone={zone} --quiet",
                shell=True, capture_output=True, text=True,
            )
            if result.returncode == 0:
                st.success("VM destroyed. No more charges.")
            else:
                st.error(f"Failed to destroy: {result.stderr}")

# ============================================================
# TAB 2: Results Explorer
# ============================================================
elif tab == "Results Explorer":
    st.title("Results Explorer")

    # Select output directory
    output_dirs = sorted(Path(".").glob("cloud_outputs*"))
    output_dirs += sorted(Path("Outputs").glob("*")) if Path("Outputs").exists() else []

    dir_options = [str(d) for d in output_dirs if d.is_dir()]
    if not dir_options:
        st.warning("No output directories found. Run a cloud job first.")
        st.stop()

    selected_dir = st.selectbox("Select output directory", dir_options)
    base = Path(selected_dir)

    # Find CSV files recursively
    def find_csv(name: str) -> Path | None:
        matches = list(base.rglob(name))
        return matches[0] if matches else None

    # Master Leaderboard
    ml_path = find_csv("master_leaderboard.csv")
    if ml_path:
        st.subheader("Master Leaderboard")
        ml = pd.read_csv(ml_path)

        display_cols = [c for c in [
            "rank", "market", "timeframe", "strategy_type", "leader_strategy_name",
            "quality_flag", "leader_pf", "is_pf", "oos_pf", "recent_12m_pf",
            "leader_trades", "leader_net_pnl",
        ] if c in ml.columns]

        fmt: dict = {}
        for col in ["leader_pf", "is_pf", "oos_pf", "recent_12m_pf"]:
            if col in display_cols:
                fmt[col] = "{:.2f}"
        if "leader_net_pnl" in display_cols:
            fmt["leader_net_pnl"] = "${:,.0f}"

        st.dataframe(
            ml[display_cols].style.format(fmt),
            use_container_width=True,
        )
    else:
        st.info("No master_leaderboard.csv found in selected directory.")

    # Portfolio Review
    pr_path = find_csv("portfolio_review_table.csv")
    if pr_path:
        st.subheader("Portfolio Review (Monte Carlo + Stress Tests)")
        pr = pd.read_csv(pr_path)
        st.dataframe(pr, use_container_width=True)

    # Correlation Matrix
    corr_path = find_csv("correlation_matrix.csv")
    if corr_path:
        st.subheader("Strategy Correlations")
        corr = pd.read_csv(corr_path, index_col=0)
        import plotly.express as px
        fig = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r",
                        zmin=-1, zmax=1, title="Return Correlation Matrix")
        st.plotly_chart(fig, use_container_width=True)

    # Yearly Stats
    ys_path = find_csv("yearly_stats_breakdown.csv")
    if ys_path:
        st.subheader("Yearly Performance")
        ys = pd.read_csv(ys_path)
        strategies = ys["strategy_name"].unique() if "strategy_name" in ys.columns else []
        if len(strategies) > 0:
            selected_strat = st.selectbox("Select strategy", strategies)
            strat_data = ys[ys["strategy_name"] == selected_strat]

            import plotly.graph_objects as go
            colors = ["green" if v > 0 else "red" for v in strat_data["net_pnl"]]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=strat_data["year"], y=strat_data["net_pnl"],
                                 marker_color=colors, name="Net PnL"))
            fig.update_layout(title=f"Yearly PnL: {selected_strat}", yaxis_title="Net PnL ($)")
            st.plotly_chart(fig, use_container_width=True)

    # Strategy Returns / Equity Curve
    sr_path = find_csv("strategy_returns.csv")
    if sr_path:
        st.subheader("Equity Curves")
        sr = pd.read_csv(sr_path)
        strat_cols = [c for c in sr.columns if c != "exit_time"]

        import plotly.graph_objects as go
        fig = go.Figure()
        for col in strat_cols:
            display_name = col.split("_", 3)[-1] if "_" in col else col
            cumulative = sr[col].cumsum()
            x_vals = sr["exit_time"] if "exit_time" in sr.columns else sr.index
            fig.add_trace(go.Scatter(x=x_vals, y=cumulative,
                                     mode="lines", name=display_name))
        fig.update_layout(title="Cumulative Equity Curves", yaxis_title="Cumulative PnL ($)",
                          xaxis_title="Exit Time")
        st.plotly_chart(fig, use_container_width=True)

# ============================================================
# TAB 3: Prop Firm Simulator
# ============================================================
elif tab == "Prop Firm Simulator":
    st.title("Prop Firm Challenge Simulator")
    st.info("Select an output directory in Results Explorer first, then come back here.")

    output_dirs = sorted(Path(".").glob("cloud_outputs*"))
    dir_options = [str(d) for d in output_dirs if d.is_dir()]

    if not dir_options:
        st.warning("No output directories found.")
        st.stop()

    selected_dir = st.selectbox("Output directory", dir_options, key="prop_dir")
    sr_path = list(Path(selected_dir).rglob("strategy_returns.csv"))

    if not sr_path:
        st.warning("No strategy_returns.csv found in selected directory.")
        st.stop()

    sr = pd.read_csv(sr_path[0])
    strat_cols = [c for c in sr.columns if c != "exit_time"]

    selected_strat = st.selectbox("Select strategy", strat_cols)

    col1, col2, col3 = st.columns(3)
    firm = col1.selectbox("Prop firm", ["The5ers Bootcamp $250K", "The5ers Bootcamp $100K", "The5ers High Stakes"])
    n_sims = col2.number_input("Simulations", value=5000, min_value=100, max_value=50000, step=1000)
    source_capital = col3.number_input("Source capital ($)", value=250000, step=50000)

    if st.button("Run Simulation"):
        trade_pnls = sr[selected_strat].dropna()
        trade_pnls = trade_pnls[trade_pnls != 0].tolist()

        if len(trade_pnls) < 10:
            st.error(f"Not enough trades ({len(trade_pnls)}). Need at least 10.")
            st.stop()

        st.write(f"Running {n_sims} Monte Carlo simulations on {len(trade_pnls)} trades...")

        try:
            from modules.prop_firm_simulator import (
                The5ersBootcampConfig,
                The5ersHighStakesConfig,
                monte_carlo_pass_rate,
            )

            target_map = {
                "The5ers Bootcamp $250K": 250_000,
                "The5ers Bootcamp $100K": 100_000,
                "The5ers High Stakes": 100_000,
            }
            target = target_map.get(firm, 250_000)

            if "High Stakes" in firm:
                config = The5ersHighStakesConfig(target=target)
            else:
                config = The5ersBootcampConfig(target=target)

            with st.spinner("Running Monte Carlo..."):
                stats = monte_carlo_pass_rate(
                    trade_pnls=trade_pnls,
                    config=config,
                    n_sims=int(n_sims),
                    source_capital=float(source_capital),
                )

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Pass Rate", f"{stats['pass_rate']*100:.1f}%")
            col2.metric("Avg Trades to Pass", f"{stats['avg_trades_to_pass']:.0f}")
            col3.metric("Median Trades", f"{stats['median_trades_to_pass']:.0f}")
            col4.metric("Worst DD %", f"{stats['worst_dd_pct']*100:.1f}%")

            st.success(f"Monte Carlo complete: {stats['pass_rate']*100:.1f}% pass rate over {n_sims} simulations")

        except ImportError as e:
            st.error(f"Could not import prop firm simulator: {e}")
        except Exception as e:
            st.error(f"Simulation error: {e}")
