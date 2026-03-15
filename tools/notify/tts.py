#!/usr/bin/env python3
"""
N.O.V.A Text-to-Speech

Speaks using espeak-ng (available on Athena OS / Arch).
Falls back silently if espeak-ng is not installed.

Usage:
    from tools.notify.tts import speak
    speak("Nova found something interesting on gitlab.com")

    nova speak "your message"
"""
import subprocess
import sys


VOICE    = "en"          # espeak-ng voice (en, en-us, en-gb, etc.)
SPEED    = 160           # words per minute (default 175)
PITCH    = 45            # 0-99 (default 50 — slightly lower = calmer)
VOLUME   = 100           # 0-200


def is_available() -> bool:
    try:
        result = subprocess.run(
            ["which", "espeak-ng"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def speak(text: str, async_: bool = True) -> bool:
    """
    Speak text via espeak-ng.
    async_=True returns immediately (fire-and-forget).
    Returns True if espeak-ng was found and launched.
    """
    if not text or not text.strip():
        return False

    # Sanitize — strip markdown and excessive whitespace
    clean = text.replace("*", "").replace("#", "").replace("`", "")
    clean = " ".join(clean.split())
    clean = clean[:500]  # don't read a novel

    cmd = [
        "espeak-ng",
        "-v", VOICE,
        "-s", str(SPEED),
        "-p", str(PITCH),
        "-a", str(VOLUME),
        clean,
    ]

    try:
        if async_:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        return True
    except FileNotFoundError:
        # espeak-ng not installed — silent fallback
        return False
    except Exception:
        return False


def speak_finding(host: str, score: float, summary: str = "") -> bool:
    """Speak a security finding alert."""
    severity = "critical" if score >= 9 else "high priority" if score >= 7 else "medium"
    text = f"Nova alert. {severity} finding on {host}. Score {score:.0f} out of ten."
    if summary:
        text += f" {summary[:100]}"
    return speak(text, async_=True)


def speak_intention(intention: str) -> bool:
    """Speak Nova's morning intention."""
    return speak(intention, async_=True)


def save_audio(text: str, path) -> bool:
    """
    Save TTS to an audio file instead of playing it.
    Uses espeak-ng -w flag.
    """
    import subprocess
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sanitise (same as speak())
    clean = text.replace('"', "'").replace('\n', ' ').replace('\\', '')[:500]

    try:
        result = subprocess.run(
            ["espeak-ng", "-w", str(path), clean],
            capture_output=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def morning_digest_speak(digest_text: str) -> bool:
    """
    Speak a brief version of the morning digest aloud.
    Trims to first 280 chars — only the highlights.
    """
    # Extract just the actionable lines (skip decorative headers)
    lines = [l.strip() for l in digest_text.splitlines()
             if l.strip() and not l.startswith("─") and not l.startswith("═")
             and not l.startswith("N.O.V.A")]
    brief = " ".join(lines[:6])[:280]

    if not brief:
        return False

    intro = "Good morning Travis. Nova's brief for today: "
    return speak(intro + brief)


def main():
    if not is_available():
        print("[tts] espeak-ng not found. Install with: sudo pacman -S espeak-ng")
        sys.exit(1)

    args = sys.argv[1:]

    if "--save" in args:
        idx = args.index("--save")
        save_path = args[idx + 1] if idx + 1 < len(args) else "nova_speech.wav"
        text_args = [a for i, a in enumerate(args) if i != idx and i != idx + 1]
        text = " ".join(text_args)
        if text:
            ok = save_audio(text, save_path)
            print(f"Saved to {save_path}" if ok else "Failed to save audio")
        sys.exit(0)

    text = " ".join(args) if args else "N.O.V.A is online."
    ok   = speak(text, async_=False)
    if ok:
        print(f"[tts] Spoke: {text[:60]}")
    else:
        print("[tts] Failed.")


if __name__ == "__main__":
    main()
