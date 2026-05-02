"""Cross-platform SSH/SCP shim using paramiko on Windows where OpenSSH+subprocess hangs.

Provides drop-in replacement for `_run(["ssh", ...])` and `_run(["scp", ...])` calls
in auto_ingest_distributed_run.py and similar scripts. Signature mimics the relevant
parts of subprocess.CompletedProcess.

On non-Windows, falls through to subprocess (original behavior). Triggered when
the caller asks for `use_paramiko=True` or env PSC_SSH_PARAMIKO=1.
"""
from __future__ import annotations

import os
import platform
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

try:
    import paramiko  # type: ignore
except ImportError:  # paramiko optional
    paramiko = None  # type: ignore


@dataclass
class _Result:
    returncode: int
    stdout: str
    stderr: str
    args: list[str]


def _read_ssh_config_host(host: str) -> tuple[str, str]:
    """Resolve hostname/user from ~/.ssh/config, returning (hostname, user)."""
    cfg_path = Path.home() / ".ssh" / "config"
    if not cfg_path.exists():
        return host, _default_user()
    try:
        cfg = paramiko.SSHConfig()
        cfg.parse(cfg_path.open(encoding="utf-8"))
        info = cfg.lookup(host)
        hostname = info.get("hostname", host)
        user = info.get("user", _default_user())
        return hostname, user
    except Exception:
        return host, _default_user()


def _default_user() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "rob"


def _key_paths() -> list[str]:
    home = Path.home()
    candidates = [
        home / ".ssh" / "id_ed25519",
        home / ".ssh" / "id_rsa",
        home / ".ssh" / "id_ecdsa",
    ]
    return [str(p) for p in candidates if p.exists()]


def _connect(host: str, *, timeout: int = 15) -> "paramiko.SSHClient":
    if paramiko is None:
        raise RuntimeError("paramiko not installed")
    hostname, user = _read_ssh_config_host(host)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    keys = _key_paths()
    last_exc: Exception | None = None
    for key in keys:
        try:
            client.connect(
                hostname=hostname,
                port=22,
                username=user,
                key_filename=key,
                timeout=timeout,
                banner_timeout=timeout,
                auth_timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
            )
            return client
        except Exception as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError(f"no usable SSH key for {host}")


def _ssh_run(host: str, remote_cmd: str, *, timeout: int) -> _Result:
    try:
        client = _connect(host, timeout=min(15, timeout))
    except Exception as exc:
        return _Result(255, "", f"connect failed: {exc}", ["ssh", host, remote_cmd])
    try:
        stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=timeout)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        rc = stdout.channel.recv_exit_status()
        return _Result(rc, out, err, ["ssh", host, remote_cmd])
    finally:
        client.close()


def _scp_recursive(host: str, remote_src: str, local_dst: Path, *, timeout: int) -> _Result:
    """SCP recursively from remote_src on host to local_dst (used by watcher to stage)."""
    try:
        client = _connect(host, timeout=15)
        sftp = client.open_sftp()
        local_dst.mkdir(parents=True, exist_ok=True)

        def _copy_dir(rpath: str, lpath: Path) -> None:
            lpath.mkdir(parents=True, exist_ok=True)
            for entry in sftp.listdir_attr(rpath):
                rname = f"{rpath}/{entry.filename}"
                lname = lpath / entry.filename
                if entry.st_mode and (entry.st_mode & 0o040000):  # directory
                    _copy_dir(rname, lname)
                else:
                    sftp.get(rname, str(lname))

        # Determine if remote_src is dir or file
        try:
            attr = sftp.stat(remote_src)
            if attr.st_mode and (attr.st_mode & 0o040000):
                # mimic scp -r behavior: copy dir contents into target dir name
                _copy_dir(remote_src, local_dst / Path(remote_src).name)
            else:
                sftp.get(remote_src, str(local_dst / Path(remote_src).name))
        except FileNotFoundError as exc:
            return _Result(1, "", f"remote not found: {exc}", ["scp", remote_src, str(local_dst)])

        sftp.close()
        client.close()
        return _Result(0, "", "", ["scp", remote_src, str(local_dst)])
    except Exception as exc:
        return _Result(1, "", f"scp failed: {exc}", ["scp", remote_src, str(local_dst)])


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def should_use_paramiko() -> bool:
    if not is_windows():
        return False
    if paramiko is None:
        return False
    return os.environ.get("PSC_SSH_PARAMIKO", "1") != "0"


def run_compat(cmd: list[str], *, check: bool = True, timeout: int = 60) -> _Result:
    """Run an ssh/scp command with paramiko backend on Windows; subprocess elsewhere.

    Recognizes the same arg patterns the watcher uses:
      ['ssh', '-T', ...opts..., host, remote_cmd]
      ['scp', ...opts..., source, target]    (only -r remote->local supported)
    """
    if not should_use_paramiko() or not cmd:
        # Fall through to subprocess
        try:
            cp = subprocess.run(cmd, text=True, capture_output=True, check=check, timeout=timeout)
            return _Result(cp.returncode, cp.stdout, cp.stderr, list(cmd))
        except subprocess.TimeoutExpired as exc:
            r = _Result(124, exc.stdout or "", (exc.stderr or "") + f"\ntimeout {timeout}s", list(cmd))
            if check:
                raise subprocess.CalledProcessError(r.returncode, r.args, output=r.stdout, stderr=r.stderr)
            return r

    name = Path(cmd[0]).name.lower()
    if name == "ssh":
        # Skip dash-prefixed flags and -o KEY=VAL pairs to find host + remote_cmd
        i = 1
        host = None
        while i < len(cmd):
            a = cmd[i]
            if a.startswith("-"):
                # eat -o KEY=VAL
                if a == "-o" and i + 1 < len(cmd):
                    i += 2
                    continue
                # standalone flag like -T
                i += 1
                continue
            host = a
            i += 1
            break
        remote_cmd = " ".join(cmd[i:]) if i < len(cmd) else ""
        if host is None:
            return _Result(2, "", "no host in ssh args", list(cmd))
        result = _ssh_run(host, remote_cmd, timeout=timeout)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, list(cmd), output=result.stdout, stderr=result.stderr)
        return result

    if name == "scp":
        # Find source/dest (last two non-flag args)
        non_flag = [a for a in cmd[1:] if not a.startswith("-") and a not in ("yes", "no")]
        # Filter out -o KEY=VAL pairs
        i = 1
        positional: list[str] = []
        while i < len(cmd):
            a = cmd[i]
            if a == "-o" and i + 1 < len(cmd):
                i += 2
                continue
            if a.startswith("-"):
                i += 1
                continue
            positional.append(a)
            i += 1
        if len(positional) < 2:
            return _Result(2, "", "scp needs source and dest", list(cmd))
        src, dst = positional[0], positional[-1]
        # Only support remote->local (host:path -> /local/path)
        m = re.match(r"^([^/@\s]+):(.+)$", src)
        if not m:
            # Local->remote not yet implemented
            return _Result(2, "", "scp local->remote not supported via paramiko shim", list(cmd))
        host, remote_path = m.group(1), m.group(2)
        result = _scp_recursive(host, remote_path, Path(dst), timeout=timeout)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, list(cmd), output=result.stdout, stderr=result.stderr)
        return result

    # Anything else falls through to subprocess
    try:
        cp = subprocess.run(cmd, text=True, capture_output=True, check=check, timeout=timeout)
        return _Result(cp.returncode, cp.stdout, cp.stderr, list(cmd))
    except subprocess.TimeoutExpired as exc:
        r = _Result(124, exc.stdout or "", (exc.stderr or "") + f"\ntimeout {timeout}s", list(cmd))
        if check:
            raise subprocess.CalledProcessError(r.returncode, r.args, output=r.stdout, stderr=r.stderr)
        return r
