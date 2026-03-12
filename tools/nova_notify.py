#!/usr/bin/env python3
"""
nova_notify.py — Desktop notification layer for N.O.V.A
Uses notify-send via Plasma's notification daemon.
"""

import subprocess
import os

DISPLAY = os.environ.get("DISPLAY", ":1")


def notify(title: str, message: str, urgency: str = "normal", icon: str = "dialog-information") -> bool:
    """
    Send a desktop notification.
    urgency: low | normal | critical
    """
    try:
        env = os.environ.copy()
        env["DISPLAY"] = DISPLAY
        result = subprocess.run(
            ["notify-send", title, message, f"--urgency={urgency}", f"--icon={icon}"],
            capture_output=True, text=True, env=env, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def notify_finding(target: str, score: float, summary: str = "") -> bool:
    """Notify when autonomous scan finds something with score > 0.7."""
    title = "N.O.V.A 🎯 Finding"
    msg = f"{target} — score {score:.2f}"
    if summary:
        msg += f"\n{summary[:120]}"
    return notify(title, msg, urgency="critical", icon="dialog-warning")


def notify_task(action: str, target: str) -> bool:
    """Notify on autonomous task execution."""
    icons = {
        "scan":     "network-workgroup",
        "research": "system-search",
        "reflect":  "brain",
        "propose":  "document-edit",
        "study":    "accessories-text-editor",
    }
    icon = icons.get(action, "dialog-information")
    return notify(f"N.O.V.A 🤖 {action.capitalize()}", target, urgency="low", icon=icon)


if __name__ == "__main__":
    notify("N.O.V.A 🛸", "Notification system ready", urgency="normal")
    print("✅ test notification sent")
