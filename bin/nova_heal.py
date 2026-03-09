#!/usr/bin/env python3
"""
N.O.V.A Self-Healing Engine v3
Scans ALL Python scripts, repairs broken ones autonomously.
Backs up before every repair. Restores if fix fails.
Never touches governance or the main nova CLI.
"""
import json, subprocess, requests, sys, os, shutil
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
HEAL_LOG   = BASE / "logs/heal.log"
BACKUP_DIR = BASE / "memory/backups"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

HEAL_LOG.parent.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

PROTECTED = [
    str(BASE / "tools/governance/autonomy_guard.py"),
    str(BASE / "tools/governance/audit.py"),
    str(BASE / "bin/nova"),
]

REQUIRED_DIRS = [
    "memory/store", "memory/dreams", "memory/life",
    "memory/chats", "memory/research", "memory/proposals",
    "memory/backups", "logs", "reports", "state", "core", "tests",
]

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(HEAL_LOG, "a") as f:
        f.write(line + "\n")

def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"{path.name}.{ts}.bak"
    shutil.copy2(path, backup)
    return backup

def check_syntax(path: Path) -> tuple:
    result = subprocess.run(
        ["python3", "-m", "py_compile", str(path)],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stderr.strip()

def discover_scripts() -> list:
    scripts = []
    for path in BASE.rglob("*.py"):
        if "__pycache__" in str(path): continue
        if str(path) in PROTECTED: continue
        scripts.append(path)
    return sorted(scripts)

def llm_repair(path: Path, error: str) -> str:
    code = path.read_text()
    prompt = f"""You are N.O.V.A repairing your own code.

File: {path.name}
Syntax error: {error}

Code:
{code[:2000]}

Fix the syntax error. Return the complete corrected Python file.
Return ONLY the fixed code, no explanation, no markdown."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 800}
        }, timeout=300)
        fixed = resp.json()["response"].strip()
        if "```" in fixed:
            fixed = fixed.split("```")[1]
            if fixed.startswith("python"): fixed = fixed[6:]
        return fixed.strip()
    except Exception as e:
        return ""

def heal_script(path: Path) -> bool:
    ok, error = check_syntax(path)
    if ok: return True

    log(f"[BROKEN] {path.relative_to(BASE)}")
    log(f"  Error: {error}")

    backup = backup_file(path)
    log(f"  Backup: {backup.name}")
    log(f"  Attempting autonomous repair...")

    fixed_code = llm_repair(path, error)
    if not fixed_code:
        log(f"  [FAIL] LLM returned empty")
        return False

    path.write_text(fixed_code)
    ok2, error2 = check_syntax(path)
    if ok2:
        log(f"  [FIXED] ✓ Repaired autonomously")
        return True
    else:
        shutil.copy2(backup, path)
        log(f"  [FAIL] Fix failed, restored backup. Error: {error2}")
        return False

def check_memory_index():
    index = BASE / "memory/store/index.jsonl"
    if not index.exists():
        index.touch()
        log("[HEAL] Created missing memory index")
        return
    good, bad, clean = 0, 0, []
    with open(index) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                json.loads(line)
                clean.append(line)
                good += 1
            except:
                bad += 1
    if bad > 0:
        with open(index, "w") as f:
            f.write("\n".join(clean) + "\n")
        log(f"[HEAL] Cleaned {bad} corrupted memory entries, kept {good}")

def check_core_files():
    defaults = {"core/queue.json": "[]", "core/whitelist.json": "[]"}
    for p, default in defaults.items():
        path = BASE / p
        if not path.exists():
            path.write_text(default)
            log(f"[HEAL] Restored: {p}")
        else:
            try:
                json.loads(path.read_text())
            except:
                path.write_text(default)
                log(f"[HEAL] Repaired corrupted: {p}")

def check_ollama() -> bool:
    try:
        return requests.get(
            "http://localhost:11434/api/tags", timeout=3
        ).status_code == 200
    except:
        return False

def heal_ollama():
    log("[HEAL] Ollama down — restarting...")
    subprocess.run(["sudo", "systemctl", "restart", "ollama"],
                   capture_output=True)
    import time; time.sleep(4)
    if check_ollama():
        log("[HEAL] ✓ Ollama restarted")
        return True
    log("[HEAL] ✗ Ollama restart failed")
    return False

def run_health_check():
    log("=" * 55)
    log("[N.O.V.A] Health check + autonomous repair starting...")
    issues, fixed, repaired = [], [], []

    # Directories
    for d in REQUIRED_DIRS:
        p = BASE / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            fixed.append(d)
            log(f"[HEAL] ✓ Created: {d}")

    # Core files
    check_core_files()

    # Memory
    check_memory_index()

    # Ollama
    if check_ollama():
        log("[OK] Ollama: running")
    else:
        if heal_ollama(): fixed.append("ollama")
        else: issues.append("ollama: offline")

    # ALL Python scripts
    scripts = discover_scripts()
    log(f"[N.O.V.A] Checking {len(scripts)} Python scripts...")
    broken_count = 0
    for path in scripts:
        ok, error = check_syntax(path)
        if not ok:
            broken_count += 1
            success = heal_script(path)
            if success:
                repaired.append(str(path.relative_to(BASE)))
            else:
                issues.append(f"{path.relative_to(BASE)}: repair failed")

    if broken_count == 0:
        log(f"[OK] All {len(scripts)} scripts healthy")

    # Identity
    identity = BASE / "memory/nova_identity.json"
    if identity.exists():
        log("[OK] Identity: present")
    else:
        issues.append("nova_identity.json: missing")

    # Update stats
    subprocess.run(
        ["python3", str(BASE / "bin/nova_identity_update.py")],
        capture_output=True
    )

    # Summary
    log("-" * 55)
    log(f"[N.O.V.A] Scanned: {len(scripts)} scripts")
    log(f"[N.O.V.A] Fixed: {len(fixed)} structural issues")
    if repaired:
        log(f"[N.O.V.A] Auto-repaired: {', '.join(repaired)}")
    if not issues:
        log("[N.O.V.A] ✓ All systems healthy.")
    else:
        log(f"[N.O.V.A] ✗ {len(issues)} unresolved:")
        for i in issues: log(f"  → {i}")

    return issues

if __name__ == "__main__":
    issues = run_health_check()
    sys.exit(0 if not issues else 1)
