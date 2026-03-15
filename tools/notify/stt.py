#!/usr/bin/env python3
"""
N.O.V.A Speech-to-Text

Listens via microphone and transcribes speech to text.
Used for voice conversations with Travis.

Backends (tried in order):
  1. whisper CLI (pip install openai-whisper OR whisper.cpp)
  2. whisper Python API (import whisper)
  3. vosk (if installed)
  4. Record only (save .wav, manual transcription)

Recording: uses sox (rec command) or arecord — both standard on Linux.
Duration: records until silence detected OR max_seconds reached.

Usage:
  from tools.notify.stt import listen
  text = listen()           # record until silence, transcribe
  text = listen(seconds=5)  # record exactly 5 seconds

  nova listen               # one-shot listen and print
  nova listen --loop        # continuous conversation mode
"""
import json
import os
import subprocess
import sys
import tempfile
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
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 180

# Default max recording duration in silence-detection mode
MAX_SECONDS = 30
# Whisper model — tiny is fastest, acceptable accuracy
WHISPER_MODEL = "tiny"


# ── Backend detection ─────────────────────────────────────────────────────────

def is_available() -> bool:
    """Check if any STT backend is available."""
    recorder = _find_recorder()
    if recorder is None:
        return False  # Can't record at all
    # At least one transcription path must exist
    if _has_whisper_cli():
        return True
    if _has_whisper_api():
        return True
    if _has_vosk():
        return True
    # Record-only mode is still "available" in the sense that we can capture
    return True


def _cmd_exists(cmd: str) -> bool:
    """Return True if a shell command exists on PATH."""
    try:
        result = subprocess.run(
            ["which", cmd],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _find_recorder() -> str | None:
    """Return 'sox', 'arecord', or None."""
    if _cmd_exists("rec"):
        return "sox"
    if _cmd_exists("arecord"):
        return "arecord"
    return None


def _has_whisper_cli() -> bool:
    return _cmd_exists("whisper")


def _has_whisper_api() -> bool:
    try:
        import whisper  # noqa
        return True
    except ImportError:
        return False


def _has_vosk() -> bool:
    try:
        import vosk  # noqa
        return True
    except ImportError:
        return False


# ── Recording ─────────────────────────────────────────────────────────────────

def _record_audio(output_path: str, max_seconds: int = MAX_SECONDS) -> bool:
    """
    Record from mic to output_path (WAV).
    Uses sox: rec -r 16000 -c 1 output.wav silence 1 0.1 3% 1 2.0 3%
    (records until 2s of silence, max max_seconds)
    Falls back to arecord: arecord -r 16000 -c 1 -f S16_LE -d max_seconds output.wav
    Returns True if recording succeeded.
    """
    recorder = _find_recorder()
    if recorder is None:
        print("[stt] No recorder found. Install sox (pacman -S sox) or alsa-utils.")
        return False

    try:
        if recorder == "sox":
            cmd = [
                "rec",
                "-r", "16000",
                "-c", "1",
                "-b", "16",
                output_path,
                "silence", "1", "0.1", "3%", "1", "2.0", "3%",
                "trim", "0", str(max_seconds),
            ]
        else:  # arecord
            cmd = [
                "arecord",
                "-r", "16000",
                "-c", "1",
                "-f", "S16_LE",
                "-d", str(max_seconds),
                output_path,
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=max_seconds + 10,
        )
        if not Path(output_path).exists():
            return False
        if Path(output_path).stat().st_size < 100:
            return False
        return True
    except subprocess.TimeoutExpired:
        # Timed out — file may still be usable
        return Path(output_path).exists() and Path(output_path).stat().st_size > 100
    except Exception as e:
        print(f"[stt] Recording error: {e}")
        return False


# ── Transcription backends ────────────────────────────────────────────────────

def _transcribe_whisper_cli(wav_path: str) -> str:
    """Run whisper CLI: whisper wav_path --model tiny --output_format txt"""
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    "whisper",
                    wav_path,
                    "--model", WHISPER_MODEL,
                    "--output_format", "txt",
                    "--output_dir", tmp_dir,
                    "--language", "en",
                    "--fp16", "False",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            # whisper writes <basename>.txt
            base = Path(wav_path).stem
            txt_file = Path(tmp_dir) / f"{base}.txt"
            if txt_file.exists():
                return txt_file.read_text().strip()
            # Fallback: parse stdout
            output = result.stdout.strip()
            # Strip timestamp lines like [00:00.000 --> 00:05.000]
            lines = []
            for line in output.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("[") and "-->" not in stripped:
                    lines.append(stripped)
            return " ".join(lines).strip()
    except subprocess.TimeoutExpired:
        print("[stt] whisper CLI timed out")
        return ""
    except Exception as e:
        print(f"[stt] whisper CLI error: {e}")
        return ""


def _transcribe_whisper_api(wav_path: str) -> str:
    """Use whisper Python API if importable."""
    try:
        import whisper  # type: ignore
        model = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(wav_path, language="en", fp16=False)
        return result.get("text", "").strip()
    except Exception as e:
        print(f"[stt] whisper API error: {e}")
        return ""


def _transcribe_vosk(wav_path: str) -> str:
    """Use vosk if installed."""
    try:
        import vosk  # type: ignore
        import wave

        # Try to find a vosk model in common locations
        model_paths = [
            Path.home() / "vosk-model-small-en-us",
            Path.home() / "vosk-model-en-us",
            Path("/usr/share/vosk/model"),
            Path("/opt/vosk/model"),
        ]
        model_path = None
        for p in model_paths:
            if p.exists():
                model_path = str(p)
                break

        if model_path is None:
            print("[stt] vosk: no model found in ~/vosk-model-small-en-us")
            return ""

        model = vosk.Model(model_path)
        with wave.open(wav_path, "rb") as wf:
            rec = vosk.KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)
            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    r = json.loads(rec.Result())
                    results.append(r.get("text", ""))
            final = json.loads(rec.FinalResult())
            results.append(final.get("text", ""))
        return " ".join(r for r in results if r).strip()
    except Exception as e:
        print(f"[stt] vosk error: {e}")
        return ""


def _transcribe(wav_path: str, language: str = "en") -> str:
    """
    Try transcription backends in order: whisper CLI, whisper API, vosk.
    Returns transcribed text or empty string.
    """
    if _has_whisper_cli():
        text = _transcribe_whisper_cli(wav_path)
        if text:
            return text

    if _has_whisper_api():
        text = _transcribe_whisper_api(wav_path)
        if text:
            return text

    if _has_vosk():
        text = _transcribe_vosk(wav_path)
        if text:
            return text

    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def listen(seconds: int = None, language: str = "en") -> str:
    """
    Record audio and transcribe.
    seconds=None: record until silence (max 30s)
    seconds=N: record exactly N seconds
    Returns transcribed text or "" on failure.
    Cleans up temp WAV file.
    """
    max_sec = seconds if seconds is not None else MAX_SECONDS

    # Write to /tmp/nova_stt_<pid>.wav
    wav_path = f"/tmp/nova_stt_{os.getpid()}.wav"

    try:
        recorder = _find_recorder()
        if recorder is None:
            print("[stt] No audio recorder available. Install: sudo pacman -S sox")
            return ""

        # If fixed duration requested, skip silence detection for sox
        if seconds is not None and recorder == "sox":
            cmd = [
                "rec",
                "-r", "16000",
                "-c", "1",
                "-b", "16",
                wav_path,
                "trim", "0", str(seconds),
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=seconds + 5)
            except Exception as e:
                print(f"[stt] Recording error: {e}")
                return ""
        else:
            ok = _record_audio(wav_path, max_seconds=max_sec)
            if not ok:
                print("[stt] Recording failed or produced no audio")
                return ""

        # Check file exists and has content
        p = Path(wav_path)
        if not p.exists() or p.stat().st_size < 100:
            print("[stt] No audio captured")
            return ""

        text = _transcribe(wav_path, language=language)
        return text

    finally:
        # Always clean up
        try:
            Path(wav_path).unlink(missing_ok=True)
        except Exception:
            pass


def listen_and_respond(callback) -> None:
    """
    Record, transcribe, call callback(text), speak response.
    callback should return a string (Nova's response).
    """
    print("[stt] Listening...")
    text = listen()
    if not text:
        print("[stt] Nothing heard or transcription failed.")
        return

    print(f"[stt] Heard: {text}")
    response = callback(text)
    if response:
        try:
            from tools.notify.tts import speak
            speak(str(response), async_=False)
        except Exception:
            pass
        print(f"[stt] Response: {response}")


# ── Status / CLI ──────────────────────────────────────────────────────────────

def status() -> None:
    """Show which backends are available."""
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"
    B = "\033[1m"; DIM = "\033[2m"; NC = "\033[0m"

    print(f"\n{B}N.O.V.A Speech-to-Text Status{NC}\n")

    recorder = _find_recorder()
    rec_str = recorder if recorder else "none"
    rec_col = G if recorder else R
    print(f"  Recorder:      {rec_col}{rec_str}{NC}")

    w_cli = _has_whisper_cli()
    print(f"  whisper CLI:   {(G+'yes') if w_cli else (R+'no')}{NC}")

    w_api = _has_whisper_api()
    print(f"  whisper API:   {(G+'yes') if w_api else (R+'no')}{NC}")

    vsk = _has_vosk()
    print(f"  vosk:          {(G+'yes') if vsk else (R+'no')}{NC}")

    overall = recorder is not None
    avail_str = "available" if overall else "unavailable"
    avail_col = G if overall else R
    print(f"\n  STT:           {avail_col}{avail_str}{NC}")

    if not w_cli and not w_api and not vsk:
        print(f"\n  {DIM}Install whisper: pip install openai-whisper{NC}")
        print(f"  {DIM}   or whisper.cpp: https://github.com/ggerganov/whisper.cpp{NC}")
    if not recorder:
        print(f"\n  {DIM}Install recorder: sudo pacman -S sox{NC}")
    print()


def main():
    args = sys.argv[1:]

    cmd = args[0] if args else "listen"

    if cmd == "status":
        status()
        return

    # Parse flags
    loop_mode   = "--loop" in args
    fixed_secs  = None
    if "--seconds" in args:
        idx = args.index("--seconds")
        if idx + 1 < len(args):
            try:
                fixed_secs = int(args[idx + 1])
            except ValueError:
                pass

    if cmd == "listen" or (cmd not in ("status",)):
        if loop_mode:
            print("[stt] Continuous loop mode. Ctrl-C to stop.\n")
            try:
                while True:
                    print("[stt] Listening...")
                    text = listen(seconds=fixed_secs)
                    if text:
                        print(f"[stt] Transcribed: {text}\n")
                    else:
                        print("[stt] (nothing)\n")
            except KeyboardInterrupt:
                print("\n[stt] Loop stopped.")
        else:
            print("[stt] Listening...")
            text = listen(seconds=fixed_secs)
            if text:
                print(f"\n{text}")
            else:
                print("[stt] Nothing transcribed.")


if __name__ == "__main__":
    main()
