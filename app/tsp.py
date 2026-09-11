"""Task-spooler client wrapper.

Shells out to the `tsp` binary (the *client*), which talks to the
task-spooler daemon over the socket pointed at by `TS_SOCKET` (or under
`$TMPDIR`). All parsing of `tsp` output lives in this module.

The binary is located at runtime; set `TSP_BIN` to override
(used heavily by the test suite).
"""

import json
import os
import re
import shutil
import subprocess


class TSPError(RuntimeError):
    """A tsp invocation failed in a non-fatal, explainable way."""


class TSPDead(TSPError):
    """The task-spooler server (daemon) is not reachable."""


def resolve_binary():
    """Locate the `tsp` CLI. `TSP_BIN` env override wins."""
    override = os.environ.get("TSP_BIN")
    if override:
        return override
    return shutil.which("tsp")


COLUMN_LABELS = ["ID", "State", "Output", "E-Level", "Times(r/u/s)", "Command"]


def _format_ms(ms):
    """Format milliseconds the way `tsp -i` does (…s/m/h)."""
    try:
        seconds = float(ms) / 1000.0
    except (TypeError, ValueError):
        return ""
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.2f}m"
    return f"{minutes / 60:.2f}h"


def _header_offsets(header_line):
    """Start column of each known label in a `tsp -l` header row."""
    offsets = []
    search_from = 0
    for label in COLUMN_LABELS:
        idx = header_line.find(label, search_from)
        if idx == -1:
            return None
        offsets.append(idx)
        search_from = idx + len(label)
    return offsets


def _slice_by_offsets(line, offsets):
    """Slice a fixed-width table row at the given column starts."""
    fields = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else None
        fields.append(line[start:end].strip() if start < len(line) else "")
    return fields


def _parse_json_jobs(data):
    """Parse the array produced by `tsp --serialize json`."""
    jobs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("ID")
        if raw_id is None:
            continue
        exit_level = item.get("E-Level")
        time_ms = item.get("Time_ms")
        label = item.get("Label") or ""
        jobs.append({
            "id": str(raw_id),
            "state": str(item.get("State", "")).strip().lower(),
            "output_file": str(item.get("Output") or ""),
            "exit_code": "" if exit_level is None else str(exit_level),
            "times": _format_ms(time_ms) if time_ms is not None else "",
            "command": str(item.get("Command") or "").strip(),
            "label": str(label).strip(),
        })
    return jobs


def _parse_table(raw):
    """Parse the fixed-width table printed by bare `tsp` / `tsp -l`."""
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return []
    header, rows = lines[0], lines[1:]
    offsets = (
        _header_offsets(header)
        if header.strip().lower().startswith(("id", "state"))
        else None
    )

    jobs = []
    for line in rows:
        if offsets:
            job_id, state, output, elevel, times, command = _slice_by_offsets(line, offsets)
        else:
            # Best-effort fallback for unexpected header formats.
            parts = re.split(r"\s{2,}", line.strip())
            if len(parts) < 2:
                continue
            job_id, state = parts[0], parts[1]
            output = parts[2] if len(parts) > 2 else ""
            elevel = parts[3] if len(parts) > 3 else ""
            times = parts[4] if len(parts) > 4 else ""
            command = parts[5] if len(parts) > 5 else ""

        if not job_id.strip():
            continue
        jobs.append({
            "id": job_id.strip(),
            "state": state.strip().lower(),
            "output_file": output.strip(),
            "exit_code": elevel.strip(),
            "times": times.strip(),
            "command": command.strip(),
            "label": "",
        })
    return jobs


def _parse_info(raw):
    """Parse the `Key: value` block printed by `tsp -i <id>`."""
    fields = []
    flat = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = label.strip()
        value = value.strip()
        if not label:
            continue
        fields.append({"label": label, "value": value})
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        flat[key] = value
    return {"fields": fields, **flat}


class TaskSpooler:
    """Thin, typed wrapper over the `tsp` command line."""

    def __init__(self, binary=None, timeout=15):
        self.binary = binary or resolve_binary()
        self.timeout = timeout

    # -- low level -----------------------------------------------------
    def _run(self, args):
        if not self.binary:
            raise TSPError("task-spooler binary not found (set TSP_BIN or add 'tsp' to PATH).")
        try:
            proc = subprocess.run(
                [self.binary, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise TSPError(f"tsp {' '.join(args)} timed out")
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def _expect(self, args, ok_msg="tsp command failed"):
        code, out, err = self._run(args)
        if code != 0:
            raise TSPError(err or out or ok_msg)
        return out

    # -- read ----------------------------------------------------------
    def list_jobs(self):
        """Return the job list, preferring `--serialize json`."""
        code, out, err = self._run(["--serialize", "json"])
        if code == 0:
            try:
                data = json.loads(out)
            except ValueError:
                data = None
            if isinstance(data, list):
                return _parse_json_jobs(data)

        # Older builds / odd output: fall back to parsing `tsp -l`.
        code, out, err = self._run(["-l"])
        if code != 0:
            raise TSPDead(err or out or "task-spooler server is not running")
        return _parse_table(out)

    def is_alive(self):
        try:
            code, _, _ = self._run(["-l"])
            return code == 0
        except TSPError:
            return False

    def version(self):
        try:
            return self._expect(["-V"])
        except TSPError:
            return None

    def get_slots(self):
        return self._expect(["-S"])

    def job_info(self, job_id):
        info = _parse_info(self._expect(["-i", job_id], f"could not read info for job #{job_id}"))
        # OS process id is only present while a job runs; non-fatal if missing.
        try:
            pid = self._expect(["-p", job_id]).strip()
            if pid.isdigit():
                info["fields"].insert(0, {"label": "PID", "value": pid})
                info["pid"] = pid
        except TSPError:
            pass
        return info

    def job_output(self, job_id):
        return self._expect(["-c", job_id], f"could not read output for job #{job_id}")

    # -- mutate --------------------------------------------------------
    def set_slots(self, num):
        self._expect(["-S", str(num)], "tsp -S failed")

    def cancel(self, job_id, action="remove"):
        """`kill` sends SIGTERM to a running job, `remove` deletes it."""
        flag = "-k" if action == "kill" else "-r"
        self._expect([flag, job_id], f"tsp {flag} {job_id} failed")

    def bump(self, job_id):
        """Move a queued job to the front of the queue (`tsp -u`)."""
        self._expect(["-u", job_id], f"tsp -u {job_id} failed")

    def swap(self, a, b):
        """Swap the queue positions of two jobs (`tsp -U a-b`)."""
        self._expect(["-U", f"{a}-{b}"], f"tsp -U {a}-{b} failed")

    def kill_all(self):
        """SIGTERM every running job group (`tsp -T`)."""
        self._expect(["-T"], "tsp -T failed")

    def clear(self):
        """Clear finished jobs from the list (`tsp -C`)."""
        self._expect(["-C"], "tsp -C failed")

    def shutdown(self):
        """Kill the task-spooler server itself (`tsp -K`)."""
        self._expect(["-K"], "tsp -K failed")