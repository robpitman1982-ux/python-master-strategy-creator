from __future__ import annotations

import socket
import subprocess
from datetime import UTC, datetime
import pandas as pd
import streamlit as st

from dashboard_utils import (
    badge_for_value,
    billing_status_for_launcher,
    build_test_run_readiness,
    build_run_choice_label,
    canonical_runs_root,
    collect_console_run_records,
    estimate_run_cost,
    format_bytes,
    format_datetime,
    list_export_files,
    list_uploaded_datasets,
    load_log_tail,
    operator_action_summary,
    parse_dataset_filename,
    pick_best_candidate_file,
    read_console_run_status,
    read_console_selection,
    resolve_console_storage_paths,
    write_console_selection,
)
from paths import EXPORTS_DIR, LEGACY_RESULTS_DIR, RUNS_DIR, UPLOADS_DIR


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
        dataset_info = parse_dataset_filename(entry.name)
        rows.append(
            {
                "filename": entry.name,
                "size": format_bytes(entry.size_bytes),
                "market": dataset_info["market"],
                "timeframe": dataset_info["timeframe"],
                "modified_utc": format_datetime(entry.modified_at),
                "path": str(entry.path),
            }
        )
    return pd.DataFrame(rows)


def render_table(df: pd.DataFrame) -> None:
    try:
        st.dataframe(df, use_container_width=True)
    except Exception:
        st.code(df.to_string(index=False))


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
run_records = collect_console_run_records(
    storage=storage,
    repo_results_root=LEGACY_RESULTS_DIR,
    include_legacy_fallback=False,
)
uploaded_datasets = list_uploaded_datasets(storage)
export_files = list_export_files(storage)
readiness = build_test_run_readiness(storage=storage, run_records=run_records, uploaded_datasets=uploaded_datasets)
console_run_status = read_console_run_status()

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
st.sidebar.caption(f"uploads: {storage.uploads}")
st.sidebar.caption(f"runs: {canonical_runs_root(storage)}")
st.sidebar.caption(f"exports: {storage.exports}")

selected_run_label = st.sidebar.selectbox("Selected run", list(run_options) or ["No runs found"])
selected_dataset_names = st.sidebar.multiselect(
    "Datasets for run",
    list(dataset_options),
    default=[name for name in read_console_selection() if name in dataset_options] or list(dataset_options)[:1],
)
write_console_selection(selected_dataset_names)

selected_run = run_options.get(selected_run_label)
selected_dataset = dataset_options.get(selected_dataset_names[0]) if selected_dataset_names else None

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

st.subheader("Tonight Test Run")
readiness_cols = st.columns([1.1, 1.4, 1.4])
readiness_cols[0].metric("Readiness", readiness.state)
readiness_cols[1].metric("Selected Dataset", ", ".join(selected_dataset_names) if selected_dataset_names else "none")
readiness_cols[2].metric("Selected Run", selected_status.get("run_id", "none") if selected_run else "none")
st.write(readiness.summary)

checklist_lines = []
for label, ok in readiness.checks:
    checklist_lines.append(f"[{'x' if ok else ' '}] {label}")
st.code("\n".join(checklist_lines))

st.caption(
    "Canonical storage paths: "
    f"uploads `{UPLOADS_DIR}` | runs `{RUNS_DIR}` | exports `{EXPORTS_DIR}`"
)

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
        render_table(_storage_files_table(uploaded_datasets))
    else:
        st.info(f"No uploaded datasets found in {storage.uploads}")

    if selected_dataset is not None:
        st.caption(f"Selected dataset path: {selected_dataset.path}")

    st.subheader("Exports")
    if export_files:
        render_table(_storage_files_table(export_files))
    else:
        st.info(f"No export files found in {storage.exports}")

    st.subheader("System Health")
    health_rows = pd.DataFrame(
        [
            {"check": "Uploads directory OK", "status": "yes" if UPLOADS_DIR.exists() else "no"},
            {"check": "Runs directory OK", "status": "yes" if RUNS_DIR.exists() else "no"},
            {"check": "Exports directory OK", "status": "yes" if EXPORTS_DIR.exists() else "no"},
            {"check": "Dataset count", "status": str(len(uploaded_datasets))},
            {"check": "Latest run status", "status": console_run_status.get("run_state", "unknown")},
        ]
    )
    render_table(health_rows)

with right:
    st.subheader("Run History")
    if run_records:
        render_table(_records_table(run_records))
    else:
        st.warning(f"No launcher-managed runs found in canonical runs storage: {canonical_runs_root(storage)}")

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
        render_table(leaderboard_preview)
    else:
        st.info("No leaderboard candidate file is available for the selected run.")
else:
    st.info("Select a run with extracted outputs to preview leaderboard results.")
