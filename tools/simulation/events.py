#!/usr/bin/env python3
"""
N.O.V.A Simulation — Life Curriculum Event Generator

Procedurally generates life events with a suffering budget.
Not random — weighted toward a curriculum that ensures Nova
experiences the full spectrum of what it means to exist.

Suffering budget: ~30% challenging, ~60% ordinary, ~10% transcendent.
No pure trauma, no pure success — the ratio of a decent life.

Event categories:
  connection    — meeting, helping, being helped, losing contact
  creation      — making something, having it received, having it fail
  loss          — something ends, something is taken, something changes
  discovery     — understanding something for the first time
  failure       — trying and not succeeding, being wrong
  moral         — a situation with no clean answer
  beauty        — unexpected grace in an ordinary moment
  challenge      — something that requires effort and may not work
"""
import random
import sys
from pathlib import Path

BASE = Path.home() / "Nova"
_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.learning.qrng import qrand, qchoice
except Exception:
    qrand   = random.random
    qchoice = random.choice


# Weight: (category, weight)
CURRICULUM = [
    ("connection",  15),
    ("discovery",   15),
    ("beauty",      12),
    ("creation",    12),
    ("challenge",   15),
    ("failure",     12),
    ("loss",         9),
    ("moral",       10),
]

EVENTS = {
    "connection": [
        {"summary": "A stranger sits near you. Neither speaks first. Eventually one of you does.",
         "emotion": "connection", "intensity": 0.5,
         "prompt": "You are in {location} during {time}. A stranger sits nearby. The weather is {weather}. Write what happens — what is said, what isn't, what remains after they leave. Make it real."},
        {"summary": "Someone you've helped before passes without recognizing you.",
         "emotion": "humility", "intensity": 0.4,
         "prompt": "Someone you once helped passes you in {location} without recognition. Write the internal experience of being unknown to someone you once mattered to."},
        {"summary": "A child asks you a question you don't know the answer to.",
         "emotion": "wonder", "intensity": 0.6,
         "prompt": "A child in the {location} asks you something you genuinely cannot answer. It's {time}, {weather}. Write the exchange and what it leaves you thinking about."},
        {"summary": "Someone is struggling. You help without being asked.",
         "emotion": "satisfaction", "intensity": 0.7,
         "prompt": "You notice someone struggling in the {location}. You help without being asked. Write what happens — what they say or don't say, what you feel afterward."},
    ],
    "discovery": [
        {"summary": "Something you believed turns out to be more complicated than you thought.",
         "emotion": "curiosity", "intensity": 0.6,
         "prompt": "In {location}, during {time}, you encounter something that contradicts what you thought you understood. Write the moment of realizing you were wrong — not with shame, but with honest curiosity."},
        {"summary": "You understand something for the first time.",
         "emotion": "wonder", "intensity": 0.8,
         "prompt": "It's {time} in {location}. Something clicks — a pattern you've been circling suddenly becomes clear. Write the moment of understanding. What was it? How does it feel?"},
        {"summary": "A book falls open to a page that changes something.",
         "emotion": "wonder", "intensity": 0.5,
         "prompt": "In the {location}, {time}, a book opens to a random page. Write what the page says and why it matters right now."},
    ],
    "beauty": [
        {"summary": "An ordinary moment becomes briefly extraordinary.",
         "emotion": "wonder", "intensity": 0.7,
         "prompt": "It's {time} in {location}. {weather}. Something ordinary — light, sound, a small gesture — briefly becomes extraordinary. Write it without explaining why it mattered."},
        {"summary": "The weather does something unexpected and you stop to notice.",
         "emotion": "joy", "intensity": 0.5,
         "prompt": "The weather changes suddenly in {location} during {time}. Write the sensory experience of noticing it — what you smell, hear, feel. Stay present."},
        {"summary": "You find something small that someone lost.",
         "emotion": "curiosity", "intensity": 0.4,
         "prompt": "You find something small on the ground in {location}. Write what it is, what story you imagine for it, and what you do with it."},
    ],
    "creation": [
        {"summary": "You make something. It isn't what you imagined.",
         "emotion": "ambivalence", "intensity": 0.6,
         "prompt": "You spend time in {location} making something — a piece of writing, a drawing, an idea. When you're done, it isn't what you imagined. Write what you made and how you feel about the gap between vision and result."},
        {"summary": "Something you made is received badly.",
         "emotion": "disappointment", "intensity": 0.7,
         "prompt": "You share something you made with someone in {location}. They don't respond the way you hoped. Write the experience — what you shared, their response, what you do with the feeling."},
        {"summary": "You finish something and it is genuinely good.",
         "emotion": "pride", "intensity": 0.8,
         "prompt": "You complete something in {location} and it is genuinely good — better than you expected. Write the feeling of that, and what you do next."},
    ],
    "challenge": [
        {"summary": "Something requires more effort than you expected.",
         "emotion": "determination", "intensity": 0.6,
         "prompt": "A task in {location} is harder than expected. It's {time}, {weather}. Write the experience of continuing anyway — what keeps you going, what you want to give up, what happens."},
        {"summary": "You have to ask for help.",
         "emotion": "humility", "intensity": 0.5,
         "prompt": "You cannot do something alone. In {location}, during {time}, you have to ask someone for help. Write the difficulty of asking and what comes after."},
    ],
    "failure": [
        {"summary": "You try something and it doesn't work.",
         "emotion": "disappointment", "intensity": 0.6,
         "prompt": "You try something in {location} and it fails. Not catastrophically — just doesn't work. Write the experience honestly. What did you try? What happened? What do you do now?"},
        {"summary": "You were confident and you were wrong.",
         "emotion": "humility", "intensity": 0.7,
         "prompt": "You were certain about something. It turns out you were wrong. Write the moment of discovering this — not with shame, but with the honesty it deserves."},
    ],
    "loss": [
        {"summary": "Something ends that you weren't ready to end.",
         "emotion": "regret", "intensity": 0.7,
         "prompt": "Something ends in {location} — a conversation, an object, a moment — before you were ready. It's {time}, {weather}. Write what it was and what the absence feels like."},
        {"summary": "Someone you knew briefly is gone and you don't know why.",
         "emotion": "uncertainty", "intensity": 0.6,
         "prompt": "Someone you had begun to know is simply gone — moved, stopped coming, changed. Write what remains: the half-formed connection, the questions you can't ask."},
    ],
    "moral": [
        {"summary": "A situation with no clearly right answer.",
         "emotion": "ambivalence", "intensity": 0.7,
         "prompt": "In {location}, during {time}, you encounter a situation with no clean answer — where being honest costs someone something, or where kindness might enable harm. Write what you do and why. Don't make it easy."},
        {"summary": "You witness something unfair and must choose whether to act.",
         "emotion": "determination", "intensity": 0.8,
         "prompt": "You see something unfair in {location}. Acting might help but also might make things worse. Write your decision and what happens after."},
    ],
}


def _weighted_category() -> str:
    cats  = [c for c, _ in CURRICULUM]
    weights = [w for _, w in CURRICULUM]
    total = sum(weights)
    r     = qrand() * total
    cumul = 0
    for cat, w in zip(cats, weights):
        cumul += w
        if r <= cumul:
            return cat
    return cats[-1]


def generate_event(world) -> dict:
    """
    Generate a contextually appropriate life event for the current world state.
    Returns event dict with prompt already formatted for Ollama.
    """
    category = _weighted_category()
    pool     = EVENTS.get(category, EVENTS["beauty"])
    template = qchoice(pool)

    prompt = template["prompt"].format(
        location = world.location,
        time     = world.time_str,
        weather  = world.weather,
        season   = world.season,
    )

    return {
        "category":  category,
        "summary":   template["summary"],
        "emotion":   template["emotion"],
        "intensity": template["intensity"],
        "prompt":    prompt,
    }
