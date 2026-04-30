"""Planning helpers for splitting CFD sweep jobs across cluster hosts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


TIMEFRAME_WEIGHTS = {
    "daily": 1.0,
    "60m": 2.0,
    "30m": 3.0,
    "15m": 4.0,
    "5m": 8.0,
}


@dataclass(frozen=True)
class HostSpec:
    name: str
    workers: int

    @property
    def capacity(self) -> float:
        return max(float(self.workers), 1.0)


def parse_host_specs(host_specs: list[str]) -> list[HostSpec]:
    """Parse HOST:WORKERS specs."""
    hosts: list[HostSpec] = []
    seen: set[str] = set()
    for spec in host_specs:
        if ":" not in spec:
            raise ValueError(f"Invalid host spec '{spec}'. Use HOST:WORKERS, e.g. c240:36")
        name, workers_text = (part.strip() for part in spec.split(":", 1))
        if not name:
            raise ValueError(f"Invalid host spec '{spec}'. Host name is empty")
        if name in seen:
            raise ValueError(f"Duplicate host spec '{name}'")
        try:
            workers = int(workers_text)
        except ValueError as exc:
            raise ValueError(f"Invalid host spec '{spec}'. Workers must be an integer") from exc
        if workers < 1:
            raise ValueError(f"Invalid host spec '{spec}'. Workers must be >= 1")
        hosts.append(HostSpec(name=name, workers=workers))
        seen.add(name)

    if not hosts:
        raise ValueError("At least one host spec is required")
    return hosts


def job_weight(job: tuple[str, str]) -> float:
    """Return a rough relative runtime weight for a market/timeframe job."""
    _, timeframe = job
    return TIMEFRAME_WEIGHTS.get(timeframe, 2.0)


def assign_jobs_to_hosts(
    jobs: list[tuple[str, str]],
    hosts: list[HostSpec],
) -> dict[str, list[tuple[str, str]]]:
    """Greedily assign heavier jobs to the least-loaded host by worker capacity."""
    assignments = {host.name: [] for host in hosts}
    host_load = {host.name: 0.0 for host in hosts}
    host_by_name = {host.name: host for host in hosts}

    def normalized_load(host: HostSpec) -> float:
        return host_load[host.name] / host.capacity

    for job in sorted(jobs, key=job_weight, reverse=True):
        host = min(hosts, key=lambda item: (normalized_load(item), item.name))
        assignments[host.name].append(job)
        host_load[host.name] += job_weight(job)

    # Preserve a stable, readable order inside each host command.
    for host_name, host_jobs in assignments.items():
        assignments[host_name] = sorted(
            host_jobs,
            key=lambda job: (job[0], TIMEFRAME_WEIGHTS.get(job[1], 99), job[1]),
        )
        if host_name not in host_by_name:
            raise AssertionError(f"Unknown host assignment: {host_name}")
    return assignments


def format_job_spec(job: tuple[str, str]) -> str:
    market, timeframe = job
    return f"{market}:{timeframe}"


def build_host_command(
    jobs: list[tuple[str, str]],
    *,
    data_dir: str,
    workers: int,
    remote_root: str = ".",
    dry_run: bool = False,
) -> str:
    """Build the command a host should run for its exact job assignment."""
    root = str(PurePosixPath(remote_root))
    job_args = " ".join(format_job_spec(job) for job in jobs)
    dry_run_arg = " --dry-run" if dry_run else ""
    return (
        f"cd {root} && python run_cluster_sweep.py "
        f"--jobs {job_args} --data-dir {data_dir} --workers {workers}{dry_run_arg}"
    )
