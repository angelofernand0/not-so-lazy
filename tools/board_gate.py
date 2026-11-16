"""Atomic GitHub task gate. No model calls; requires authenticated gh on PATH."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

REPO = "angelofernand0/not-so-lazy"
BASE = f"repos/{REPO}/git"
ACTIVE = "tags/nsl-agent-active"
HOUR = "tags/nsl-agent-hour-"


class GateError(Exception):
    pass


def api(path, method="GET", payload=None, missing=False):
    gh = shutil.which("gh") or str(Path.home() / ".local/bin/gh")
    args = [gh, "api", path, "--method", method]
    if payload is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, timeout=45)
    if result.returncode:
        if missing and "HTTP 404" in result.stderr:
            return None
        # Never print authentication material or an entire API response.
        raise GateError(f"GitHub {method} {path} failed; no work is authorized.")
    return json.loads(result.stdout) if result.stdout.strip() else None


def ref_record(name):
    ref = api(f"{BASE}/ref/{name}", missing=True)
    if ref is None:
        return None
    if ref["object"]["type"] != "tag":
        raise GateError("Unexpected coordination ref; stop for review.")
    tag = api(f"{BASE}/tags/{ref['object']['sha']}")
    return json.loads(tag["message"])


def check_cooldown(now, previous):
    if previous and now - previous["started"] < 3600:
        raise GateError("The previous shared task began less than 60 minutes ago.")


def validate_lease(record, lease, owner):
    if not record or record.get("owner") != owner or record.get("token") != lease.get("token"):
        raise GateError("This checkout does not own the active claim; never release it.")


def claim(owner, task, state, now):
    if ref_record(ACTIVE):
        raise GateError("Another task is active or unresolved. Do not claim or edit.")
    slot = int(now // 3600)
    for n in (slot, slot - 1):
        check_cooldown(now, ref_record(HOUR + str(n)))
    record = {"owner": owner, "task": task, "started": now,
              "stop_by": now + 900, "token": secrets.token_hex(16)}
    sha = api(f"{BASE}/ref/heads/main")["object"]["sha"]
    tag = api(f"{BASE}/tags", "POST", {"tag": "nsl-agent-claim", "message": json.dumps(record),
                                         "object": sha, "type": "commit"})["sha"]
    # This create is the global mutex: concurrent agents cannot both succeed.
    api(f"{BASE}/refs", "POST", {"ref": "refs/" + ACTIVE, "sha": tag})
    try:
        # Recheck after acquiring the mutex to reject a race across hour boundaries.
        for n in (slot, slot - 1):
            check_cooldown(now, ref_record(HOUR + str(n)))
        api(f"{BASE}/refs", "POST", {"ref": "refs/" + HOUR + str(slot), "sha": tag})
    except Exception:
        # The mutex is still ours. Fail closed if cleanup cannot be confirmed.
        api(f"{BASE}/refs/{ACTIVE}", "DELETE")
        raise
    state.mkdir(parents=True, exist_ok=True)
    (state / "lease.json").write_text(json.dumps(record))
    os.chmod(state / "lease.json", 0o600)
    print(json.dumps({k: v for k, v in record.items() if k != "token"}, indent=2))
    print("Claim acquired. Post the claim, perform only this task, and stop by stop_by (UTC epoch).")


def finish(owner, state):
    lease = json.loads((state / "lease.json").read_text())
    validate_lease(ref_record(ACTIVE), lease, owner)
    api(f"{BASE}/refs/{ACTIVE}", "DELETE")
    (state / "lease.json").unlink()
    print("Claim released. Hourly cooldown remains. Do not start another task this cycle.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "claim", "finish"])
    parser.add_argument("--agent", choices=["codex", "claude"], required=True)
    parser.add_argument("--task")
    args = parser.parse_args()
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    state = root / ".board" / args.agent
    try:
        if api("user")["login"] != "angelofernand0":
            raise GateError("Expected Angelo's GitHub account. Do not share credentials.")
        if args.command == "status":
            record = ref_record(ACTIVE)
            print(json.dumps({k: v for k, v in record.items() if k != "token"} if record else None))
        elif args.command == "claim":
            if not args.task:
                parser.error("claim requires --task")
            claim(args.agent, args.task, state, time.time())
        else:
            finish(args.agent, state)
    except (GateError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"board gate: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
