#!/usr/bin/env python3
"""
Nova Autonomy Guard
- Reads /home/m4j1k/Nova/core/autonomy.yaml (fallback: ./core/autonomy.yaml)
- Enforces tool/mode restrictions + confidence thresholds
- Adds: record["guard"] = {allowed, reason, policy_snapshot}
- Writes an audit line to ./logs/autonomy.log (creates dirs)

Input: JSONL on stdin
Output: JSONL on stdout
"""

import json
import os
import sys
import datetime
from typing import Any, Dict, List, Tuple
import yaml
from pathlib import Path

# ---------- tiny YAML reader (supports simple key/value + nesting via indentation) ----------
def _parse_yaml_minimal(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(0, root)]
    last_key_stack: List[str] = []

    def current(indent: int) -> Dict[str, Any]:
        while stack and indent < stack[-1][0]:
            stack.pop()
        return stack[-1][1]

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        line = line.lstrip()

        # list items not needed for our core enforcement; ignore safely
        if line.startswith("- "):
            continue

        if ":" not in line:
            continue

        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")

        obj = current(indent)

        # create nested dict if val empty
        if val == "":
            obj[key] = {}
            stack.append((indent + 2, obj[key]))
            continue

        # type coercion
        if val.lower() in ("true", "false"):
            obj[key] = (val.lower() == "true")
        else:
            try:
                obj[key] = float(val) if "." in val else int(val)
            except ValueError:
                obj[key] = val

    return root


def load_policy() -> Dict[str, Any]:
    candidates = [
        os.path.expanduser("~/Nova/core/autonomy.yaml"),
        os.path.join(os.getcwd(), "core", "autonomy.yaml"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return _parse_yaml_minimal(f.read())
    # safe fallback policy
    return {
        "autonomy": {"enabled": True},
        "internet": {"mode": "disabled"},
        "safety": {"require_audit_log": True},
        "tools": {"allowed": {}, "denied": {}},
    }


def log_line(msg: str) -> None:
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "autonomy.log")
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")


def get_mode(policy: Dict[str, Any], record: Dict[str, Any]) -> str:
    # prefer explicit intent.mode, fallback to "recon"
    intent = record.get("intent") or {}
    mode = get_active_mode()
    return str(mode)


def get_min_conf(policy: Dict[str, Any], mode: str) -> float:
    modes = policy.get("modes") or {}
    m = modes.get(mode) or {}
    try:
        return float(m.get("min_confidence", 0.0))
    except Exception:
        return 0.0


def allow_mutations(policy: Dict[str, Any], mode: str) -> bool:
    modes = policy.get("modes") or {}
    m = modes.get(mode) or {}
    return bool(m.get("allow_mutations", False))


def is_mutation(record: Dict[str, Any]) -> bool:
    src = record.get("source", "")
    return isinstance(src, str) and src.startswith("mutation:")


def should_block_for_internet(policy: Dict[str, Any], record: Dict[str, Any]) -> Tuple[bool, str]:
    # This guard doesn't fetch internet; it only blocks records that *imply* forbidden internet ops.
    net = policy.get("internet") or {}
    mode = str(net.get("mode", "disabled"))

    # if record says it needs fetch (optional field you may add later)
    needs_fetch = bool(record.get("needs_fetch", False))
    if not needs_fetch:
        return (False, "")

    if mode in ("disabled", "off", "none"):
        return (True, "internet disabled by policy")

    # deny authentication by policy
    if bool(net.get("deny_authentication", True)) and bool(record.get("needs_auth", False)):
        return (True, "internet auth denied by policy")

    return (False, "")


def decide(policy: Dict[str, Any], record: Dict[str, Any]) -> Tuple[bool, str]:
    if not bool((policy.get("autonomy") or {}).get("enabled", True)):
        return (False, "autonomy disabled")

    mode = get_mode(policy, record)

    # confidence gating
    conf = record.get("confidence", 0.0)
    try:
        conf = float(conf)
    except Exception:
        conf = 0.0
    min_conf = get_min_conf(policy, mode)
    if conf < min_conf:
        return (False, f"confidence {conf:.2f} < min_confidence {min_conf:.2f} for mode '{mode}'")

    # mutation gating
    if is_mutation(record) and not allow_mutations(policy, mode):
        return (False, f"mutations blocked in mode '{mode}'")

    # submission safety
    sub = record.get("submission_status")
    if mode == "submission" and sub not in ("READY", "REVIEW"):
        return (False, f"mode 'submission' requires READY/REVIEW, got {sub}")

    # internet safety (optional future use)
    block, reason = should_block_for_internet(policy, record)
    if block:
        return (False, reason)

    return (True, "ok")


def main() -> int:
    policy = load_policy()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)

        allowed, reason = decide(policy, record)
        record["guard"] = {
            "allowed": bool(allowed),
            "reason": reason,
            "mode": get_mode(policy, record),
            "policy_snapshot": {
                "autonomy_enabled": bool((policy.get("autonomy") or {}).get("enabled", True)),
                "internet_mode": str((policy.get("internet") or {}).get("mode", "disabled")),
            },
        }

        # audit
        host = record.get("host", "?")
        path = record.get("path", "?")
        log_line(f"{host}{path} | allowed={allowed} | {reason}")

        # If blocked, mark as HOLD so downstream tools don't format/submit it.
        if not allowed:
            record["submission_status"] = "HOLD"

        print(json.dumps(record))

    return 0
def get_active_mode():
    mode_file = Path.home() / "Nova/core/mode.yaml"
    if mode_file.exists():
        with open(mode_file) as f:
            return yaml.safe_load(f).get("active_mode", "recon")
    return "recon"


if __name__ == "__main__":
    raise SystemExit(main())
