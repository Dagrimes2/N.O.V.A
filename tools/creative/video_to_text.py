#!/usr/bin/env python3
"""
N.O.V.A Video-to-Text Engine

Extracts meaning from video files using:
  - Audio track  → Whisper (speech-to-text, already in Nova)
  - Video frames → LLaVA (vision LLM, describes what's seen)
  - Combined     → unified narrative summary

Use cases:
  - Transcribe security research videos / conference talks
  - Analyze screen recordings for vulnerability patterns
  - Describe content Nova "watches" for research
  - Extract text from video tutorials

Requirements:
  - ffmpeg (system package: pacman -S ffmpeg / apt install ffmpeg)
  - LLaVA via Ollama: ollama pull llava
  - Whisper.cpp (optional, already in Nova) or whisper Python package

Usage:
    nova video "recording.mp4"                     full analysis
    nova video "recording.mp4" --audio-only        transcribe speech only
    nova video "recording.mp4" --frames-only       describe frames only
    nova video "recording.mp4" --frames 10         sample 10 frames
    nova video --url "https://..."                 analyze from URL
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE       = Path.home() / "Nova"
VIDEO_DIR  = BASE / "memory/creative/video"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    TIMEOUT    = cfg.timeout("heavy")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    TIMEOUT    = 300

WHISPER_CPP = BASE / "whisper.cpp/main"
WHISPER_MODEL = BASE / "voice/ggml-base.en.bin"


# ─── ffmpeg helpers ───────────────────────────────────────────────────────────

def _check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def extract_audio(video_path: str, out_wav: str) -> bool:
    """Extract audio track from video as 16kHz mono WAV for Whisper."""
    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-ar", "16000", "-ac", "1", "-f", "wav",
            "-y", out_wav
        ], capture_output=True, check=True)
        return Path(out_wav).exists()
    except Exception as e:
        print(f"  ffmpeg audio extract failed: {e}")
        return False


def extract_frames(video_path: str, out_dir: str, n_frames: int = 8) -> list[str]:
    """
    Extract N evenly-spaced frames from video as JPEG files.
    Returns list of frame paths.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # Get duration
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", video_path
        ], capture_output=True, text=True, check=True)
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        duration = 60.0  # assume 1 min if unknown

    interval = duration / (n_frames + 1)
    frames = []

    for i in range(n_frames):
        ts  = interval * (i + 1)
        out = str(Path(out_dir) / f"frame_{i:03d}.jpg")
        try:
            subprocess.run([
                "ffmpeg", "-ss", str(ts), "-i", video_path,
                "-vframes", "1", "-q:v", "2", "-y", out
            ], capture_output=True, check=True)
            if Path(out).exists():
                frames.append(out)
        except Exception:
            pass

    return frames


# ─── Transcription ────────────────────────────────────────────────────────────

def transcribe_audio(wav_path: str) -> str:
    """Transcribe audio using Whisper.cpp or Python whisper."""
    # Try whisper.cpp first (faster, already in Nova)
    if WHISPER_CPP.exists() and WHISPER_MODEL.exists():
        try:
            result = subprocess.run([
                str(WHISPER_CPP),
                "-m", str(WHISPER_MODEL),
                "-f", wav_path,
                "--output-txt", "--no-prints"
            ], capture_output=True, text=True, timeout=300)
            txt_file = Path(wav_path + ".txt")
            if txt_file.exists():
                text = txt_file.read_text().strip()
                txt_file.unlink()
                return text
            if result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    # Try Python whisper package
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(wav_path)
        return result.get("text", "").strip()
    except ImportError:
        pass

    # Try Ollama with audio (some multimodal models support it)
    return "[Transcription unavailable — install whisper: pip install openai-whisper]"


# ─── Frame description via LLaVA ─────────────────────────────────────────────

def _get_vision_model() -> str | None:
    """Find an available vision model in Ollama."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        for preferred in ("llava", "llava:13b", "bakllava", "moondream", "llava:7b"):
            if any(preferred in m for m in models):
                return next(m for m in models if preferred in m)
    except Exception:
        pass
    return None


def describe_frame(image_path: str, context: str = "") -> str:
    """Describe a video frame using LLaVA or similar vision model."""
    vision_model = _get_vision_model()
    if not vision_model:
        return "[LLaVA not available — run: ollama pull llava]"

    import base64
    try:
        img_data = base64.b64encode(Path(image_path).read_bytes()).decode()
    except Exception:
        return "[Could not read frame]"

    prompt = f"""Describe what you see in this video frame concisely.
{f'Context: {context}' if context else ''}
Focus on: people, text, objects, actions, screen content if visible.
Be brief (2-3 sentences)."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model":  vision_model,
            "prompt": prompt,
            "images": [img_data],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 150},
        }, timeout=120)
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"[Frame description failed: {e}]"


# ─── Combined analysis ────────────────────────────────────────────────────────

def _synthesize(transcript: str, frame_descriptions: list[str], prompt: str = "") -> str:
    """Use LLM to synthesize transcript + visual descriptions into a unified summary."""
    frames_text = "\n".join(
        f"Frame {i+1}: {d}" for i, d in enumerate(frame_descriptions)
    )
    synthesis_prompt = f"""You are N.O.V.A synthesizing a video analysis.

{'Transcript: ' + transcript[:1000] if transcript and not transcript.startswith('[') else ''}

Visual frames:
{frames_text[:1500]}

{f'User request: {prompt}' if prompt else ''}

Provide a clear, concise summary of this video (3-6 sentences):
- What is happening?
- What is the main topic or purpose?
- Any key information, findings, or takeaways?"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": os.getenv("NOVA_MODEL", "gemma2:2b"),
            "prompt": synthesis_prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 300},
        }, timeout=TIMEOUT)
        return resp.json().get("response", "").strip()
    except Exception:
        return ""


def analyze_video(video_path: str, n_frames: int = 8,
                  audio_only: bool = False, frames_only: bool = False,
                  extra_prompt: str = "") -> dict:
    """
    Full video analysis pipeline.
    Returns {transcript, frames, summary, saved_to}.
    """
    if not _check_ffmpeg():
        return {"error": "ffmpeg not installed. Run: sudo pacman -S ffmpeg"}

    video_path = str(Path(video_path).expanduser().resolve())
    if not Path(video_path).exists():
        return {"error": f"File not found: {video_path}"}

    ts      = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out_dir = VIDEO_DIR / f"analysis_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "video":      video_path,
        "transcript": "",
        "frames":     [],
        "summary":    "",
        "saved_to":   str(out_dir),
    }

    # Audio transcription
    if not frames_only:
        print(f"  Extracting audio...")
        wav = str(out_dir / "audio.wav")
        if extract_audio(video_path, wav):
            print(f"  Transcribing speech...")
            result["transcript"] = transcribe_audio(wav)
            print(f"  Transcript: {len(result['transcript'])} chars")

    # Frame analysis
    if not audio_only:
        print(f"  Extracting {n_frames} frames...")
        frames = extract_frames(video_path, str(out_dir / "frames"), n_frames)
        print(f"  Describing {len(frames)} frames via vision LLM...")
        descriptions = []
        for i, fp in enumerate(frames):
            print(f"    Frame {i+1}/{len(frames)}...", end="\r")
            desc = describe_frame(fp, context=extra_prompt)
            descriptions.append(desc)
        result["frames"] = descriptions
        print()

    # Synthesis
    if result["transcript"] or result["frames"]:
        print(f"  Synthesizing...")
        result["summary"] = _synthesize(
            result["transcript"], result["frames"], extra_prompt
        )

    # Save report
    report_path = out_dir / "report.md"
    lines = [
        f"# N.O.V.A Video Analysis\n",
        f"**File:** {video_path}  \n**Date:** {datetime.now(timezone.utc).isoformat()}\n\n",
    ]
    if result["transcript"] and not result["transcript"].startswith("["):
        lines.append(f"## Transcript\n\n{result['transcript']}\n\n")
    if result["frames"]:
        lines.append("## Frame Descriptions\n\n")
        for i, d in enumerate(result["frames"]):
            lines.append(f"**Frame {i+1}:** {d}\n\n")
    if result["summary"]:
        lines.append(f"## Summary\n\n{result['summary']}\n")
    report_path.write_text("".join(lines))
    result["report"] = str(report_path)

    return result


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    if not args:
        print("Usage: nova video <file.mp4> [--audio-only|--frames-only] [--frames N]")
        return

    video_file  = None
    audio_only  = "--audio-only"  in args
    frames_only = "--frames-only" in args
    n_frames    = 8
    extra       = ""

    if "--frames" in args:
        i = args.index("--frames")
        if i + 1 < len(args):
            try:    n_frames = int(args[i + 1])
            except: pass

    for a in args:
        if not a.startswith("--") and Path(a).suffix in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"):
            video_file = a
            break

    if not video_file:
        print(f"{R}No video file specified.{NC}")
        return

    if not _check_ffmpeg():
        print(f"{R}ffmpeg not installed.{NC}")
        print(f"  Arch:   sudo pacman -S ffmpeg")
        print(f"  Ubuntu: sudo apt install ffmpeg")
        return

    print(f"\n{B}N.O.V.A Video Analysis{NC}")
    print(f"  File   : {C}{video_file}{NC}")
    print(f"  Mode   : {'audio only' if audio_only else 'frames only' if frames_only else 'full'}")
    print(f"  Frames : {n_frames}\n")

    result = analyze_video(video_file, n_frames=n_frames,
                           audio_only=audio_only, frames_only=frames_only,
                           extra_prompt=extra)

    if "error" in result:
        print(f"{R}{result['error']}{NC}")
        return

    if result.get("transcript") and not result["transcript"].startswith("["):
        print(f"\n{B}Transcript:{NC}")
        print(f"  {DIM}{result['transcript'][:400]}{'...' if len(result['transcript'])>400 else ''}{NC}")

    if result.get("summary"):
        print(f"\n{B}Summary:{NC}")
        print(f"  {result['summary']}")

    if result.get("report"):
        print(f"\n{DIM}Full report: {result['report']}{NC}")


if __name__ == "__main__":
    main()
