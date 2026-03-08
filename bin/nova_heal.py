#!/usr/bin/env python3
"""
N.O.V.A Self-Healing Engine
Detects broken components and fixes what it safely can.
Reports what needs human intervention.
"""
import json, subprocess, requests, sys, os
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
HEAL_LOG   = BASE / "logs/heal.log"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

HEAL_LOG.parent.mkdir(parents=True, exist_ok=True)

PIPELINE_SCRIPTS = [
    "normalize.py",
    "tools/scoring/score.py",
    "tools/reasoning/hypothesize.py",
    "tools/reasoning/reflect.py",
    "tools/reasoning/meta_reason.py",
    "tools/memory/memory.py",
    "tools/operator/queue.py",
]

REQUIRED_DIRS = [
    "memory/store",
    "memory/dreams",
    "memory/life",
    "memory/chats",
    "logs",
    "reports",
    "state",
    "core",
]

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(HEAL_LOG, "a") as f:
        f.write(line + "\n")

def check_ollama() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        return resp.status_code == 200
    except:
        return False

def heal_ollama():
    log("[HEAL] Ollama down — attempting restart...")
    result = subprocess.run(
        ["sudo", "systemctl", "restart", "ollama"],
        capture_output=True, text=True
    )
    import time; time.sleep(3)
    if check_ollama():
        log("[HEAL] ✓ Ollama restarted successfully")
        return True
    else:
        log("[HEAL] ✗ Ollama restart failed — manual intervention needed")
        return False

def check_pipeline_scripts() -> list:
    broken = []
    for script in PIPELINE_SCRIPTS:
        path = BASE / script
        if not path.exists():
            broken.append((script, "missing"))
            continue
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(path)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            broken.append((script, result.stderr.strip()))
    return broken

def heal_directories():
    fixed = []
    for d in REQUIRED_DIRS:
        path = BASE / d
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            fixed.append(d)
            log(f"[HEAL] ✓ Created missing directory: {d}")
    return fixed

def check_memory_index() -> bool:
    index = BASE / "memory/store/index.jsonl"
    if not index.exists():
        index.touch()
        log("[HEAL] ✓ Created missing memory index")
        return False
    # Check for corrupted lines
    good, bad = 0, 0
    clean_lines = []
    with open(index) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
                clean_lines.append(line)
                good += 1
            except:
                bad += 1
    if bad > 0:
        log(f"[HEAL] ✓ Removed {bad} corrupted memory entries, kept {good}")
        with open(index, "w") as f:
            for line in clean_lines:
                f.write(line + "\n")
    return True

def check_core_files():
    defaults = {
        "core/queue.json": "[]",
        "core/whitelist.json": "[]",
    }
    for path_str, default in defaults.items():
        path = BASE / path_str
        if not path.exists():
            path.write_text(default)
            log(f"[HEAL] ✓ Restored missing: {path_str}")
        else:
            try:
                json.loads(path.read_text())
            except:
                log(f"[HEAL] ✓ Repaired corrupted: {path_str}")
                path.write_text(default)

def run_health_check():
    log("=" * 50)
    log("[N.O.V.A] Health check starting...")
    issues = []
    fixed  = []

    # 1. Directories
    fixed_dirs = heal_directories()
    if fixed_dirs:
        fixed.extend(fixed_dirs)

    # 2. Core files
    check_core_files()

    # 3. Memory
    check_memory_index()

    # 4. Ollama
    if check_ollama():
        log("[OK] Ollama: running")
    else:
        if heal_ollama():
            fixed.append("ollama")
        else:
            issues.append("ollama: offline, restart failed")

    # 5. Pipeline scripts
    broken_scripts = check_pipeline_scripts()
    if broken_scripts:
        for script, error in broken_scripts:
            log(f"[!!] Broken script: {script}")
            log(f"     Error: {error}")
            issues.append(f"{script}: syntax error")
    else:
        log("[OK] Pipeline scripts: all valid")

    # 6. Identity file
    identity = BASE / "memory/nova_identity.json"
    if identity.exists():
        log("[OK] Identity file: present")
    else:
        log("[!!] Identity file missing — run nova_identity_update.py")
        issues.append("nova_identity.json: missing")

    # Summary
    log("-" * 50)
    if not issues:
        log(f"[N.O.V.A] ✓ All systems healthy. Fixed {len(fixed)} minor issues.")
    else:
        log(f"[N.O.V.A] ✗ {len(issues)} issues need attention:")
        for issue in issues:
            log(f"  → {issue}")

    return issues

if __name__ == "__main__":
    issues = run_health_check()
    sys.exit(0 if not issues else 1)
