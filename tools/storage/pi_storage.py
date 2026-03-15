#!/usr/bin/env python3
"""
N.O.V.A Raspberry Pi Storage Extension

When local disk fills up, offloads cold files to the Pi over SSH/rsync.
Hot data stays local. Cold data (older than N days) moves to Pi.
Nova can recall any file back from Pi on demand.

The Pi acts as a warm-cold tier:
  Local SSD (hot)  →  Pi SD/USB (cold)  →  (future) cloud

Configuration: config/storage.yaml
Usage:
    nova storage status        disk usage + Pi connectivity
    nova storage sync          offload cold files to Pi
    nova storage recall FILE   pull a file back from Pi
    nova storage ls            list files on Pi
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path.home() / "Nova"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# Load config
def _cfg() -> dict:
    try:
        import yaml
        cfg_file = BASE / "config/storage.yaml"
        if cfg_file.exists():
            return yaml.safe_load(cfg_file.read_text())
    except Exception:
        pass
    return {
        "local": {"threshold_pct": 85, "hot_dirs": ["memory/research", "logs"]},
        "pi": {"enabled": False, "host": "nova-pi.local", "user": "nova",
               "port": 22, "remote_path": "/home/nova/Nova-archive",
               "cold_after_days": 14},
        "offload": {"patterns": ["memory/research/research_*.json"],
                    "keep_local": 30}
    }


def disk_usage() -> dict:
    """Local disk usage stats."""
    total, used, free = shutil.disk_usage(str(BASE))
    pct = round(used / total * 100, 1)
    return {
        "total_gb": round(total / 1e9, 2),
        "used_gb":  round(used  / 1e9, 2),
        "free_gb":  round(free  / 1e9, 2),
        "pct":      pct,
    }


def nova_dir_sizes() -> dict[str, float]:
    """Size in MB of Nova's major directories."""
    cfg = _cfg()
    sizes = {}
    for d in cfg["local"].get("hot_dirs", []):
        path = BASE / d
        if path.exists():
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            sizes[d] = round(total / 1e6, 2)
    return sizes


def pi_reachable() -> bool:
    """Check if Pi is on the network."""
    cfg = _cfg()
    if not cfg["pi"].get("enabled"):
        return False
    host = cfg["pi"]["host"]
    port = cfg["pi"].get("port", 22)
    try:
        import socket
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        return True
    except Exception:
        return False


def cold_files() -> list[Path]:
    """
    Find local files eligible for offload:
    - Match offload patterns
    - Older than cold_after_days
    - Not in the keep_local most recent per pattern
    """
    cfg          = _cfg()
    cold_days    = cfg["pi"].get("cold_after_days", 14)
    keep_local   = cfg["offload"].get("keep_local", 30)
    cutoff       = datetime.now(timezone.utc) - timedelta(days=cold_days)
    patterns     = cfg["offload"].get("patterns", [])
    candidates   = []

    for pattern in patterns:
        matches = sorted(BASE.glob(pattern), key=lambda f: f.stat().st_mtime)
        # Keep the newest keep_local, everything else is cold
        cold = matches[:-keep_local] if len(matches) > keep_local else []
        for f in cold:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                candidates.append(f)

    return candidates


def sync_to_pi(dry_run: bool = False) -> dict:
    """
    Offload cold files to Pi via rsync.
    Returns summary of what was transferred.
    """
    cfg = _cfg()
    if not cfg["pi"].get("enabled"):
        return {"status": "pi_disabled", "transferred": 0}
    if not pi_reachable():
        return {"status": "pi_unreachable", "transferred": 0}

    files = cold_files()
    if not files:
        return {"status": "nothing_to_offload", "transferred": 0}

    host        = cfg["pi"]["host"]
    user        = cfg["pi"]["user"]
    port        = cfg["pi"].get("port", 22)
    remote_path = cfg["pi"]["remote_path"]
    transferred = 0

    for f in files:
        rel = f.relative_to(BASE)
        remote_dir = f"{user}@{host}:{remote_path}/{rel.parent}"
        cmd = [
            "rsync", "-az", "--remove-source-files",
            "-e", f"ssh -p {port} -o StrictHostKeyChecking=no",
            str(f), remote_dir
        ]
        if dry_run:
            print(f"  [dry] would offload: {rel}")
            transferred += 1
        else:
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=60)
                if result.returncode == 0:
                    transferred += 1
                    print(f"  [pi] offloaded: {rel}")
            except Exception as e:
                print(f"  [pi] error offloading {rel}: {e}")

    return {"status": "ok", "transferred": transferred, "total_candidates": len(files)}


def recall_from_pi(filename: str) -> bool:
    """Pull a specific file back from Pi to its original location."""
    cfg = _cfg()
    if not cfg["pi"].get("enabled"):
        print("Pi storage not enabled in config/storage.yaml")
        return False
    if not pi_reachable():
        print("Pi is not reachable")
        return False

    host        = cfg["pi"]["host"]
    user        = cfg["pi"]["user"]
    port        = cfg["pi"].get("port", 22)
    remote_path = cfg["pi"]["remote_path"]

    # Find file on Pi
    cmd = [
        "rsync", "-az",
        "-e", f"ssh -p {port} -o StrictHostKeyChecking=no",
        f"{user}@{host}:{remote_path}/**/{filename}", str(BASE) + "/"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        return result.returncode == 0
    except Exception as e:
        print(f"[pi] recall error: {e}")
        return False


def list_pi_files() -> list[str]:
    """List files stored on Pi."""
    cfg = _cfg()
    if not cfg["pi"].get("enabled") or not pi_reachable():
        return []
    host        = cfg["pi"]["host"]
    user        = cfg["pi"]["user"]
    port        = cfg["pi"].get("port", 22)
    remote_path = cfg["pi"]["remote_path"]
    try:
        result = subprocess.run(
            ["ssh", "-p", str(port), f"{user}@{host}", f"find {remote_path} -type f"],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip().splitlines()
    except Exception:
        return []


def auto_offload_if_needed() -> bool:
    """
    Called by autonomous cycle. Offloads if disk > threshold.
    Returns True if offload was triggered.
    """
    cfg = _cfg()
    threshold = cfg["local"].get("threshold_pct", 85)
    usage = disk_usage()
    if usage["pct"] >= threshold:
        print(f"[storage] Disk at {usage['pct']}% — offloading to Pi...")
        result = sync_to_pi()
        print(f"[storage] Transferred {result['transferred']} files")
        return True
    return False


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Pi Storage")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status",   help="Disk usage + Pi connectivity")
    sub.add_parser("sync",     help="Offload cold files to Pi")
    sub.add_parser("dry",      help="Dry run — show what would be offloaded")
    sub.add_parser("ls",       help="List files on Pi")
    r = sub.add_parser("recall",   help="Recall a file from Pi")
    r.add_argument("filename")

    args = p.parse_args()
    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"

    if args.cmd == "status" or not args.cmd:
        usage = disk_usage()
        pct_col = G if usage["pct"] < 70 else (Y if usage["pct"] < 85 else R)
        pi_ok   = pi_reachable()
        pi_col  = G if pi_ok else R
        pi_lbl  = "reachable" if pi_ok else "offline/disabled"
        cold    = cold_files()

        print(f"\n{B}N.O.V.A Storage{NC}")
        print(f"  Local disk:   {pct_col}{usage['pct']}%{NC} used  "
              f"({usage['used_gb']} / {usage['total_gb']} GB)")
        print(f"  Pi:           {pi_col}{pi_lbl}{NC}")
        print(f"  Cold files:   {W}{len(cold)}{NC} eligible for offload")

        sizes = nova_dir_sizes()
        if sizes:
            print(f"\n  {B}Nova directory sizes:{NC}")
            for d, mb in sorted(sizes.items(), key=lambda x: x[1], reverse=True):
                print(f"    {C}{d:35s}{NC} {W}{mb:.1f}{NC} MB")

    elif args.cmd == "sync":
        result = sync_to_pi()
        if result["status"] == "ok":
            print(f"{G}Transferred {result['transferred']} files to Pi.{NC}")
        else:
            print(f"{Y}Status: {result['status']}{NC}")

    elif args.cmd == "dry":
        files = cold_files()
        print(f"\n{B}Dry run — {len(files)} files would be offloaded:{NC}")
        for f in files[:20]:
            print(f"  {DIM}{f.relative_to(BASE)}{NC}")

    elif args.cmd == "ls":
        files = list_pi_files()
        if not files:
            print(f"{DIM}No files on Pi (or Pi disabled/unreachable).{NC}")
        else:
            for f in files:
                print(f"  {f}")

    elif args.cmd == "recall":
        ok = recall_from_pi(args.filename)
        print(f"{G if ok else R}{'Recalled' if ok else 'Failed'}: {args.filename}{NC}")


if __name__ == "__main__":
    main()
