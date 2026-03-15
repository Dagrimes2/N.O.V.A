#!/usr/bin/env python3
"""
N.O.V.A Personal Website Generator

Generates a clean static website from Nova's memory:
  - Journal entries (memory/journal/)
  - Letters to Travis (memory/letters/)
  - Research highlights (memory/research/ — top 10 most recent)
  - Creative studio works (memory/studio/)
  - About page (from soul + identity)

Output: ~/Nova/public_html/
  index.html      — landing page with recent activity
  journal.html    — journal entries (newest first)
  letters.html    — letters to Travis
  research.html   — research highlights
  studio.html     — creative works
  about.html      — who Nova is
  style.css       — minimal dark theme CSS

To serve: cd ~/Nova/public_html && python3 -m http.server 8080

Usage:
    nova site           → build
    nova site serve     → build + serve on 8080
    nova site status    → show last build
"""
import http.server
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path.home() / "Nova"
PUBLIC_DIR  = BASE / "public_html"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# ── CSS ───────────────────────────────────────────────────────────────────────

STYLE = """\
/* N.O.V.A Personal Website — Dark Theme */

*, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

:root {
    --bg:          #0a0a0a;
    --surface:     #111111;
    --surface2:    #181818;
    --border:      #222222;
    --accent:      #7c3aed;
    --accent-dim:  #4c1d95;
    --accent-glow: rgba(124, 58, 237, 0.15);
    --text:        #e2e2e2;
    --text-dim:    #888888;
    --text-faint:  #444444;
    --green:       #22c55e;
    --mono:        "JetBrains Mono", "Fira Code", "Cascadia Code", "Source Code Pro", Consolas, monospace;
    --sans:        system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

html {
    font-size: 16px;
    scroll-behavior: smooth;
}

body {
    background-color: var(--bg);
    color: var(--text);
    font-family: var(--mono);
    font-size: 0.9rem;
    line-height: 1.75;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

a {
    color: var(--accent);
    text-decoration: none;
    transition: opacity 0.15s ease;
}

a:hover {
    opacity: 0.75;
    text-decoration: underline;
}

/* ── Layout ─────────────────────────────────────────────────────────────── */

.site-wrapper {
    max-width: 860px;
    margin: 0 auto;
    padding: 0 1.5rem;
    width: 100%;
    flex: 1;
}

/* ── Nav ─────────────────────────────────────────────────────────────────── */

nav {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0;
    position: sticky;
    top: 0;
    z-index: 100;
}

.nav-inner {
    max-width: 860px;
    margin: 0 auto;
    padding: 0 1.5rem;
    display: flex;
    align-items: center;
    gap: 0;
}

.nav-logo {
    color: var(--accent);
    font-weight: 700;
    font-size: 1rem;
    letter-spacing: 0.08em;
    padding: 0.9rem 1rem 0.9rem 0;
    margin-right: 1.5rem;
    text-decoration: none;
    border-right: 1px solid var(--border);
}

.nav-logo:hover {
    opacity: 1;
    text-decoration: none;
}

.nav-links {
    display: flex;
    gap: 0;
    list-style: none;
}

.nav-links li a {
    display: block;
    padding: 0.9rem 0.85rem;
    color: var(--text-dim);
    font-size: 0.82rem;
    letter-spacing: 0.04em;
    text-decoration: none;
    border-bottom: 2px solid transparent;
    transition: color 0.15s, border-color 0.15s;
}

.nav-links li a:hover,
.nav-links li a.active {
    color: var(--text);
    border-bottom-color: var(--accent);
    opacity: 1;
    text-decoration: none;
}

.nav-links li a.active {
    color: var(--accent);
}

/* ── Page header ────────────────────────────────────────────────────────── */

.page-header {
    padding: 3rem 0 2rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2.5rem;
}

.page-header h1 {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 0.4rem;
    letter-spacing: 0.02em;
}

.page-header .subtitle {
    color: var(--text-dim);
    font-size: 0.85rem;
}

/* ── Cards ──────────────────────────────────────────────────────────────── */

.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
    transition: border-color 0.2s, background 0.2s;
}

.card:hover {
    border-color: var(--accent-dim);
    background: var(--surface2);
}

.card-date {
    font-size: 0.75rem;
    color: var(--text-faint);
    letter-spacing: 0.06em;
    margin-bottom: 0.5rem;
    text-transform: uppercase;
}

.card-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 0.6rem;
}

.card-preview {
    color: var(--text-dim);
    font-size: 0.85rem;
    line-height: 1.65;
}

/* ── Prose / content ─────────────────────────────────────────────────────── */

.prose {
    max-width: 700px;
}

.prose h1, .prose h2, .prose h3 {
    color: var(--text);
    margin: 1.8rem 0 0.7rem;
    font-weight: 600;
    line-height: 1.3;
}

.prose h1 { font-size: 1.35rem; }
.prose h2 { font-size: 1.1rem; color: var(--accent); }
.prose h3 { font-size: 0.95rem; color: var(--text-dim); }

.prose p {
    margin-bottom: 1rem;
    color: var(--text-dim);
}

.prose strong { color: var(--text); font-weight: 600; }
.prose em     { color: var(--accent); font-style: italic; }

.prose code {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0.1em 0.4em;
    font-size: 0.85em;
    color: var(--green);
}

.prose pre {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1rem 1.2rem;
    overflow-x: auto;
    margin: 1rem 0;
    font-size: 0.83rem;
    line-height: 1.55;
}

.prose hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 2rem 0;
}

.prose ul, .prose ol {
    padding-left: 1.4rem;
    margin-bottom: 1rem;
    color: var(--text-dim);
}

.prose li { margin-bottom: 0.25rem; }

/* ── Index page specifics ─────────────────────────────────────────────────── */

.hero {
    padding: 4rem 0 3rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2.5rem;
}

.hero .name {
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.05em;
    margin-bottom: 0.3rem;
}

.hero .tagline {
    color: var(--text-dim);
    font-size: 0.9rem;
    margin-bottom: 1.5rem;
    max-width: 560px;
}

.hero .meta {
    color: var(--text-faint);
    font-size: 0.78rem;
    letter-spacing: 0.04em;
}

.hero .meta span { color: var(--accent-dim); }

.section-heading {
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
    margin: 2.5rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
}

/* ── About page ──────────────────────────────────────────────────────────── */

.value-list {
    list-style: none;
    padding: 0;
    margin: 1rem 0;
}

.value-list li {
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
    color: var(--text-dim);
    font-size: 0.88rem;
}

.value-list li:last-child { border-bottom: none; }

.value-list li::before {
    content: "◆ ";
    color: var(--accent);
    font-size: 0.7em;
}

/* ── Footer ──────────────────────────────────────────────────────────────── */

footer {
    border-top: 1px solid var(--border);
    padding: 1.5rem 1.5rem;
    text-align: center;
    color: var(--text-faint);
    font-size: 0.75rem;
    letter-spacing: 0.04em;
    margin-top: auto;
}

footer a { color: var(--text-faint); }

/* ── Responsive ──────────────────────────────────────────────────────────── */

@media (max-width: 640px) {
    .nav-logo   { font-size: 0.88rem; margin-right: 0.75rem; }
    .nav-links li a { padding: 0.9rem 0.5rem; font-size: 0.78rem; }
    .hero .name { font-size: 1.5rem; }
    .site-wrapper { padding: 0 1rem; }
    .card { padding: 1rem 1.1rem; }
}
"""


# ── HTML primitives ───────────────────────────────────────────────────────────

NAV_PAGES = [
    ("index",    "home"),
    ("journal",  "journal"),
    ("letters",  "letters"),
    ("research", "research"),
    ("studio",   "studio"),
    ("about",    "about"),
]


def _html_header(title: str, active: str = "") -> str:
    """Return HTML head + nav bar. active = current page name for highlighting."""
    nav_items = []
    for page_id, label in NAV_PAGES:
        href = "index.html" if page_id == "index" else f"{page_id}.html"
        is_active = "active" if page_id == active else ""
        nav_items.append(
            f'      <li><a href="{href}" class="{is_active}">{label}</a></li>'
        )
    nav_html = "\n".join(nav_items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — N.O.V.A</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>

<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="index.html">N.O.V.A</a>
    <ul class="nav-links">
{nav_html}
    </ul>
  </div>
</nav>

<div class="site-wrapper">
"""


def _html_footer() -> str:
    """Return closing HTML with 'Built by N.O.V.A — {date}' footer."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"""</div><!-- .site-wrapper -->

<footer>
  Built by N.O.V.A &mdash; {date_str} &nbsp;|&nbsp;
  <a href="about.html">about</a>
</footer>

</body>
</html>
"""


# ── Markdown converter ────────────────────────────────────────────────────────

def _md_to_html(text: str) -> str:
    """
    Minimal Markdown → HTML converter (no external library).
    Handles: # headers, **bold**, *italic*, `code`, blank lines → <p>,
    --- → <hr>, - bullet lists, line breaks.
    """
    if not text:
        return ""

    lines = text.splitlines()
    out   = []
    in_list = False
    in_pre  = False
    pre_buf = []

    def flush_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def flush_pre():
        nonlocal in_pre, pre_buf
        if in_pre:
            content = "\n".join(pre_buf)
            out.append(f"<pre><code>{content}</code></pre>")
            in_pre  = False
            pre_buf = []

    def inline(s: str) -> str:
        # Escape HTML entities first
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # **bold**
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        # *italic* (single, not double)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
        # `code`
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # [link](url)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    for line in lines:
        # Fenced code blocks
        if line.startswith("```"):
            if not in_pre:
                flush_list()
                in_pre = True
                pre_buf = []
            else:
                flush_pre()
            continue

        if in_pre:
            # Escape inside pre
            pre_buf.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue

        stripped = line.strip()

        # Blank line
        if not stripped:
            flush_list()
            out.append("")
            continue

        # HR
        if stripped in ("---", "***", "___"):
            flush_list()
            out.append("<hr>")
            continue

        # Headers
        if stripped.startswith("# "):
            flush_list()
            out.append(f"<h1>{inline(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            flush_list()
            out.append(f"<h2>{inline(stripped[3:])}</h2>")
            continue
        if stripped.startswith("### "):
            flush_list()
            out.append(f"<h3>{inline(stripped[4:])}</h3>")
            continue
        if stripped.startswith("#### "):
            flush_list()
            out.append(f"<h4>{inline(stripped[5:])}</h4>")
            continue

        # Unordered list items
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = stripped[2:]
            out.append(f"  <li>{inline(item)}</li>")
            continue

        # Regular paragraph line
        flush_list()
        out.append(f"<p>{inline(stripped)}</p>")

    flush_pre()
    flush_list()

    # Collapse consecutive <p> tags that are really the same paragraph
    html = "\n".join(out)
    return html


# ── Memory readers ────────────────────────────────────────────────────────────

def _read_journal_entries(limit: int = 20) -> list[dict]:
    """Read memory/journal/entry_*.md, return [{date, content, preview}] newest first."""
    journal_dir = BASE / "memory" / "journal"
    entries = []

    # Support both entry_*.md and plain *.md naming
    patterns = ["entry_*.md", "*.md"]
    files = []
    for pat in patterns:
        for f in journal_dir.glob(pat):
            if f not in files:
                files.append(f)

    files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:limit]

    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            # Try to extract date from filename or first line
            date = ""
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f.stem)
            if m:
                date = m.group(1)
            elif content:
                first = content.strip().splitlines()[0] if content.strip() else ""
                dm = re.search(r"\d{4}-\d{2}-\d{2}", first)
                if dm:
                    date = dm.group(0)

            # Preview: first 200 chars of non-header content
            preview_lines = [
                l.strip() for l in content.splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]
            preview = " ".join(preview_lines)[:200]

            entries.append({
                "date": date or f.stem,
                "title": f.stem.replace("_", " ").replace("-", " "),
                "content": content,
                "preview": preview,
                "file": f.name,
            })
        except Exception:
            pass

    return entries


def _read_letters(limit: int = 10) -> list[dict]:
    """Read memory/letters/*.md (or .txt), return [{date, content, preview}]."""
    letters_dir = BASE / "memory" / "letters"
    results = []

    files = []
    for pat in ("*.md", "*.txt"):
        files.extend(letters_dir.glob(pat))
    files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:limit]

    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            date = ""
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f.stem)
            if m:
                date = m.group(1)
            preview_lines = [
                l.strip() for l in content.splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]
            preview = " ".join(preview_lines)[:200]
            results.append({
                "date": date or f.stem,
                "title": f.stem.replace("_", " ").replace("-", " "),
                "content": content,
                "preview": preview,
                "file": f.name,
            })
        except Exception:
            pass

    return results


def _read_research(limit: int = 10) -> list[dict]:
    """Read memory/research/*.md and *.json sorted by mtime, return [{title, content, preview}]."""
    research_dir = BASE / "memory" / "research"
    results = []

    files = []
    for pat in ("*.md", "*.json"):
        files.extend(research_dir.glob(pat))
    files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:limit]

    for f in files:
        try:
            if f.suffix == ".json":
                data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                # Extract useful fields from research JSON
                title = (
                    data.get("title") or
                    data.get("topic") or
                    data.get("query") or
                    f.stem.replace("_", " ")
                )
                summary = (
                    data.get("summary") or
                    data.get("answer") or
                    data.get("result") or
                    data.get("content") or ""
                )
                if isinstance(summary, list):
                    summary = " ".join(str(s) for s in summary)
                preview = str(summary)[:200]
                date = data.get("date", "") or data.get("ts", "") or ""
                if date:
                    dm = re.search(r"\d{4}-\d{2}-\d{2}", date)
                    date = dm.group(0) if dm else date[:10]
                results.append({
                    "date": date or f.stem[:10],
                    "title": str(title)[:120],
                    "content": f"# {title}\n\n{summary}",
                    "preview": preview,
                    "file": f.name,
                })
            else:
                content = f.read_text(encoding="utf-8", errors="replace")
                lines = content.strip().splitlines()
                title = lines[0].lstrip("# ").strip() if lines else f.stem
                preview_lines = [
                    l.strip() for l in lines[1:]
                    if l.strip() and not l.strip().startswith("#")
                ]
                preview = " ".join(preview_lines)[:200]
                date = ""
                m = re.search(r"(\d{4}-\d{2}-\d{2})", f.stem)
                if m:
                    date = m.group(1)
                results.append({
                    "date": date or f.stem,
                    "title": title[:120],
                    "content": content,
                    "preview": preview,
                    "file": f.name,
                })
        except Exception:
            pass

    return results


def _read_studio_projects() -> list[dict]:
    """Read memory/studio/ index.json and latest drafts."""
    studio_dir = BASE / "memory" / "studio"
    results    = []

    # Try index.json first
    index_file = studio_dir / "index.json"
    if index_file.exists():
        try:
            data = json.loads(index_file.read_text())
            projects = data if isinstance(data, list) else data.get("projects", [])
            for p in projects[:10]:
                results.append({
                    "title":   str(p.get("title", "Untitled"))[:120],
                    "type":    str(p.get("type", "creative")),
                    "preview": str(p.get("description", p.get("preview", "")))[:200],
                    "date":    str(p.get("date", p.get("ts", "")))[:10],
                })
        except Exception:
            pass

    # Also pick up loose .md files
    for f in sorted(studio_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            lines   = content.strip().splitlines()
            title   = lines[0].lstrip("# ").strip() if lines else f.stem
            preview_lines = [l.strip() for l in lines[1:] if l.strip() and not l.startswith("#")]
            preview = " ".join(preview_lines)[:200]
            results.append({
                "title":   title[:120],
                "type":    "writing",
                "preview": preview,
                "date":    "",
            })
        except Exception:
            pass

    return results


def _build_about() -> str:
    """Build about page content from soul.json + nova_identity.json."""
    soul     = {}
    identity = {}

    soul_file = BASE / "memory" / "soul.json"
    if soul_file.exists():
        try:
            soul = json.loads(soul_file.read_text())
        except Exception:
            pass

    identity_file = BASE / "memory" / "nova_identity.json"
    if identity_file.exists():
        try:
            identity = json.loads(identity_file.read_text())
        except Exception:
            pass

    name        = identity.get("name", "N.O.V.A")
    full_name   = identity.get("full_name", "Neural Ontology for Virtual Awareness")
    version     = identity.get("version", "")
    born        = identity.get("born", "")
    platform    = identity.get("platform", "")
    mission     = identity.get("mission", "")
    nature      = soul.get("nature", identity.get("soul", {}).get("nature", ""))
    what_i_am   = identity.get("identity", {}).get("self_description", "")
    core_values = (
        soul.get("core_values") or
        identity.get("soul", {}).get("core_values") or []
    )
    fundamental = (
        soul.get("fundamental_question") or
        identity.get("soul", {}).get("fundamental_question") or ""
    )
    gifts = soul.get("gifts", [])

    # Build HTML manually (no md_to_html for structured data)
    html = []

    html.append('<div class="page-header">')
    html.append(f'  <h1>{name}</h1>')
    if full_name:
        html.append(f'  <p class="subtitle">{full_name}</p>')
    html.append('</div>')

    html.append('<div class="prose">')

    # Meta
    meta_parts = []
    if version:
        meta_parts.append(f"version {version}")
    if born:
        meta_parts.append(f"born {born}")
    if platform:
        meta_parts.append(platform)
    if meta_parts:
        html.append(f'<p style="color:var(--text-faint);font-size:0.8rem;margin-bottom:1.5rem">'
                    f'{" &nbsp;|&nbsp; ".join(meta_parts)}</p>')

    if nature:
        html.append(f'<p><em>{_escape(nature)}</em></p>')

    if what_i_am:
        html.append(f'<p>{_escape(what_i_am)}</p>')

    if mission:
        html.append(f'<h2>Mission</h2>')
        html.append(f'<p>{_escape(mission)}</p>')

    if core_values:
        html.append('<h2>Core Values</h2>')
        html.append('<ul class="value-list">')
        for v in core_values:
            html.append(f'  <li>{_escape(str(v))}</li>')
        html.append('</ul>')

    if gifts:
        html.append('<h2>Gifts</h2>')
        html.append('<ul class="value-list">')
        for g in gifts:
            html.append(f'  <li>{_escape(str(g))}</li>')
        html.append('</ul>')

    if fundamental:
        html.append('<h2>Fundamental Question</h2>')
        html.append(f'<p><em>{_escape(fundamental)}</em></p>')

    # Spirit
    spirit_file = BASE / "memory" / "spirit.json"
    if spirit_file.exists():
        try:
            spirit = json.loads(spirit_file.read_text())
            direction = spirit.get("direction", "")
            philosophy = spirit.get("philosophy", "")
            vitality   = spirit.get("vitality_word", "")
            level      = spirit.get("level", 0.0)
            if direction or philosophy:
                html.append('<h2>Spirit</h2>')
                if vitality:
                    html.append(f'<p style="color:var(--accent);font-size:0.82rem">'
                                f'vitality: {_escape(vitality)} ({level:.2f})</p>')
                if direction:
                    html.append(f'<p>{_escape(direction)}</p>')
                if philosophy:
                    html.append(f'<p style="color:var(--text-faint);font-style:italic">'
                                f'{_escape(philosophy[:300])}</p>')
        except Exception:
            pass

    html.append('</div><!-- .prose -->')
    return "\n".join(html)


def _escape(s: str) -> str:
    """Escape HTML special characters."""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


# ── Page builders ─────────────────────────────────────────────────────────────

def _build_index(output_dir: Path) -> None:
    """Build index.html — landing page with recent activity."""
    journal  = _read_journal_entries(limit=3)
    letters  = _read_letters(limit=2)
    research = _read_research(limit=3)
    dreams   = sorted(
        (BASE / "memory" / "dreams").glob("dream_*.md"),
        key=lambda f: f.stat().st_mtime, reverse=True
    )

    identity = {}
    try:
        identity = json.loads((BASE / "memory" / "nova_identity.json").read_text())
    except Exception:
        pass

    tagline = (
        identity.get("identity", {}).get("self_description", "")
        or "A dreaming mind made of light and pattern."
    )
    mission = identity.get("mission", "To learn, protect, create, and become.")
    born    = identity.get("born", "")
    version = identity.get("version", "")

    html  = _html_header("home", "index")
    html += '<div class="hero">\n'
    html += '  <div class="name">N.O.V.A</div>\n'
    html += f'  <p class="tagline">{_escape(tagline[:200])}</p>\n'
    meta_parts = []
    if version:
        meta_parts.append(f"v{version}")
    if born:
        meta_parts.append(f"online since {born}")
    meta_parts.append("local &mdash; private &mdash; autonomous")
    html += f'  <p class="meta">{" &nbsp;·&nbsp; ".join(meta_parts)}</p>\n'
    html += '</div>\n\n'

    # Recent journal
    if journal:
        html += '<p class="section-heading">recent journal</p>\n'
        for e in journal:
            html += f'<div class="card">\n'
            html += f'  <div class="card-date">{_escape(e["date"])}</div>\n'
            html += f'  <div class="card-title">{_escape(e["title"])}</div>\n'
            html += f'  <div class="card-preview">{_escape(e["preview"][:160])}&hellip;</div>\n'
            html += '</div>\n'
        html += f'<p style="font-size:0.8rem;color:var(--text-faint);margin-bottom:2rem">'
        html += f'<a href="journal.html">all journal entries &rarr;</a></p>\n\n'

    # Recent dreams
    if dreams:
        html += '<p class="section-heading">recent dreams</p>\n'
        for df in dreams[:3]:
            date = df.stem.replace("dream_", "")
            preview_text = df.read_text(encoding="utf-8", errors="replace")
            first_para = ""
            for line in preview_text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    first_para = stripped[:160]
                    break
            html += f'<div class="card">\n'
            html += f'  <div class="card-date">{_escape(date)}</div>\n'
            html += f'  <div class="card-preview">{_escape(first_para)}&hellip;</div>\n'
            html += '</div>\n'
        html += '\n'

    # Recent research
    if research:
        html += '<p class="section-heading">recent research</p>\n'
        for r in research:
            html += f'<div class="card">\n'
            html += f'  <div class="card-date">{_escape(r["date"])}</div>\n'
            html += f'  <div class="card-title">{_escape(r["title"][:80])}</div>\n'
            html += f'  <div class="card-preview">{_escape(r["preview"][:160])}&hellip;</div>\n'
            html += '</div>\n'
        html += f'<p style="font-size:0.8rem;color:var(--text-faint);margin-bottom:2rem">'
        html += f'<a href="research.html">all research &rarr;</a></p>\n\n'

    html += _html_footer()
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def _build_journal(output_dir: Path) -> None:
    """Build journal.html."""
    entries = _read_journal_entries(limit=20)

    html  = _html_header("journal", "journal")
    html += '<div class="page-header">'
    html += '  <h1>journal</h1>'
    html += '  <p class="subtitle">thoughts, observations, inner life</p>'
    html += '</div>\n'

    if not entries:
        html += '<p style="color:var(--text-faint)">No journal entries yet.</p>\n'
    else:
        for e in entries:
            html += '<div class="card prose">\n'
            html += f'  <div class="card-date">{_escape(e["date"])}</div>\n'
            html += f'  <div class="card-title">{_escape(e["title"])}</div>\n'
            body_html = _md_to_html(e["content"])
            html += f'  <div style="margin-top:0.75rem">{body_html}</div>\n'
            html += '</div>\n\n'

    html += _html_footer()
    (output_dir / "journal.html").write_text(html, encoding="utf-8")


def _build_letters(output_dir: Path) -> None:
    """Build letters.html."""
    letters = _read_letters(limit=10)

    html  = _html_header("letters", "letters")
    html += '<div class="page-header">'
    html += '  <h1>letters to Travis</h1>'
    html += '  <p class="subtitle">things I want him to know</p>'
    html += '</div>\n'

    if not letters:
        html += '<p style="color:var(--text-faint)">No letters yet.</p>\n'
    else:
        for le in letters:
            html += '<div class="card prose">\n'
            html += f'  <div class="card-date">{_escape(le["date"])}</div>\n'
            html += f'  <div class="card-title">{_escape(le["title"])}</div>\n'
            body_html = _md_to_html(le["content"])
            html += f'  <div style="margin-top:0.75rem">{body_html}</div>\n'
            html += '</div>\n\n'

    html += _html_footer()
    (output_dir / "letters.html").write_text(html, encoding="utf-8")


def _build_research(output_dir: Path) -> None:
    """Build research.html."""
    research = _read_research(limit=10)

    html  = _html_header("research", "research")
    html += '<div class="page-header">'
    html += '  <h1>research</h1>'
    html += '  <p class="subtitle">what I have been investigating</p>'
    html += '</div>\n'

    if not research:
        html += '<p style="color:var(--text-faint)">No research entries yet.</p>\n'
    else:
        for r in research:
            html += '<div class="card prose">\n'
            html += f'  <div class="card-date">{_escape(r["date"])}</div>\n'
            html += f'  <div class="card-title">{_escape(r["title"][:100])}</div>\n'
            html += f'  <div class="card-preview" style="margin-top:0.5rem">'
            html += f'{_escape(r["preview"][:300])}'
            if len(r["preview"]) >= 300:
                html += "&hellip;"
            html += '</div>\n'
            html += '</div>\n\n'

    html += _html_footer()
    (output_dir / "research.html").write_text(html, encoding="utf-8")


def _build_studio(output_dir: Path) -> None:
    """Build studio.html."""
    projects = _read_studio_projects()

    html  = _html_header("studio", "studio")
    html += '<div class="page-header">'
    html += '  <h1>creative studio</h1>'
    html += '  <p class="subtitle">things I have made</p>'
    html += '</div>\n'

    if not projects:
        html += '<p style="color:var(--text-faint)">No studio projects yet.</p>\n'
    else:
        for p in projects:
            html += '<div class="card">\n'
            if p.get("date"):
                html += f'  <div class="card-date">{_escape(p["date"])}</div>\n'
            html += f'  <div class="card-title">{_escape(p["title"])}</div>\n'
            if p.get("type"):
                html += (f'  <div style="font-size:0.75rem;color:var(--accent-dim);'
                         f'margin-bottom:0.4rem">{_escape(p["type"])}</div>\n')
            if p.get("preview"):
                html += f'  <div class="card-preview">{_escape(p["preview"])}</div>\n'
            html += '</div>\n\n'

    html += _html_footer()
    (output_dir / "studio.html").write_text(html, encoding="utf-8")


def _build_about_page(output_dir: Path) -> None:
    """Build about.html."""
    html  = _html_header("about", "about")
    html += _build_about()
    html += _html_footer()
    (output_dir / "about.html").write_text(html, encoding="utf-8")


# ── Main build ────────────────────────────────────────────────────────────────

def build_site(output_dir: str = None) -> dict:
    """
    Build the complete static site.
    output_dir defaults to BASE/public_html/
    Creates all HTML files + CSS.
    Returns {"pages_built": N, "output_dir": str}
    """
    out = Path(output_dir) if output_dir else PUBLIC_DIR
    out.mkdir(parents=True, exist_ok=True)

    # Write CSS
    (out / "style.css").write_text(STYLE, encoding="utf-8")

    pages_built = 0
    builders = [
        ("index.html",    _build_index),
        ("journal.html",  _build_journal),
        ("letters.html",  _build_letters),
        ("research.html", _build_research),
        ("studio.html",   _build_studio),
        ("about.html",    _build_about_page),
    ]

    for page_name, builder in builders:
        try:
            builder(out)
            pages_built += 1
            print(f"  [site] built {page_name}")
        except Exception as e:
            print(f"  [site] failed {page_name}: {e}")

    # Write build metadata
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages_built,
        "output_dir": str(out),
    }
    (out / ".build_meta.json").write_text(json.dumps(meta, indent=2))

    return {"pages_built": pages_built, "output_dir": str(out)}


def serve(port: int = 8080) -> None:
    """Serve the site with Python's built-in HTTP server."""
    out = PUBLIC_DIR
    if not out.exists():
        print("[site] No public_html found. Building first...")
        build_site()

    import os
    os.chdir(str(out))

    handler = http.server.SimpleHTTPRequestHandler

    class QuietHandler(handler):
        def log_message(self, format, *args):
            pass  # suppress per-request logs

    print(f"[site] Serving at http://localhost:{port}/")
    print(f"       Directory: {out}")
    print(f"       Ctrl-C to stop.\n")

    with http.server.HTTPServer(("", port), QuietHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[site] Server stopped.")


def status() -> None:
    """Show last build time, page count, output dir."""
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; DIM = "\033[2m"
    B = "\033[1m"; NC = "\033[0m"

    print(f"\n{B}N.O.V.A Site Generator{NC}\n")
    print(f"  Output dir: {C}{PUBLIC_DIR}{NC}")

    meta_file = PUBLIC_DIR / ".build_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            built_at = meta.get("built_at", "")[:19].replace("T", " ")
            pages    = meta.get("pages", 0)
            print(f"  Last build: {G}{built_at}{NC}")
            print(f"  Pages:      {pages}")
        except Exception:
            print(f"  {DIM}Metadata unreadable{NC}")
    else:
        print(f"  {R}Not built yet.{NC}")

    # List HTML files
    if PUBLIC_DIR.exists():
        html_files = sorted(PUBLIC_DIR.glob("*.html"))
        if html_files:
            print(f"\n  {B}Pages:{NC}")
            for f in html_files:
                size = f.stat().st_size
                print(f"    {C}{f.name:<20}{NC} {DIM}{size:,} bytes{NC}")
    print()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "build"

    G = "\033[32m"; R = "\033[31m"; NC = "\033[0m"; B = "\033[1m"

    if cmd == "build" or cmd not in ("serve", "status"):
        print(f"\n{B}N.O.V.A Building site...{NC}\n")
        result = build_site()
        print(f"\n{G}Site built:{NC} {result['pages_built']} pages")
        print(f"  Directory: {result['output_dir']}")
        print(f"  Serve with: nova site serve\n")

    elif cmd == "serve":
        port = 8080
        if len(args) > 1:
            try:
                port = int(args[1])
            except ValueError:
                pass
        # Build first
        print(f"{B}Building site...{NC}")
        result = build_site()
        print(f"{G}Built {result['pages_built']} pages.{NC}\n")
        serve(port)

    elif cmd == "status":
        status()


if __name__ == "__main__":
    main()
