from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard_utils import (
    badge_for_value,
    build_run_choice_label,
    collect_launcher_run_records,
    estimate_run_cost,
    format_bytes,
)


st.set_page_config(page_title="Strategy Engine Monitor", layout="wide")
st.title("Strategy Sweep Monitor")

records = collect_launcher_run_records(Path("cloud_results"))
if not records:
    st.warning("No launcher-managed cloud runs found yet.")
    st.stop()

record = records[0]
status = record["launcher_status"]
manifest = record["run_manifest"]
run_dir = record["run_dir"]
outputs_dir = record["outputs_dir"]

st.subheader("Latest Cloud Run")
st.caption(build_run_choice_label(record))

run_outcome = str(status.get("run_outcome") or "unknown")
vm_outcome = str(status.get("vm_outcome") or "unknown")

summary_cols = st.columns(4)
summary_cols[0].metric("Run Outcome", badge_for_value(run_outcome))
summary_cols[1].metric("VM Outcome", badge_for_value(vm_outcome))
summary_cols[2].metric("Artifact Downloaded", "yes" if status.get("artifacts_downloaded") else "no")
summary_cols[3].metric("Artifact Verified", "yes" if status.get("artifact_verified") else "no")

detail_cols = st.columns(4)
detail_cols[0].metric("Destroy Allowed", "yes" if status.get("destroy_allowed") else "no")
detail_cols[1].metric(
    "Billing Likely Stopped",
    "yes" if vm_outcome == "vm_destroyed" or run_outcome == "dry_run_complete" else "no" if status.get("instance_exists_at_end") else "unknown",
)
detail_cols[2].metric("Bundle Size", format_bytes(status.get("bundle_size_bytes")))
detail_cols[3].metric("Machine Type", str(manifest.get("machine_type") or status.get("machine_type") or "unknown"))

if run_outcome != "run_completed_verified":
    st.error(
        "Run did not complete verified artifact retrieval. "
        "Do not trust this run until the launcher status and local artifacts are checked."
    )

if not outputs_dir or not outputs_dir.exists():
    st.warning("This run has no extracted Outputs directory locally. The latest run is incomplete or unverified.")

if status.get("failure_reason"):
    st.info(f"Failure reason: {status['failure_reason']}")

cost = estimate_run_cost(record)
st.write(
    f"Run ID: `{status.get('run_id', run_dir.name)}`  \n"
    f"Run Path: `{run_dir}`  \n"
    f"Stage: `{status.get('stage', 'unknown')}`  \n"
    f"Message: `{status.get('message', '')}`  \n"
    f"Updated UTC: `{status.get('updated_utc', 'unknown')}`  \n"
    f"Estimated Cost: `{cost['estimated_total_cost'] if cost['estimated_total_cost'] is not None else 'unknown'}`"
)

artifact_log = run_dir / "artifacts" / "logs" / "engine_run.log"
legacy_log = run_dir / "logs" / "engine_run.log"
log_path = artifact_log if artifact_log.exists() else legacy_log

st.subheader("Engine Log Tail")
if log_path.exists():
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    st.code("\n".join(lines[-50:]) or "(log is empty)")
else:
    st.warning("No local engine log was extracted for the latest run.")
