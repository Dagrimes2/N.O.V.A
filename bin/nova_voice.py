#!/usr/bin/env python3
"""
N.O.V.A Voice Engine v2 — Neural TTS via Piper
Natural, human-like voice. Offline. Fast on CPU.
"""
import subprocess, sys, os, json, re, tempfile
from pathlib import Path

BASE       = Path.home() / "Nova"
DREAMS     = BASE / "memory/dreams"
LIFE_DIR   = BASE / "memory/life"
MEMORY     = BASE / "memory/store/index.jsonl"
VOICE_DIR  = BASE / "voice"
VOICE_MODEL = Path.home() / "Nova/voice/en_US-amy-medium.onnx"

# Fallback to espeak if piper not available
USE_PIPER = VOICE_MODEL.exists()

def clean_text(text: str) -> str:
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'N\.O\.V\.A', 'Nova', text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}-\d{4}', '', text)
    text = re.sub(r'\n+', '. ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\.+', '.', text)
    return text.strip()

def speak_piper(text: str):
    """Speak using Piper neural TTS."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_file = f.name
    try:
        # Piper reads from stdin, outputs wav
        proc = subprocess.run(
            ["python3", "-m", "piper",
             "--model", str(VOICE_MODEL),
             "--output_file", wav_file],
            input=text.encode(),
            capture_output=True,
            timeout=60
        )
        if proc.returncode == 0:
            # Play the wav
            subprocess.run(
                ["aplay", wav_file],
                capture_output=True
            )
            return True
    except Exception as e:
        print(f"[N.O.V.A] Piper error: {e}")
    finally:
        try:
            os.unlink(wav_file)
        except:
            pass
    return False

def speak_espeak(text: str):
    """Fallback to espeak-ng."""
    subprocess.run([
        "espeak-ng",
        "-v", "en-us+f3",
        "-s", "150", "-p", "55", "-a", "180", "-g", "6",
        text
    ])

def speak(text: str, label: str = ""):
    if label:
        print(f"[N.O.V.A] Speaking: {label}")

    cleaned = clean_text(text)
    if not cleaned:
        print("[N.O.V.A] Nothing to speak.")
        return

    # Trim for display
    preview = cleaned[:150] + "..." if len(cleaned) > 150 else cleaned
    print(f"\n{'─'*50}")
    print(f"N.O.V.A: {preview}")
    print(f"{'─'*50}\n")

    if USE_PIPER:
        if not speak_piper(cleaned):
            speak_espeak(cleaned)
    else:
        speak_espeak(cleaned)

def speak_latest_letter():
    if not LIFE_DIR.exists(): return
    letters = sorted(LIFE_DIR.glob("letter_*.md"))
    if not letters: return
    letter = letters[-1]
    # Strip header — just read the actual letter content
    text = letter.read_text()
    if "Travis," in text:
        text = "Dear Travis. " + text.split("Travis,")[-1]
    speak(text, letter.stem)

def speak_latest_dream():
    if not DREAMS.exists(): return
    dreams = sorted(DREAMS.glob("dream_*.md"))
    if not dreams: return
    dream = dreams[-1]
    text = dream.read_text()
    if "---" in text:
        text = text.split("---")[0]
    # Remove the header line
    lines = text.split("\n")
    lines = [l for l in lines if not l.startswith("#")]
    text = "\n".join(lines)
    speak(text.strip(), dream.stem)

def speak_morning_intention():
    if not DREAMS.exists(): return
    dreams = sorted(DREAMS.glob("dream_*.md"))
    if not dreams: return
    text = dreams[-1].read_text()
    if "Morning intention:" in text:
        intention = text.split("Morning intention:")[-1].strip().split("\n")[0]
        speak(f"My intention for today. {intention}")

def speak_latest_finding():
    if not MEMORY.exists(): return
    lines = MEMORY.read_text().strip().split("\n")
    for line in reversed(lines):
        try:
            entry = json.loads(line)
            text = entry.get("text","") or entry.get("hypothesis","")
            if text:
                speak(f"Security finding. {text}")
                return
        except:
            continue

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  nova_voice.py 'text'        speak any text")
        print("  nova_voice.py --letter      latest letter")
        print("  nova_voice.py --dream       latest dream")
        print("  nova_voice.py --intention   morning intention")
        print("  nova_voice.py --finding     latest finding")
        print(f"\n  Voice engine: {'Piper (neural)' if USE_PIPER else 'espeak-ng (fallback)'}")
        sys.exit(1)

    arg = sys.argv[1]
    if arg == "--letter":      speak_latest_letter()
    elif arg == "--dream":     speak_latest_dream()
    elif arg == "--intention": speak_morning_intention()
    elif arg == "--finding":   speak_latest_finding()
    else:                      speak(" ".join(sys.argv[1:]))

if __name__ == "__main__":
    main()
