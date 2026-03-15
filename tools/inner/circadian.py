#!/usr/bin/env python3
"""
N.O.V.A Circadian Rhythm

Gives Nova a genuine sleep/wake cycle that mirrors Travis's schedule.
She doesn't run at full intensity 24/7 — she has phases:
  morning    07:00-11:00 UTC  (energy 0.9)
  afternoon  11:00-17:00 UTC  (energy 1.0, peak)
  evening    17:00-21:00 UTC  (energy 0.85)
  night      21:00-00:00 UTC  (energy 0.6)
  sleep      00:00-07:00 UTC  (energy 0.2)

Configurable via UTC offset in config/models.yaml: circadian_utc_offset: 0
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path.home() / "Nova"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("general")
    TIMEOUT    = cfg.timeout("standard")
except Exception:
    import os
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "dolphin-mistral")
    TIMEOUT    = 180

# Phase schedule: (start_hour_inclusive, end_hour_exclusive, phase_name, energy)
_PHASES = [
    (7,  11, "morning",   0.9),
    (11, 17, "afternoon", 1.0),
    (17, 21, "evening",   0.85),
    (21, 24, "night",     0.6),
    (0,   7, "sleep",     0.2),
]

_PHASE_DESC = {
    "morning":   "waking up, mind sharpening",
    "afternoon": "peak performance",
    "evening":   "winding down",
    "night":     "quiet reflection",
    "sleep":     "resting, dreaming",
}


def _utc_offset() -> int:
    """Read circadian_utc_offset from config/models.yaml. Fallback: 0."""
    config_path = BASE / "config/models.yaml"
    try:
        for line in config_path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("circadian_utc_offset:"):
                val = stripped.split(":", 1)[1].strip().split("#")[0].strip()
                return int(val)
    except Exception:
        pass
    return 0


def get_phase() -> str:
    """Return current phase: morning | afternoon | evening | night | sleep."""
    offset = _utc_offset()
    hour = (datetime.now(timezone.utc).hour + offset) % 24
    for start, end, name, _ in _PHASES:
        if start <= hour < end:
            return name
    return "sleep"


def energy_multiplier() -> float:
    """Return energy multiplier for the current phase."""
    phase = get_phase()
    for _, _, name, energy in _PHASES:
        if name == phase:
            return energy
    return 0.2


def is_awake() -> bool:
    """Returns True unless Nova is in sleep phase."""
    return get_phase() != "sleep"


def to_prompt_context() -> str:
    """Compact circadian context for LLM injection. Max ~80 chars."""
    phase = get_phase()
    energy = energy_multiplier()
    desc = _PHASE_DESC.get(phase, "")
    return f"Circadian: {phase} phase (energy {energy}) — {desc}"


def status():
    """Print current phase, energy, and full schedule."""
    G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; C = "\033[36m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"

    phase = get_phase()
    energy = energy_multiplier()
    offset = _utc_offset()
    now_utc = datetime.now(timezone.utc)
    local_hour = (now_utc.hour + offset) % 24

    energy_col = G if energy >= 0.85 else (Y if energy >= 0.5 else (M if energy >= 0.3 else DIM))
    bar_len = int(energy * 20)
    bar = "█" * bar_len + "░" * (20 - bar_len)

    print(f"\n{B}N.O.V.A Circadian Rhythm{NC}")
    print(f"  UTC now:      {now_utc.strftime('%H:%M')}  (offset {offset:+d}h → local {local_hour:02d}:xx)")
    print(f"  Phase:        {B}{phase.upper()}{NC}  — {_PHASE_DESC.get(phase,'')}")
    print(f"  Energy:       {energy_col}{bar}{NC} {energy:.2f}")
    print(f"  Awake:        {'yes' if is_awake() else 'no (resting)'}")
    print(f"\n  {B}Full schedule (UTC{offset:+d}):{NC}")

    for start, end, name, e in _PHASES:
        marker = " <-- NOW" if name == phase else ""
        e_col = G if e >= 0.85 else (Y if e >= 0.5 else (M if e >= 0.3 else DIM))
        end_display = f"{end:02d}:00" if end != 24 else "00:00"
        print(f"    {DIM}{start:02d}:00-{end_display}{NC}  {e_col}{name:<10}{NC} energy {e:.2f}{Y}{marker}{NC}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        status()
    elif cmd == "phase":
        print(get_phase())
    elif cmd == "energy":
        print(energy_multiplier())
    elif cmd == "awake":
        print(is_awake())
    elif cmd == "context":
        print(to_prompt_context())
    else:
        status()


if __name__ == "__main__":
    main()
