#!/usr/bin/env python3
"""Minimal task-spooler *emulator* used by the test suite.

The real `tsp` daemon keeps state between client invocations; this
emulator does the same by persisting its job list to a JSON file given
in `FAKE_TSP_STATE`. It implements just enough of the CLI that the
dashboard needs:

    -l, --serialize json, -S [num], -i <id>, -p <id>, -c <id>,
    -k <id>, -r <id>, -T, -C, -u <id>, -U <a>-<b>, -K, -V

Anything it does not recognise is reported as an error (non-zero exit),
mirroring what a real tsp client does.
"""

import json
import os
import sys
from datetime import datetime

STATE_PATH = os.environ.get("FAKE_TSP_STATE")
if not STATE_PATH:
    print("fake tsp: FAKE_TSP_STATE is not set", file=sys.stderr)
    sys.exit(2)

FMT = "%-5s %-10s %-20s %-8s %-14s %s"
DONE = {"finished", "failed"}


def load():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    return {"jobs": [], "slots": 2, "alive": True, "next_id": 0}


def save(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_PATH)


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def _find(state, job_id):
    for job in state["jobs"]:
        if job["id"] == job_id:
            return job
    return None


def main():
    args = sys.argv[1:]
    if not args:
        args = ["-l"]

    state = load()

    # Once the server has been killed (-K), only -K itself "succeeds".
    if not state.get("alive", True) and args[0] != "-K":
        fail("Server is already exited, TS_SOCKET empty. Run -K or start a new server.")

    op = args[0]

    if op == "-V":
        print("Task Spooler v2.0.0 (fake)")

    elif op == "--serialize":
        rows = []
        for job in state["jobs"]:
            rows.append({
                "ID": int(job["id"]),
                "State": job["state"],
                "Output": job.get("output", ""),
                "E-Level": job.get("exit_code", 0),
                "Time_ms": job.get("time_ms", 0),
                "Command": job["command"],
                "Label": job.get("label", ""),
            })
        print(json.dumps(rows))

    elif op == "-l":
        lines = [FMT % ("ID", "State", "Output", "E-Level", "Times(r/u/s)",
                        f"Command [run={state.get('slots', 0)}]")]
        for job in state["jobs"]:
            lines.append(FMT % (
                job["id"], job["state"], job.get("output", ""),
                job.get("exit_code", ""), job.get("times", ""), job["command"],
            ))
        print("\n".join(lines))

    elif op == "-S":
        if len(args) > 1 and args[1].isdigit():
            state["slots"] = int(args[1])
            save(state)
        print(state["slots"])

    elif op == "-i":
        job = _find(state, args[1]) or fail(f"job {args[1]} not found")
        print("\n".join([
            f"Command: {job['command']}",
            "Slots required: 1",
            f"Enqueue time: {datetime.now().isoformat()}",
            f"Start time: {datetime.now().isoformat()}",
            "Time running: 0.00s",
        ]))

    elif op == "-p":
        job = _find(state, args[1]) or fail(f"job {args[1]} not found")
        print("1234")

    elif op == "-c":
        job = _find(state, args[1]) or fail(f"job {args[1]} not found")
        print(job.get("output_text", "hello from fake tsp"))

    elif op == "-k":
        job = _find(state, args[1]) or fail(f"job {args[1]} not found")
        job["state"] = "finished"
        job["exit_code"] = 143
        job["times"] = "1.00s"
        save(state)

    elif op == "-r":
        job = _find(state, args[1]) or fail(f"job {args[1]} not found")
        state["jobs"] = [j for j in state["jobs"] if j["id"] != job["id"]]
        save(state)

    elif op == "-T":
        for job in state["jobs"]:
            if job["state"] == "running":
                job["state"] = "finished"
                job["exit_code"] = 143
        save(state)

    elif op == "-C":
        state["jobs"] = [j for j in state["jobs"] if j["state"] not in DONE]
        save(state)

    elif op == "-u":
        for i, job in enumerate(state["jobs"]):
            if job["id"] == args[1]:
                state["jobs"].insert(0, state["jobs"].pop(i))
                save(state)
                break
        else:
            fail(f"job {args[1]} not found")

    elif op == "-U":
        a, b = args[1].split("-")
        ia = next((i for i, j in enumerate(state["jobs"]) if j["id"] == a), None)
        ib = next((i for i, j in enumerate(state["jobs"]) if j["id"] == b), None)
        if ia is None or ib is None:
            fail(f"jobs {a} or {b} not found")
        state["jobs"][ia], state["jobs"][ib] = state["jobs"][ib], state["jobs"][ia]
        save(state)

    elif op == "-K":
        state["alive"] = False
        save(state)
        print("Server ended, emptying TS_SOCKET.")

    else:
        fail(f"fake tsp: unsupported option {op}")

    sys.exit(0)


if __name__ == "__main__":
    main()