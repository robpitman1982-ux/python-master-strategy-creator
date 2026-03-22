from __future__ import annotations

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
    collect_console_run_records,
    estimate_run_cost,
    format_bytes,
    format_datetime,
    list_export_files,
    list_uploaded_datasets,
    load_log_tail,
    operator_action_summary,
    pick_best_candidate_file,
    resolve_console_storage_paths,
)


@st.cache_resource
def dashboard_runtime_metadata() -> dict[str, str]:
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
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


def _records_table(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        status = record["launcher_status"]
        rows.append(
            {
                "run_id": status.get("run_id", record["run_dir"].name),
                "updated_utc": status.get("updated_utc", "unknown"),
                "run_outcome": status.get("run_outcome", "unknown"),
                "vm_outcome": status.get("vm_outcome", "unknown"),
                "billing_status": billing_status_for_launcher(status),
                "path": str(record["run_dir"]),
            }
        )
    return pd.DataFrame(rows)


def _storage_files_table(entries: list) -> pd.DataFrame:
    rows = []
    for entry in entries:
        rows.append(
            {
                "filename": entry.name,
                "size": format_bytes(entry.size_bytes),
                "modified_utc": format_datetime(entry.modified_at),
                "path": str(entry.path),
            }
        )
    return pd.DataFrame(rows)


def _read_leaderboard_preview(run_record: dict, limit: int = 12) -> pd.DataFrame | None:
    candidate = pick_best_candidate_file(run_record.get("outputs_dir"))
    if candidate is None or not candidate.exists():
        return None
    try:
        return pd.read_csv(candidate).head(limit)
    except Exception:
        return None


st.set_page_config(page_title="Strategy Console", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    .console-banner {
        padding: 1.1rem 1.25rem;
        border-radius: 16px;
        background: linear-gradient(135deg, #102a43 0%, #1f4e5f 52%, #c05621 100%);
        color: #f8fafc;
        margin-bottom: 1.25rem;
        box-shadow: 0 18px 40px rgba(16, 42, 67, 0.18);
    }
    .console-banner h1 {margin: 0 0 0.35rem 0; font-size: 2rem;}
    .console-banner p {margin: 0; opacity: 0.92;}
    </style>
    """,
    unsafe_allow_html=True,
)

runtime = dashboard_runtime_metadata()
storage = resolve_console_storage_paths()
run_records = collect_console_run_records(storage=storage, repo_results_root=Path("cloud_results"))
uploaded_datasets = list_uploaded_datasets(storage)
export_files = list_export_files(storage)

run_options = {build_run_choice_label(record): record for record in run_records}
dataset_options = {entry.name: entry for entry in uploaded_datasets}

st.sidebar.title("Strategy Console")
st.sidebar.code(
    "\n".join(
        [
            f"commit: {runtime['commit']}",
            f"hostname: {runtime['hostname']}",
            f"dashboard started: {runtime['started_at']}",
        ]
    )
)
st.sidebar.caption(f"storage root: {storage.root}")

selected_run_label = st.sidebar.selectbox("Selected run", list(run_options) or ["No runs found"])
selected_dataset_label = st.sidebar.selectbox("Selected dataset", list(dataset_options) or ["No uploads found"])

selected_run = run_options.get(selected_run_label)
selected_dataset = dataset_options.get(selected_dataset_label)

if selected_run:
    selected_status = selected_run["launcher_status"]
    selected_manifest = selected_run["run_manifest"]
    selected_run_dir = selected_run["run_dir"]
    selected_outputs_dir = selected_run["outputs_dir"]
    run_outcome = str(selected_status.get("run_outcome") or "unknown")
    vm_outcome = str(selected_status.get("vm_outcome") or "unknown")
    billing_status = billing_status_for_launcher(selected_status)
    operator_summary = operator_action_summary(selected_status)
else:
    selected_status = {}
    selected_manifest = {}
    selected_run_dir = None
    selected_outputs_dir = None
    run_outcome = "unknown"
    vm_outcome = "unknown"
    billing_status = "unknown"
    operator_summary = "No runs available yet."

st.markdown(
    f"""
    <div class="console-banner">
        <h1>Strategy Console</h1>
        <p>Latest run state: {badge_for_value(run_outcome)} | Billing state: {billing_status} | Operator action: {operator_summary}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

top_metrics = st.columns(6)
top_metrics[0].metric("Run Outcome", badge_for_value(run_outcome))
top_metrics[1].metric("VM Outcome", badge_for_value(vm_outcome))
top_metrics[2].metric("Billing Status", billing_status)
top_metrics[3].metric("Artifact Verified", "yes" if selected_status.get("artifact_verified") else "no")
top_metrics[4].metric("Machine Type", str(selected_manifest.get("machine_type") or selected_status.get("machine_type") or "unknown"))
top_metrics[5].metric("Bundle Size", format_bytes(selected_status.get("bundle_size_bytes")))

left, right = st.columns([1.1, 1.4])

with left:
    st.subheader("Storage Overview")
    storage_cols = st.columns(4)
    storage_cols[0].metric("Uploads", str(len(uploaded_datasets)))
    storage_cols[1].metric("Runs", str(len(run_records)))
    storage_cols[2].metric("Exports", str(len(export_files)))
    storage_cols[3].metric("Backups Path", storage.backups.name)

    st.subheader("Uploaded Datasets")
    if uploaded_datasets:
        st.dataframe(_storage_files_table(uploaded_datasets), use_container_width=True, hide_index=True)
    else:
        st.info(f"No uploaded datasets found in {storage.uploads}")

    if selected_dataset is not None:
        st.caption(f"Selected dataset path: {selected_dataset.path}")

    st.subheader("Exports")
    if export_files:
        st.dataframe(_storage_files_table(export_files), use_container_width=True, hide_index=True)
    else:
        st.info(f"No export files found in {storage.exports}")

with right:
    st.subheader("Run History")
    if run_records:
        st.dataframe(_records_table(run_records), use_container_width=True, hide_index=True)
    else:
        st.warning("No launcher-managed runs found in storage or repo-local results.")

    st.subheader("Run Detail")
    if selected_run:
        cost = estimate_run_cost(selected_run)
        st.write(
            f"Run ID: `{selected_status.get('run_id', selected_run_dir.name)}`  \n"
            f"Run Path: `{selected_run_dir}`  \n"
            f"Updated UTC: `{selected_status.get('updated_utc', 'unknown')}`  \n"
            f"Destroy Reason: `{selected_status.get('destroy_reason', 'unknown')}`  \n"
            f"Operator Action: `{selected_status.get('operator_action', 'unknown')}`  \n"
            f"Estimated Cost: `{cost['estimated_total_cost'] if cost['estimated_total_cost'] is not None else 'unknown'}`"
        )

        recovery_commands = selected_status.get("recovery_commands") or []
        if recovery_commands:
            st.caption("Recovery commands")
            st.code("\n".join(recovery_commands))

        log_tail = load_log_tail(selected_run_dir)
        st.caption("Engine log tail")
        if log_tail:
            st.code(log_tail)
        else:
            st.info("No engine log found for this run yet.")
    else:
        st.info("Select a run to inspect its metadata and recovery guidance.")

st.subheader("Leaderboard Preview")
if selected_run and selected_outputs_dir:
    leaderboard_preview = _read_leaderboard_preview(selected_run)
    if leaderboard_preview is not None and not leaderboard_preview.empty:
        st.dataframe(leaderboard_preview, use_container_width=True, hide_index=True)
    else:
        st.info("No leaderboard candidate file is available for the selected run.")
else:
    st.info("Select a run with extracted outputs to preview leaderboard results.")
