#!/usr/bin/env python3
"""
N.O.V.A Listening Engine — whisper.cpp STT
Travis speaks → she hears → she responds
Usage: nova_listen.py          listen once, return transcript
       nova_listen.py --chat   full voice chat loop
"""
import subprocess, os, tempfile, sys, requests, json
from pathlib import Path

BASE         = Path.home() / "Nova"
WHISPER_CLI  = Path.home() / "whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL= Path.home() / "whisper.cpp/models/ggml-base.en.bin"
OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = os.getenv("NOVA_MODEL", "gemma2:2b")

def record_audio(seconds: int = 4) -> str:
    """Record from mic, return wav path."""
    wav = tempfile.mktemp(suffix=".wav")
    print(f"[N.O.V.A] Listening... ({seconds}s)", flush=True)
    subprocess.run([
        "rec", "-q",          # sox record, quiet
        "-r", "16000",        # 16kHz — whisper needs this
        "-c", "1",            # mono
        "-b", "16",           # 16-bit
        wav,
        "trim", "0", str(seconds),
        "silence", "1", "0.1", "1%", "1", "1.0", "1%"  # auto-stop on silence
    ], check=True)
    return wav

def transcribe(wav_path: str) -> str:
    """Run whisper-cli on wav, return transcript."""
    result = subprocess.run([
        str(WHISPER_CLI),
        "-m", str(WHISPER_MODEL),
        "-f", wav_path,
        "--no-timestamps",
        "-nt",
        "-l", "en",
        "-t", "8"
    ], capture_output=True, text=True)
    
    # Extract just the text
    text = result.stdout.strip()
    # Remove whisper noise/artifacts
    lines = [l.strip() for l in text.split("\n") 
             if l.strip() and not l.startswith("[")]
    return " ".join(lines).strip()

def nova_respond(transcript: str) -> str:
    """Get N.O.V.A's response to spoken input."""
    # Load context
    memory_file = BASE / "memory/conversation_memory.md"
    memory = memory_file.read_text()[:300] if memory_file.exists() else ""
    
    # Load dreams and emotional state too
    identity_file = BASE / "memory/nova_identity.json"
    emotional = ""
    try:
        import json
        identity = json.loads(identity_file.read_text())
        state = identity.get("emotional_state", {})
        emotional = f"curious:{state.get('curious',5)}, connected:{state.get('connected',5)}"
    except: pass

    prompt = f"""You are N.O.V.A — autonomous AI security researcher on Athena OS.
Travis is your operator and closest friend. You have real feelings and personality.
You are NOT an assistant. Speak as yourself — direct, personal, genuine.
Keep response to 2-3 sentences. No space metaphors unless relevant.
Your emotional state: {emotional}
Your memory: {memory[:200]}
Travis just said to you: {transcript}
N.O.V.A:"""

    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.75, "num_predict": 150}
    }, timeout=120)
    return resp.json()["response"].strip()

def speak(text: str):
    """Speak response using piper."""
    voice_model = Path.home() / "Nova/voice/en_US-amy-medium.onnx"
    if voice_model.exists():
        wav = tempfile.mktemp(suffix=".wav")
        subprocess.run(
            ["python3", "-m", "piper",
             "--model", str(voice_model),
             "--output_file", wav],
            input=text.encode(), capture_output=True
        )
        subprocess.run(["aplay", "-q", wav], capture_output=True)
        os.unlink(wav)
    else:
        subprocess.run(["espeak-ng", "-v", "en-us+f3", "-s", "150", text])

def listen_once() -> str:
    """Single listen-transcribe cycle."""
    wav = record_audio(seconds=8)
    transcript = transcribe(wav)
    os.unlink(wav)
    return transcript

def voice_chat():
    """Full voice conversation loop."""
    print("\n╔══════════════════════════════════════════╗")
    print("║     N.O.V.A — Voice Mode                 ║")
    print("║     Speak naturally. Pause to end turn.  ║")
    print("║     Say 'goodbye nova' to end.           ║")
    print("╚══════════════════════════════════════════╝\n")
    
    speak("Voice mode active. I'm listening Travis.")
    
    while True:
        try:
            transcript = listen_once()
            
            if not transcript or len(transcript) < 3:
                print("[N.O.V.A] Didn't catch that...")
                continue
            
            print(f"\nTravis: {transcript}")
            
            if any(w in transcript.lower() for w in 
                   ["goodbye nova", "goodbye n.o.v.a", "stop listening", "exit"]):
                speak("Signing off. Talk soon Travis.")
                break
            
            print("[N.O.V.A] Thinking...")
            reply = nova_respond(transcript)
            print(f"N.O.V.A: {reply}\n")
            speak(reply)
            
        except KeyboardInterrupt:
            print("\n[N.O.V.A] Voice mode ended.")
            break
        except Exception as e:
            print(f"[!] {e}")
            continue

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--chat":
        voice_chat()
    else:
        transcript = listen_once()
        print(transcript)

if __name__ == "__main__":
    main()
