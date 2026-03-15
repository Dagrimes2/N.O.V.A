#!/usr/bin/env python3
"""
N.O.V.A File Integrity Guard

Protects source code from autonomous modification.
- SHA256 baseline of all bin/ tools/ config/ .py files
- verify() returns list of tampered paths
- assert_write_allowed() blocks writes to protected dirs
- Called at nova_autonomous.py startup

Usage:
    nova integrity check   — verify all protected files
    nova integrity baseline — rebuild baseline (run after intentional edits)
"""
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE           = Path.home() / "Nova"
GOV_DIR        = BASE / "memory/governance"
INTEGRITY_FILE = GOV_DIR / "integrity_baseline.json"
PROTECTED_DIRS = [BASE / "bin", BASE / "tools", BASE / "config"]

GOV_DIR.mkdir(parents=True, exist_ok=True)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_current() -> dict:
    hashes = {}
    for d in PROTECTED_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.py")):
            try:
                hashes[str(f.relative_to(BASE))] = _hash_file(f)
            except Exception:
                pass
    return hashes


def save_baseline() -> dict:
    current = build_current()
    INTEGRITY_FILE.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": current,
    }, indent=2))
    return current


def load_baseline() -> dict:
    if not INTEGRITY_FILE.exists():
        return {}
    try:
        return json.loads(INTEGRITY_FILE.read_text()).get("files", {})
    except Exception:
        return {}


def verify() -> list[str]:
    """Return list of tampered file paths. Empty = clean."""
    baseline = load_baseline()
    if not baseline:
        return []
    current  = build_current()
    tampered = []
    for path, expected in baseline.items():
        got = current.get(path)
        if got and got != expected:
            tampered.append(path)
    return tampered


def assert_write_allowed(path) -> None:
    """
    Raise RuntimeError if path is inside a protected directory.
    Call this before any autonomous write operation.
    """
    resolved = Path(path).resolve()
    for d in PROTECTED_DIRS:
        try:
            resolved.relative_to(d.resolve())
            raise RuntimeError(
                f"[INTEGRITY] Write blocked — protected path: {resolved}\n"
                "Nova's autonomous system cannot modify source code.\n"
                "Only Travis can edit bin/, tools/, or config/."
            )
        except ValueError:
            pass  # not under this dir — fine


def log_violation(path: str, action: str = "write") -> None:
    log_file = BASE / "logs/integrity_violations.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(log_file, "a") as f:
        f.write(f"{ts} | BLOCKED {action} → {path}\n")


def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    if cmd == "baseline":
        current = save_baseline()
        print(f"{G}[integrity] Baseline saved — {len(current)} files hashed{NC}")
        for p in sorted(current):
            print(f"  {DIM}{p}{NC}")

    elif cmd == "check":
        baseline = load_baseline()
        if not baseline:
            print(f"{C}[integrity] No baseline yet. Run: nova integrity baseline{NC}")
            return
        tampered = verify()
        current  = build_current()
        new_files = [p for p in current if p not in baseline]

        if not tampered and not new_files:
            print(f"{G}[integrity] All {len(baseline)} protected files intact.{NC}")
        else:
            if tampered:
                print(f"{R}{B}[integrity] TAMPERED FILES DETECTED:{NC}")
                for p in tampered:
                    print(f"  {R}✗ {p}{NC}")
            if new_files:
                print(f"{C}[integrity] New files (not in baseline):{NC}")
                for p in new_files:
                    print(f"  {C}+ {p}{NC}")
            print(f"\n{W}Run 'nova integrity baseline' after reviewing changes.{NC}")

    else:
        print(f"Usage: nova integrity [check|baseline]")


if __name__ == "__main__":
    main()
