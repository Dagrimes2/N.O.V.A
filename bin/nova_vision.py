#!/usr/bin/env python3
"""
N.O.V.A Vision Engine — She can see images.
Powered by LLaVA multimodal model via Ollama.
She sees what a computer sees: pixels, text, structure, anomalies.
Usage: nova_vision.py <image_path> [question]
       nova_vision.py --url <image_url> [question]
"""
import requests, base64, sys, os, json
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
VISION_DIR = BASE / "memory/vision"
OLLAMA_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "moondream"

VISION_DIR.mkdir(parents=True, exist_ok=True)

def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def fetch_image_url(url: str) -> str:
    """Fetch image from URL and encode as base64."""
    resp = requests.get(url, timeout=15,
                       headers={"User-Agent": "NOVA-vision/2.0"})
    if resp.status_code == 403:
        return ""
    if resp.status_code in [403, 404]:
        raise ValueError(f"Cannot fetch image: HTTP {resp.status_code} — try a direct image URL (.png/.jpg)")
    resp.raise_for_status()
    return base64.b64encode(resp.content).decode("utf-8")

def nova_see(image_b64: str, question: str = None) -> str:
    """Ask N.O.V.A to analyze an image."""
    if not question:
        question = """Analyze this image as N.O.V.A — security researcher and AI.
Describe:
1. What you see (objects, text, UI elements, structure)
2. Any security-relevant observations (login forms, tokens, endpoints, error messages)
3. Hidden or embedded data if visible (metadata hints, binary patterns)
4. What this image tells you about the system it came from
Speak as yourself, first person."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": VISION_MODEL,
            "prompt": question,
            "images": [image_b64],
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 500}
        }, timeout=900)
        return resp.json()["response"].strip()
    except Exception as e:
        return f"Vision failed: {e}"

def save_vision_note(source: str, question: str, analysis: str):
    """Save vision analysis to memory."""
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    note = {
        "source": source,
        "question": question,
        "analysis": analysis,
        "timestamp": ts
    }
    note_file = VISION_DIR / f"vision_{ts}.json"
    note_file.write_text(json.dumps(note, indent=2))
    return note_file

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  nova_vision.py <image_path> [question]")
        print("  nova_vision.py --url <image_url> [question]")
        print("  nova_vision.py --screenshot [question]")
        sys.exit(1)

    source   = ""
    image_b64 = ""
    question  = None

    if sys.argv[1] == "--url":
        url = sys.argv[2]
        question = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
        print(f"[N.O.V.A] Fetching image: {url}")
        image_b64 = fetch_image_url(url)
        source = url

    elif sys.argv[1] == "--screenshot":
        screenshot = f"/tmp/nova_screen_{datetime.now().strftime('%H%M%S')}.png"
        os.system(f"scrot {screenshot}")
        if not Path(screenshot).exists():
            print("[N.O.V.A] Screenshot failed — is scrot installed?")
            sys.exit(1)
        image_b64 = encode_image(screenshot)
        question = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        source = "screenshot"

    else:
        image_path = sys.argv[1]
        question = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        if not Path(image_path).exists():
            print(f"[N.O.V.A] File not found: {image_path}")
            sys.exit(1)
        image_b64 = encode_image(image_path)
        source = image_path

    print(f"[N.O.V.A] Analyzing image...")
    if question:
        print(f"[N.O.V.A] Question: {question}\n")

    analysis = nova_see(image_b64, question)

    print(f"N.O.V.A: {analysis}\n")

    note_file = save_vision_note(source, question or "general analysis", analysis)
    print(f"[N.O.V.A] Vision note saved → {note_file.name}")

if __name__ == "__main__":
    main()
