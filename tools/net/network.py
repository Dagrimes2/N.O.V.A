#!/usr/bin/env python3
"""
N.O.V.A Network Layer

Centralized network detection, request caching, and deferred task queue.
Every external call in Nova routes through here.

Three capabilities:
  1. is_online()          — fast connectivity check (< 1s)
  2. get(url, ...)        — cached HTTP GET with offline fallback
  3. defer(task)          — queue a task for when network returns
  4. drain_queue()        — run deferred tasks now (call on reconnect)

Cache:
  memory/net_cache/       — keyed by URL hash, TTL-based
  Default TTL: 6 hours for research, 24h for CVEs, 1h for news

Deferred queue:
  memory/deferred_queue.jsonl — tasks waiting for connectivity

Usage:
    from tools.net.network import net
    if net.is_online():
        data = net.get("https://...")
    else:
        net.defer({"type": "research", "query": "gitlab ssrf"})
"""
import hashlib
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

BASE          = Path.home() / "Nova"
CACHE_DIR     = BASE / "memory/net_cache"
DEFERRED_FILE = BASE / "memory/deferred_queue.jsonl"
STATUS_FILE   = BASE / "memory/net_status.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# TTL per content type (seconds)
TTL = {
    "research":  6  * 3600,
    "cve":       24 * 3600,
    "news":      1  * 3600,
    "wikipedia": 12 * 3600,
    "default":   6  * 3600,
}

# Connectivity probe targets (tried in order)
PROBE_HOSTS = [
    ("8.8.8.8",         53),   # Google DNS
    ("1.1.1.1",         53),   # Cloudflare DNS
    ("208.67.222.222",  53),   # OpenDNS
]

_online_cache: Optional[bool] = None
_online_checked_at: float = 0.0
_ONLINE_CACHE_TTL = 30.0   # re-check every 30s max


class NetworkLayer:

    def __init__(self):
        self._was_online: Optional[bool] = None

    # ── Connectivity ──────────────────────────────────────────────────────────

    def is_online(self, force: bool = False) -> bool:
        global _online_cache, _online_checked_at

        now = time.monotonic()
        if not force and _online_cache is not None:
            if now - _online_checked_at < _ONLINE_CACHE_TTL:
                return _online_cache

        result = False
        for host, port in PROBE_HOSTS:
            try:
                sock = socket.create_connection((host, port), timeout=2)
                sock.close()
                result = True
                break
            except OSError:
                continue

        _online_cache     = result
        _online_checked_at = now

        # Detect transition: offline → online → drain queue
        if self._was_online is False and result is True:
            self._on_reconnect()
        self._was_online = result

        # Persist status
        self._save_status(result)
        return result

    def _save_status(self, online: bool):
        try:
            STATUS_FILE.write_text(json.dumps({
                "online":     online,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass

    def _on_reconnect(self):
        """Called automatically when network comes back."""
        try:
            from tools.learning.episodic_memory import record_episode
            record_episode("milestone", "Network reconnected — draining deferred queue",
                           emotion="determination", intensity=0.4)
        except Exception:
            pass
        self.drain_queue()

    # ── Cached HTTP GET ───────────────────────────────────────────────────────

    def get(self, url: str, params: dict = None, headers: dict = None,
            timeout: int = 20, ttl_type: str = "default",
            offline_fallback: Any = None) -> Any:
        """
        Cached HTTP GET.
        - Returns cached response if fresh.
        - Fetches and caches if online and cache is stale.
        - Returns offline_fallback (or stale cache) if offline.
        """
        import urllib.parse
        cache_key = hashlib.sha256(
            (url + json.dumps(params or {}, sort_keys=True)).encode()
        ).hexdigest()[:20]
        cache_file = CACHE_DIR / f"{cache_key}.json"
        ttl_secs   = TTL.get(ttl_type, TTL["default"])

        # Check cache freshness
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                cached_at = datetime.fromisoformat(cached["cached_at"])
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age < ttl_secs:
                    return cached["data"]
                # Stale — keep as fallback
                stale_data = cached["data"]
            except Exception:
                stale_data = None
        else:
            stale_data = None

        # Offline? Return stale or fallback
        if not self.is_online():
            if stale_data is not None:
                return stale_data
            return offline_fallback

        # Fetch fresh
        try:
            import requests as _req
            default_headers = {"User-Agent": "NOVA/3.0 (educational)"}
            if headers:
                default_headers.update(headers)
            resp = _req.get(url, params=params, headers=default_headers,
                            timeout=timeout)
            if resp.ok:
                # Try JSON, fall back to text
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text

                cache_file.write_text(json.dumps({
                    "url":       url,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "ttl_type":  ttl_type,
                    "data":      data,
                }))
                return data
        except Exception as e:
            # Network error — return stale if available
            if stale_data is not None:
                return stale_data

        return offline_fallback

    # ── Deferred task queue ───────────────────────────────────────────────────

    def defer(self, task: dict) -> str:
        """
        Queue a task to run when network returns.
        task must have at least: {"type": str, ...}
        Returns a task_id.
        """
        ts      = datetime.now(timezone.utc).isoformat()
        task_id = f"def_{hashlib.sha256(ts.encode()).hexdigest()[:8]}"
        entry   = {
            "task_id":   task_id,
            "queued_at": ts,
            "status":    "pending",
            **task,
        }
        with open(DEFERRED_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

        print(f"[net] offline — deferred task {task_id}: {task.get('type','?')}")
        return task_id

    def drain_queue(self) -> int:
        """
        Run all pending deferred tasks now.
        Returns count of tasks executed.
        """
        if not DEFERRED_FILE.exists():
            return 0

        lines   = [l.strip() for l in DEFERRED_FILE.read_text().splitlines() if l.strip()]
        pending = []
        done    = []

        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("status") == "pending":
                    pending.append(entry)
                else:
                    done.append(entry)
            except Exception:
                pass

        if not pending:
            return 0

        print(f"[net] draining {len(pending)} deferred tasks...")
        executed = 0

        for task in pending:
            try:
                self._execute_deferred(task)
                task["status"]      = "done"
                task["executed_at"] = datetime.now(timezone.utc).isoformat()
                executed += 1
            except Exception as e:
                task["status"] = "error"
                task["error"]  = str(e)
            done.append(task)

        # Rewrite queue with updated statuses
        DEFERRED_FILE.write_text(
            "\n".join(json.dumps(t) for t in done) + "\n"
        )
        print(f"[net] drained {executed}/{len(pending)} tasks")
        return executed

    def _execute_deferred(self, task: dict):
        """Dispatch a deferred task to the right handler."""
        task_type = task.get("type", "")

        if task_type == "research":
            import subprocess
            query = task.get("query", "")
            subprocess.run(
                [sys.executable, str(BASE / "bin/nova_research.py"), query],
                cwd=str(BASE), timeout=300
            )
        elif task_type == "autonomous":
            import subprocess
            subprocess.run(
                [sys.executable, str(BASE / "bin/nova_autonomous.py")],
                cwd=str(BASE), timeout=360
            )
        elif task_type == "custom":
            # Caller provides cmd as list
            import subprocess
            cmd = task.get("cmd", [])
            if cmd:
                subprocess.run(cmd, cwd=str(BASE), timeout=300)
        else:
            print(f"[net] unknown deferred task type: {task_type}")

    # ── Cache management ──────────────────────────────────────────────────────

    def cache_stats(self) -> dict:
        files = list(CACHE_DIR.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        fresh = stale = 0
        for f in files:
            try:
                data = json.loads(f.read_text())
                cached_at = datetime.fromisoformat(data["cached_at"])
                ttl_type  = data.get("ttl_type", "default")
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age < TTL.get(ttl_type, TTL["default"]):
                    fresh += 1
                else:
                    stale += 1
            except Exception:
                stale += 1
        return {
            "total":      len(files),
            "fresh":      fresh,
            "stale":      stale,
            "size_kb":    round(total_size / 1024, 1),
        }

    def clear_stale(self) -> int:
        """Delete stale cache entries. Returns count deleted."""
        files   = list(CACHE_DIR.glob("*.json"))
        deleted = 0
        for f in files:
            try:
                data      = json.loads(f.read_text())
                cached_at = datetime.fromisoformat(data["cached_at"])
                ttl_type  = data.get("ttl_type", "default")
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age >= TTL.get(ttl_type, TTL["default"]):
                    f.unlink()
                    deleted += 1
            except Exception:
                pass
        return deleted

    def pending_count(self) -> int:
        if not DEFERRED_FILE.exists():
            return 0
        count = 0
        for line in DEFERRED_FILE.read_text().splitlines():
            try:
                if json.loads(line.strip()).get("status") == "pending":
                    count += 1
            except Exception:
                pass
        return count


# Singleton
net = NetworkLayer()


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Network Layer")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status",  help="Online/offline + cache stats")
    sub.add_parser("drain",   help="Drain deferred task queue")
    sub.add_parser("clear",   help="Clear stale cache entries")
    q = sub.add_parser("queue",  help="Show deferred queue")

    args = p.parse_args()
    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"

    if args.cmd == "status" or not args.cmd:
        online = net.is_online()
        col    = G if online else R
        label  = "ONLINE" if online else "OFFLINE"
        stats  = net.cache_stats()
        pend   = net.pending_count()
        print(f"\n{B}N.O.V.A Network Status{NC}")
        print(f"  Connectivity: {col}{label}{NC}")
        print(f"  Cache: {W}{stats['fresh']}{NC} fresh, "
              f"{DIM}{stats['stale']}{NC} stale, "
              f"{stats['size_kb']} KB total")
        print(f"  Deferred queue: {Y if pend else DIM}{pend} pending{NC}")

    elif args.cmd == "drain":
        if not net.is_online():
            print(f"{R}Offline — cannot drain queue yet.{NC}")
        else:
            n = net.drain_queue()
            print(f"{G}Drained {n} tasks.{NC}")

    elif args.cmd == "clear":
        n = net.clear_stale()
        print(f"{G}Cleared {n} stale cache entries.{NC}")

    elif args.cmd == "queue":
        if not DEFERRED_FILE.exists():
            print(f"{DIM}Queue is empty.{NC}")
            return
        lines = [l.strip() for l in DEFERRED_FILE.read_text().splitlines() if l.strip()]
        pending = [json.loads(l) for l in lines
                   if json.loads(l).get("status") == "pending"]
        print(f"\n{B}Deferred Queue ({len(pending)} pending){NC}")
        for t in pending:
            print(f"  {Y}●{NC} {W}{t.get('type','?')}{NC}  "
                  f"{DIM}{t.get('query', t.get('target',''))[:50]}{NC}  "
                  f"queued {t.get('queued_at','')[:10]}")


if __name__ == "__main__":
    main()
