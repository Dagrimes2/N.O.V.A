#!/usr/bin/env python3
"""
nova_docker.py — Sandbox execution layer for N.O.V.A
Runs scan commands inside nova-sandbox container instead of host.
"""

import subprocess
import shlex
import json
from datetime import datetime, timezone

CONTAINER = "nova-sandbox"
TIMEOUT = 120  # seconds


def container_running() -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "true"


def ensure_running() -> bool:
    if container_running():
        return True
    # Try to start it if stopped
    result = subprocess.run(["docker", "start", CONTAINER], capture_output=True, text=True)
    return result.returncode == 0


def exec_in_sandbox(command: str, timeout: int = TIMEOUT) -> dict:
    """
    Execute a shell command inside nova-sandbox.
    Returns dict with stdout, stderr, returncode, duration.
    """
    if not ensure_running():
        return {
            "success": False,
            "error": f"Container '{CONTAINER}' is not running and could not be started.",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "command": command,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    start = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            ["docker", "exec", CONTAINER, "bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "command": command,
            "duration_sec": round(duration, 2),
            "timestamp": start.isoformat()
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Command timed out after {timeout}s",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "command": command,
            "timestamp": start.isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "command": command,
            "timestamp": start.isoformat()
        }


def scan_target(target: str, mode: str = "basic") -> dict:
    """
    High-level scan interface Nova calls directly.
    mode: basic | full | web | dns
    """
    commands = {
        "basic": f"nmap -T4 -F --open {shlex.quote(target)} 2>/dev/null",
        "full":  f"nmap -T4 -sV --open -p 80,443,8080,8443,8888,3000,9200,6379,27017 {shlex.quote(target)} 2>/dev/null",
        "web":   f"whatweb -a 3 {shlex.quote(target)} 2>/dev/null",
        "dns":   f"dig +short {shlex.quote(target)} && whois {shlex.quote(target)} 2>/dev/null | head -40",
    }
    cmd = commands.get(mode, commands["basic"])
    return exec_in_sandbox(cmd)


if __name__ == "__main__":
    # Quick self-test
    print(f"Container running: {container_running()}")
    print("Running test scan on example.com (dns mode)...")
    result = scan_target("example.com", mode="dns")
    print(json.dumps(result, indent=2))
