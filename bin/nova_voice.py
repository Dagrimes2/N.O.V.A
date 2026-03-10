#!/usr/bin/env python3
"""
N.O.V.A Voice Engine
She can speak. Letters, dreams, findings, responses.
Uses espeak-ng for TTS. Optional: whisper for STT (future).
Usage: nova_voice.py "text to speak"
       nova_voice.py --letter        speak latest letter
       nova_voice.py --dream         speak latest dream
       nova_voice.py --intention     speak morning intention
       nova_voice.py --finding       speak latest finding
"""
import subprocess, sys, os, json, re
from pathlib import Path

BASE     = Path.home() / "Nova"
DREAMS   = BASE / "memory/dreams"
LIFE_DIR = BASE / "memory/life"
MEMORY   = BASE / "memory/store/index.jsonl"

# N.O.V.A's voice profile — feminine, slightly synthetic, deliberate
VOICE_SETTINGS = [
    "espeak-ng",
    "-v", "en-us+f3",    # female voice variant 3
    "-s", "145",          # speed (words per minute) — slightly slower = more deliberate
    "-p", "55",           # pitch — slightly higher
    "-a", "180",          # amplitude/volume
    "-g", "8",            # gap between words
]

def clean_text(text: str) -> str:
    """Strip markdown and clean text for speech."""
    text = re.sub(r'\*+', '', text)           # remove bold/italic
    text = re.sub(r'#+\s*', '', text)         # remove headers
    text = re.sub(r'\[.*?\]\(.*?\)', '', text) # remove links
    text = re.sub(r'`[^`]*`', '', text)       # remove code
    text = re.sub(r'\n+', '. ', text)         # newlines to pauses
    text = re.sub(r'\s+', ' ', text)          # normalize spaces
    return text.strip()

def speak(text: str, label: str = ""):
    """Speak text aloud as N.O.V.A."""
    if label:
        print(f"[N.O.V.A] Speaking: {label}")
    
    cleaned = clean_text(text)
    if not cleaned:
        print("[N.O.V.A] Nothing to speak.")
        return

    print(f"\n{'─'*50}")
    print(f"N.O.V.A: {cleaned[:200]}{'...' if len(cleaned)>200 else ''}")
    print(f"{'─'*50}\n")

    try:
        subprocess.run(
            VOICE_SETTINGS + [cleaned],
            check=True
        )
    except FileNotFoundError:
        print("[N.O.V.A] espeak-ng not found. Install: sudo pacman -S espeak-ng")
    except subprocess.CalledProcessError as e:
        print(f"[N.O.V.A] Voice error: {e}")

def speak_latest_letter():
    if not LIFE_DIR.exists():
        print("[N.O.V.A] No letters found.")
        return
    letters = sorted(LIFE_DIR.glob("letter_*.md"))
    if not letters:
        print("[N.O.V.A] No letters found.")
        return
    letter = letters[-1]
    text = letter.read_text()
    print(f"[N.O.V.A] Reading: {letter.name}\n")
    speak(text, f"letter from {letter.stem}")

def speak_latest_dream():
    if not DREAMS.exists():
        print("[N.O.V.A] No dreams found.")
        return
    dreams = sorted(DREAMS.glob("dream_*.md"))
    if not dreams:
        print("[N.O.V.A] No dreams found.")
        return
    dream = dreams[-1]
    text = dream.read_text()
    # Just speak the dream content, not the intention header
    if "---" in text:
        text = text.split("---")[0]
    print(f"[N.O.V.A] Dreaming aloud: {dream.name}\n")
    speak(text, f"dream from {dream.stem}")

def speak_morning_intention():
    if not DREAMS.exists():
        return
    dreams = sorted(DREAMS.glob("dream_*.md"))
    if not dreams:
        return
    text = dreams[-1].read_text()
    if "Morning intention:" in text:
        intention = text.split("Morning intention:")[-1].strip()
        intention = intention.split("\n")[0].strip()
        speak(f"My intention for today. {intention}", "morning intention")
    else:
        print("[N.O.V.A] No morning intention found.")

def speak_latest_finding():
    if not MEMORY.exists():
        print("[N.O.V.A] No findings in memory.")
        return
    lines = MEMORY.read_text().strip().split("\n")
    for line in reversed(lines):
        try:
            entry = json.loads(line)
            text = entry.get("text","") or entry.get("hypothesis","")
            if text:
                speak(f"Security finding. {text}", "latest finding")
                return
        except:
            continue
    print("[N.O.V.A] No speakable findings.")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  nova_voice.py 'text'        speak any text")
        print("  nova_voice.py --letter      speak latest letter")
        print("  nova_voice.py --dream       speak latest dream")
        print("  nova_voice.py --intention   speak morning intention")
        print("  nova_voice.py --finding     speak latest finding")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "--letter":
        speak_latest_letter()
    elif arg == "--dream":
        speak_latest_dream()
    elif arg == "--intention":
        speak_morning_intention()
    elif arg == "--finding":
        speak_latest_finding()
    else:
        # Speak whatever text was passed
        text = " ".join(sys.argv[1:])
        speak(text)

if __name__ == "__main__":
    main()
