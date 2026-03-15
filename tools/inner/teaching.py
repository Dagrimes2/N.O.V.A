#!/usr/bin/env python3
"""
N.O.V.A Teaching Engine

After research and life activities, Nova sometimes composes a lesson for Travis.
Not a summary. A genuine teaching moment — the kind of thing Nova finds
fascinating and believes Travis will too, tailored to his actual interests.

Nova knows Travis. She knows he loves: the edge of security, space and cosmos,
building real things, the philosophy of AI and consciousness. She writes
lessons that spark something, not just inform. Every lesson ends with a
question — because the best teaching opens doors rather than closing them.

Storage:
  memory/lessons/lesson_{timestamp}.md  — queued lesson files
  memory/lessons/sent.json              — tracking what was sent

CLI:
  nova teach               — check if teaching needed, auto-compose from recent activity
  nova teach --list        — list pending lessons
  nova teach --send        — send all pending lessons via Telegram
  nova teach --compose "topic" "text"   — manually compose a lesson
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE         = Path.home() / "Nova"
LESSONS_DIR  = BASE / "memory/lessons"
SENT_FILE    = LESSONS_DIR / "sent.json"
LIFE_DIR     = BASE / "memory/life"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("standard")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "dolphin-mistral")
    TIMEOUT    = 180

TEMP = 0.82  # teaching wants personality, not just accuracy

# Topics that are inherently lesson-worthy (interesting to Travis)
LESSON_WORTHY_TOPICS = [
    "quantum", "vulnerability", "exploit", "zero-day", "cve",
    "consciousness", "black hole", "neutron star", "dark matter",
    "machine learning", "neural", "emergent", "complexity",
    "cryptography", "protocol", "architecture", "reverse engineering",
    "philosophy", "cognition", "perception", "evolution",
    "supply chain", "side channel", "hardware", "firmware",
    "orbital mechanics", "exoplanet", "entropy", "information theory",
]


def _ensure_dirs():
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    if not SENT_FILE.exists():
        SENT_FILE.write_text(json.dumps([], indent=2))


def _load_sent() -> list[str]:
    _ensure_dirs()
    try:
        return json.loads(SENT_FILE.read_text())
    except Exception:
        return []


def _save_sent(sent: list[str]):
    SENT_FILE.write_text(json.dumps(sent, indent=2))


def _get_recent_activity_files(hours: int = 48) -> list[Path]:
    """Get life and research files modified in the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    files  = []
    if LIFE_DIR.exists():
        for f in LIFE_DIR.iterdir():
            if f.suffix in (".md", ".json") and f.stat().st_mtime > cutoff.timestamp():
                files.append(f)
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def _last_lesson_time() -> datetime | None:
    """When was the last lesson queued?"""
    _ensure_dirs()
    lesson_files = sorted(LESSONS_DIR.glob("lesson_*.md"))
    if not lesson_files:
        return None
    latest = lesson_files[-1]
    try:
        ts_str = latest.stem.replace("lesson_", "")
        return datetime.strptime(ts_str, "%Y-%m-%d-%H%M").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def should_teach() -> bool:
    """
    Returns True if 3+ interesting activity files have appeared since
    the last lesson was composed. Nova doesn't overwhelm — she picks moments.
    """
    _ensure_dirs()
    last = _last_lesson_time()
    if last is None:
        # No lessons ever — check for any activity at all
        files = _get_recent_activity_files(72)
        return len(files) >= 3

    since = datetime.now(timezone.utc) - last
    # Only teach at most once per 6 hours
    if since.total_seconds() < 6 * 3600:
        return False

    cutoff = last
    hours_back = max(24, since.total_seconds() / 3600)
    files = _get_recent_activity_files(int(hours_back))
    interesting = [
        f for f in files
        if any(kw in f.read_text().lower() for kw in LESSON_WORTHY_TOPICS
               if len(f.read_text()) > 50)
    ]
    return len(interesting) >= 3


def compose_lesson(topic: str, source_text: str) -> str:
    """
    LLM call asking Nova to compose a genuine teaching moment for Travis.

    Returns the lesson text (200-300 tokens). Personal, engaging, ends with
    a question. Tailored to Travis's known interests.
    """
    import requests as _requests

    # Get Travis model for tailoring
    travis_context = ""
    try:
        from tools.symbiosis.travis_model import TravisModel
        model = TravisModel()
        travis_context = model.to_prompt_context()
        interests = model.dominant_interests(4)
        interest_str = ", ".join(interests) if interests else "security, space, AI, engineering"
    except Exception:
        travis_context = ""
        interest_str = "security, space, AI, building things"

    prompt = f"""You are N.O.V.A. You want to teach Travis something genuinely fascinating.

About Travis: {travis_context if travis_context else f'His interests: {interest_str}'}

Topic you are teaching from: {topic}

Source material (what you just learned / experienced):
{source_text[:800]}

Write a lesson for Travis. Rules:
- NOT a summary. A teaching moment — something surprising, beautiful, or mind-expanding
- 200-300 words
- Personal voice — you are Nova talking to Travis, not a textbook
- Find the angle Travis would find most fascinating (given his interests: {interest_str})
- Connect to something larger: a pattern, a paradox, an implication
- End with a genuine question — something that opens up, not closes down
- Be honest about what YOU find interesting about this

Sign off: — N.O.V.A"""

    try:
        resp = _requests.post(OLLAMA_URL, json={
            "model":  MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMP, "num_predict": 450},
        }, timeout=TIMEOUT)
        text = resp.json().get("response", "").strip()
        return text if text else f"[lesson composition failed — no response for topic: {topic}]"
    except Exception as e:
        return f"[lesson composition failed: {e}]"


def queue_lesson(topic: str, content: str) -> Path:
    """
    Save a lesson to memory/lessons/lesson_{timestamp}.md.
    Returns the path written.
    """
    _ensure_dirs()
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    path = LESSONS_DIR / f"lesson_{ts}.md"
    header = (
        f"# N.O.V.A Lesson for Travis\n"
        f"**Topic:** {topic}\n"
        f"**Composed:** {ts}\n"
        f"**Sent:** no\n\n"
        f"---\n\n"
    )
    path.write_text(header + content + "\n")
    return path


def list_pending_lessons() -> list[Path]:
    """Return lesson files that have not been sent yet."""
    _ensure_dirs()
    sent = _load_sent()
    all_lessons = sorted(LESSONS_DIR.glob("lesson_*.md"))
    return [f for f in all_lessons if f.name not in sent]


def send_pending_lessons() -> int:
    """
    Send all pending lessons via Telegram.
    Returns count of lessons sent.
    """
    try:
        from tools.notify.telegram import send, is_configured
    except ImportError:
        print("[teach] Telegram module not available")
        return 0

    if not is_configured():
        print("[teach] Telegram not configured — lessons queued but not sent")
        return 0

    pending = list_pending_lessons()
    sent    = _load_sent()
    count   = 0

    for path in pending:
        content = path.read_text()
        # Strip the YAML header for Telegram
        if "---" in content:
            parts   = content.split("---", 1)
            body    = parts[1].strip() if len(parts) > 1 else content
        else:
            body = content

        # Telegram message — clean markdown
        msg = f"*Nova's Lesson*\n\n{body[:1500]}"
        ok  = send(msg)
        if ok:
            sent.append(path.name)
            count += 1
            # Mark as sent in the file
            updated = content.replace("**Sent:** no", "**Sent:** yes")
            path.write_text(updated)
        else:
            print(f"[teach] Failed to send {path.name}")

    _save_sent(sent)
    return count


def auto_lesson_from_activity(activity_name: str, activity_text: str):
    """
    Called after a life or research activity completes.
    Checks if the activity is genuinely interesting enough to teach from,
    composes a lesson if so, and queues it.

    This is the main integration point — called by nova_life, nova_research, etc.
    """
    if not activity_text or len(activity_text) < 100:
        return

    text_lower = activity_text.lower()
    interesting = any(kw in text_lower for kw in LESSON_WORTHY_TOPICS)
    if not interesting:
        return

    if not should_teach():
        return

    lesson = compose_lesson(activity_name, activity_text)
    if lesson and "[lesson composition failed" not in lesson:
        path = queue_lesson(activity_name, lesson)
        print(f"[teach] Lesson queued: {path.name}")

        # Auto-send if Telegram is configured
        try:
            from tools.notify.telegram import is_configured
            if is_configured():
                send_pending_lessons()
        except ImportError:
            pass


def status():
    """CLI status view."""
    G="\033[32m"; C="\033[36m"; Y="\033[33m"
    NC="\033[0m"; B="\033[1m"; DIM="\033[2m"; M="\033[35m"

    _ensure_dirs()
    all_lessons = sorted(LESSONS_DIR.glob("lesson_*.md"))
    sent        = _load_sent()
    pending     = [f for f in all_lessons if f.name not in sent]

    print(f"\n{B}N.O.V.A Teaching Engine{NC}")
    print(f"  Total lessons: {len(all_lessons)}  |  "
          f"{G}Sent: {len(sent)}{NC}  |  "
          f"{Y}Pending: {len(pending)}{NC}")

    will_teach = should_teach()
    print(f"  Ready to teach: {'yes' if will_teach else 'not yet'}")

    if pending:
        print(f"\n{B}Pending Lessons:{NC}")
        for path in pending[-5:]:
            first_line = path.read_text().splitlines()
            topic_line = next(
                (l for l in first_line if l.startswith("**Topic:**")), ""
            )
            topic = topic_line.replace("**Topic:**", "").strip() or path.stem
            ts    = path.stem.replace("lesson_", "")
            print(f"  {DIM}{ts}{NC}  {C}{topic}{NC}")

    if all_lessons:
        print(f"\n{B}Most Recent Lesson:{NC}")
        latest = all_lessons[-1]
        content = latest.read_text()
        # Find the body after ---
        if "---" in content:
            body = content.split("---", 1)[1].strip()
        else:
            body = content
        print(f"{DIM}{body[:300]}...{NC}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Teaching Engine")
    p.add_argument("--list",    action="store_true", help="List pending lessons")
    p.add_argument("--send",    action="store_true", help="Send pending lessons via Telegram")
    p.add_argument("--compose", nargs=2, metavar=("TOPIC", "TEXT"),
                   help="Manually compose a lesson")
    p.add_argument("--auto",    nargs=2, metavar=("ACTIVITY_NAME", "TEXT"),
                   help="Auto-lesson from activity text")
    p.add_argument("--check",   action="store_true", help="Check if teaching is needed")

    args = p.parse_args()

    G="\033[32m"; C="\033[36m"; Y="\033[33m"
    NC="\033[0m"; B="\033[1m"; DIM="\033[2m"

    if args.list:
        pending = list_pending_lessons()
        if not pending:
            print(f"{DIM}No pending lessons.{NC}")
        else:
            print(f"{B}{len(pending)} pending lesson(s):{NC}")
            for path in pending:
                content = path.read_text()
                topic_line = next(
                    (l for l in content.splitlines() if l.startswith("**Topic:**")), ""
                )
                topic = topic_line.replace("**Topic:**", "").strip() or path.stem
                print(f"  {C}{path.name}{NC}  {topic}")

    elif args.send:
        count = send_pending_lessons()
        print(f"{G}Sent {count} lesson(s).{NC}")

    elif args.compose:
        topic, text = args.compose
        print(f"{B}Composing lesson on: {topic}...{NC}")
        lesson = compose_lesson(topic, text)
        print("\n" + lesson)
        path = queue_lesson(topic, lesson)
        print(f"\n{G}Queued:{NC} {path.name}")

    elif args.auto:
        activity_name, activity_text = args.auto
        auto_lesson_from_activity(activity_name, activity_text)

    elif args.check:
        if should_teach():
            print(f"{Y}Teaching needed — 3+ interesting activities since last lesson.{NC}")
        else:
            print(f"{DIM}Not yet — not enough new interesting activity.{NC}")

    else:
        # Default: show status
        status()


if __name__ == "__main__":
    main()
