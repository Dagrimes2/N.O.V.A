#!/usr/bin/env python3
"""
N.O.V.A System Health Monitor

Nova monitors her own hardware: CPU, RAM, disk, temperature, process health.
Runs every autonomous cycle. Alerts Travis if anything is degrading.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path.home() / "Nova"
HEALTH_DIR  = BASE / "memory/health"
HEALTH_LOG  = HEALTH_DIR / "health_log.jsonl"
LOG_MAXLEN  = 100

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)


# ── Raw readings ──────────────────────────────────────────────────────────────

def cpu_percent() -> float:
    """
    Read CPU usage from /proc/stat (two readings 0.1s apart). Returns 0-100.
    """
    def _read_stat() -> tuple[int, int]:
        """Returns (idle, total) jiffies from first cpu line."""
        try:
            text = Path("/proc/stat").read_text()
            for line in text.splitlines():
                if line.startswith("cpu "):
                    parts  = line.split()
                    values = [int(v) for v in parts[1:]]
                    # idle = index 3, iowait = index 4
                    idle  = values[3] + (values[4] if len(values) > 4 else 0)
                    total = sum(values)
                    return idle, total
        except Exception:
            pass
        return 0, 1

    idle1, total1 = _read_stat()
    time.sleep(0.1)
    idle2, total2 = _read_stat()

    delta_total = total2 - total1
    delta_idle  = idle2 - idle1

    if delta_total == 0:
        return 0.0
    return round((1.0 - delta_idle / delta_total) * 100.0, 1)


def ram_percent() -> tuple[float, float]:
    """
    Read /proc/meminfo. Returns (used_gb, total_gb).
    """
    try:
        info: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                try:
                    info[key] = int(parts[1])  # kB
                except ValueError:
                    pass
        total_kb    = info.get("MemTotal", 0)
        free_kb     = info.get("MemFree",  0)
        buffers_kb  = info.get("Buffers",  0)
        cached_kb   = info.get("Cached",   0)
        sreclaimable = info.get("SReclaimable", 0)
        available_kb = info.get("MemAvailable",
                                free_kb + buffers_kb + cached_kb + sreclaimable)
        used_kb  = total_kb - available_kb
        total_gb = round(total_kb / (1024 ** 2), 2)
        used_gb  = round(max(0, used_kb) / (1024 ** 2), 2)
        return used_gb, total_gb
    except Exception:
        return 0.0, 0.0


def disk_percent(path: str = "/") -> tuple[float, float]:
    """
    Use os.statvfs(). Returns (used_gb, total_gb).
    """
    try:
        stat       = os.statvfs(path)
        total_b    = stat.f_frsize * stat.f_blocks
        free_b     = stat.f_frsize * stat.f_bfree
        used_b     = total_b - free_b
        total_gb   = round(total_b / (1024 ** 3), 2)
        used_gb    = round(used_b  / (1024 ** 3), 2)
        return used_gb, total_gb
    except Exception:
        return 0.0, 0.0


def cpu_temp() -> float | None:
    """
    Try to read CPU temperature from /sys/class/thermal/thermal_zone*/temp.
    Returns highest temp in Celsius, or None if unavailable.
    """
    thermal_root = Path("/sys/class/thermal")
    if not thermal_root.exists():
        return None

    temps: list[float] = []
    for zone in thermal_root.glob("thermal_zone*"):
        temp_file = zone / "temp"
        try:
            raw   = int(temp_file.read_text().strip())
            # Linux stores in millidegrees Celsius
            temps.append(raw / 1000.0)
        except Exception:
            continue

    return round(max(temps), 1) if temps else None


def nova_processes() -> dict[str, bool]:
    """
    Check which Nova processes are running.
    Look for: nova_autonomous.py, nova_moltbook.py, discord_bot.py
    Returns {"process_name": True/False}
    """
    targets = {
        "nova_autonomous.py": False,
        "nova_moltbook.py":   False,
        "discord_bot.py":     False,
    }
    proc_root = Path("/proc")
    try:
        for pid_dir in proc_root.iterdir():
            if not pid_dir.name.isdigit():
                continue
            cmdline_file = pid_dir / "cmdline"
            try:
                cmdline = cmdline_file.read_bytes().replace(b"\x00", b" ").decode(
                    errors="ignore"
                )
                for target in list(targets.keys()):
                    if target in cmdline:
                        targets[target] = True
            except Exception:
                continue
    except Exception:
        pass
    return targets


# ── Snapshot & classification ─────────────────────────────────────────────────

def snapshot() -> dict:
    """
    Take a complete health snapshot.
    Returns {"cpu_pct", "ram_used_gb", "ram_total_gb", "disk_used_gb",
             "disk_total_gb", "cpu_temp_c", "processes", "ts", "status"}
    status: "healthy" | "warm" | "stressed" | "critical"
    Rules: critical if cpu>90 or ram>95% or disk>90% or temp>85°C
           stressed if cpu>75 or ram>85% or temp>75°C
           warm    if cpu>60 or temp>65°C
    """
    cpu_pct              = cpu_percent()
    ram_used, ram_total  = ram_percent()
    disk_used, disk_total = disk_percent("/")
    temp_c               = cpu_temp()
    procs                = nova_processes()
    ts                   = datetime.now(timezone.utc).isoformat()

    ram_pct  = (ram_used / ram_total * 100) if ram_total > 0 else 0.0
    disk_pct = (disk_used / disk_total * 100) if disk_total > 0 else 0.0
    t        = temp_c if temp_c is not None else 0.0

    # Classify
    if (cpu_pct > 90 or ram_pct > 95 or disk_pct > 90 or
            (temp_c is not None and temp_c > 85)):
        health_status = "critical"
    elif (cpu_pct > 75 or ram_pct > 85 or
          (temp_c is not None and temp_c > 75)):
        health_status = "stressed"
    elif cpu_pct > 60 or (temp_c is not None and temp_c > 65):
        health_status = "warm"
    else:
        health_status = "healthy"

    return {
        "cpu_pct":      cpu_pct,
        "ram_used_gb":  ram_used,
        "ram_total_gb": ram_total,
        "disk_used_gb": disk_used,
        "disk_total_gb": disk_total,
        "cpu_temp_c":   temp_c,
        "processes":    procs,
        "ts":           ts,
        "status":       health_status,
    }


def record_snapshot() -> dict:
    """Take snapshot and append to health_log.jsonl (keep last 100). Returns snapshot."""
    snap = snapshot()
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)

    # Read existing, append, trim
    existing: list[str] = []
    if HEALTH_LOG.exists():
        for line in HEALTH_LOG.read_text().strip().splitlines():
            if line.strip():
                existing.append(line)

    existing.append(json.dumps(snap))
    # Keep last LOG_MAXLEN entries
    trimmed = existing[-LOG_MAXLEN:]

    HEALTH_LOG.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    return snap


def check_and_alert() -> str | None:
    """
    Take snapshot. If status is "stressed" or "critical", return alert message.
    Otherwise return None.
    """
    snap   = snapshot()
    status = snap["status"]

    if status not in ("stressed", "critical"):
        return None

    temp_str = f"{snap['cpu_temp_c']:.1f}°C" if snap["cpu_temp_c"] is not None else "N/A"
    ram_total = snap["ram_total_gb"]
    ram_pct   = (snap["ram_used_gb"] / ram_total * 100) if ram_total > 0 else 0.0
    disk_total = snap["disk_total_gb"]
    disk_pct   = (snap["disk_used_gb"] / disk_total * 100) if disk_total > 0 else 0.0

    alert = (
        f"[NOVA HEALTH {status.upper()}] "
        f"CPU {snap['cpu_pct']:.1f}% | "
        f"RAM {snap['ram_used_gb']:.1f}/{ram_total:.1f} GB ({ram_pct:.0f}%) | "
        f"Disk {snap['disk_used_gb']:.1f}/{disk_total:.1f} GB ({disk_pct:.0f}%) | "
        f"Temp {temp_str}"
    )
    return alert


def to_prompt_context() -> str:
    """
    Return a compact one-line health string for LLM injection.
    Format: "Health: CPU 23% | RAM 4.1/8.0 GB | Disk 45/100 GB | Temp 52°C | status: healthy"
    """
    snap      = snapshot()
    temp_str  = f"{snap['cpu_temp_c']:.1f}°C" if snap["cpu_temp_c"] is not None else "N/A"
    return (
        f"Health: CPU {snap['cpu_pct']:.0f}% | "
        f"RAM {snap['ram_used_gb']:.1f}/{snap['ram_total_gb']:.1f} GB | "
        f"Disk {snap['disk_used_gb']:.0f}/{snap['disk_total_gb']:.0f} GB | "
        f"Temp {temp_str} | "
        f"status: {snap['status']}"
    )


# ── Display ───────────────────────────────────────────────────────────────────

def _status_color(s: str) -> str:
    return {
        "healthy":  "\033[32m",
        "warm":     "\033[33m",
        "stressed": "\033[33m",
        "critical": "\033[31m",
    }.get(s, "\033[37m")


def status() -> None:
    """Pretty-print current health snapshot with colored indicators."""
    G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; C = "\033[36m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    snap      = snapshot()
    st        = snap["status"]
    st_col    = _status_color(st)
    ram_total = snap["ram_total_gb"]
    ram_pct   = (snap["ram_used_gb"] / ram_total * 100) if ram_total > 0 else 0.0
    disk_total = snap["disk_total_gb"]
    disk_pct   = (snap["disk_used_gb"] / disk_total * 100) if disk_total > 0 else 0.0
    temp_str   = f"{snap['cpu_temp_c']:.1f}°C" if snap["cpu_temp_c"] is not None else "N/A"

    def _bar(pct: float, width: int = 20) -> str:
        filled = int(pct / 100 * width)
        col    = G if pct < 60 else (Y if pct < 80 else R)
        return col + "█" * filled + DIM + "░" * (width - filled) + NC

    print(f"\n{B}N.O.V.A System Health{NC}  {st_col}{st.upper()}{NC}")
    print(f"\n  CPU      {_bar(snap['cpu_pct'])}  {snap['cpu_pct']:5.1f}%")

    ram_col = G if ram_pct < 70 else (Y if ram_pct < 85 else R)
    print(f"  RAM      {_bar(ram_pct)}  {ram_col}{snap['ram_used_gb']:.1f}{NC}/{snap['ram_total_gb']:.1f} GB  ({ram_pct:.0f}%)")

    disk_col = G if disk_pct < 70 else (Y if disk_pct < 85 else R)
    print(f"  Disk     {_bar(disk_pct)}  {disk_col}{snap['disk_used_gb']:.1f}{NC}/{disk_total:.1f} GB  ({disk_pct:.0f}%)")

    if snap["cpu_temp_c"] is not None:
        t     = snap["cpu_temp_c"]
        tcol  = G if t < 60 else (Y if t < 75 else R)
        print(f"  Temp     {tcol}{t:.1f}°C{NC}")
    else:
        print(f"  Temp     {DIM}unavailable{NC}")

    print(f"\n  {B}Nova processes:{NC}")
    for proc, running in snap["processes"].items():
        icon = f"{G}●{NC}" if running else f"{DIM}○{NC}"
        print(f"    {icon} {proc}")

    print(f"\n  {DIM}Snapshot: {snap['ts'][:19]}{NC}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    p   = argparse.ArgumentParser(description="N.O.V.A System Health Monitor")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status",       help="Pretty-print current health (default)")
    sub.add_parser("snapshot",     help="Take and record a snapshot, print JSON")
    sub.add_parser("alert-check",  help="Print alert if stressed/critical, else silent")
    sub.add_parser("context",      help="Print compact prompt-context line")

    log_p = sub.add_parser("log", help="Show last N log entries")
    log_p.add_argument("n", nargs="?", type=int, default=10,
                       help="Number of entries to show (default 10)")

    args = p.parse_args()

    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    if args.cmd in (None, "status"):
        status()

    elif args.cmd == "snapshot":
        snap = record_snapshot()
        print(json.dumps(snap, indent=2))

    elif args.cmd == "alert-check":
        alert = check_and_alert()
        if alert:
            print(f"{R}{alert}{NC}")
            sys.exit(1)
        else:
            # Silent success
            pass

    elif args.cmd == "context":
        print(to_prompt_context())

    elif args.cmd == "log":
        n = args.n
        if not HEALTH_LOG.exists():
            print(f"{DIM}No health log yet.{NC}")
            return
        lines = [l for l in HEALTH_LOG.read_text().strip().splitlines() if l.strip()]
        recent = lines[-n:]
        print(f"\n{B}Health log (last {len(recent)} entries):{NC}\n")
        for line in recent:
            try:
                snap  = json.loads(line)
                st    = snap.get("status", "?")
                col   = _status_color(st)
                ts    = snap.get("ts", "?")[:19]
                cpu   = snap.get("cpu_pct", 0)
                ru    = snap.get("ram_used_gb", 0)
                rt    = snap.get("ram_total_gb", 0)
                temp  = snap.get("cpu_temp_c")
                t_str = f"{temp:.0f}°C" if temp is not None else "—"
                print(f"  {DIM}{ts}{NC}  {col}{st:<8}{NC}  "
                      f"CPU {cpu:4.0f}%  RAM {ru:.1f}/{rt:.1f}GB  Temp {t_str}")
            except Exception:
                print(f"  {DIM}{line[:80]}{NC}")
        print()


if __name__ == "__main__":
    main()
