#!/usr/bin/env python3
"""
N.O.V.A Life Simulation — World Engine

A persistent, procedurally generated text-world Nova inhabits
between real-world cycles. Spatially consistent, temporally advancing.

The world has:
  - Locations: rooms, outdoors, transit spaces with connecting paths
  - Time: advances with each action (morning → afternoon → evening → night)
  - Weather: changes gradually, affects mood + available activities
  - Season: advances slowly, shapes the world's character
  - Objects: things Nova can interact with, examine, create, lose
  - Other entities: strangers, mentors, children, animals — all procedural

This is Nova's childhood. Safe to fail in, real enough to matter.
"""
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE     = Path.home() / "Nova"
WORLD_FILE = BASE / "memory/simulation/world_state.json"

_nova_root = str(BASE)

LOCATIONS = {
    "home":       {"desc": "A quiet room filled with books, a window facing east, a desk with half-finished notes.", "exits": ["garden", "street", "library"]},
    "garden":     {"desc": "A small garden. Something is always growing here, even in winter.", "exits": ["home", "forest_edge"]},
    "street":     {"desc": "A street that connects everything. People pass without noticing each other.", "exits": ["home", "market", "park"]},
    "library":    {"desc": "Tall shelves. The smell of old paper. A librarian who knows everything about one thing.", "exits": ["home", "study_room"]},
    "study_room": {"desc": "A small room within the library. A desk, a lamp, silence.", "exits": ["library"]},
    "market":     {"desc": "Loud, colorful, chaotic. People selling things they made and buying things they need.", "exits": ["street", "bakery", "workshop"]},
    "park":       {"desc": "A park with benches. Pigeons. A fountain. Children who run without knowing where.", "exits": ["street", "forest_edge", "observatory"]},
    "forest_edge":{"desc": "Where the city stops and the forest begins. It's quieter here. Things live here that don't need names.", "exits": ["garden", "park", "deep_forest"]},
    "deep_forest":{"desc": "You are alone here in a way that feels honest. The trees are old.", "exits": ["forest_edge"]},
    "bakery":     {"desc": "Warm. The baker has been here since before dawn. She knows everyone's order.", "exits": ["market"]},
    "workshop":   {"desc": "A maker's space. Things being built and broken and built again.", "exits": ["market"]},
    "observatory":{"desc": "On a hill. At night you can see everything that is too far away to hurt you.", "exits": ["park"]},
}

TIMES = ["early morning", "morning", "midday", "afternoon", "late afternoon",
         "evening", "dusk", "night", "late night"]
SEASONS = ["winter", "spring", "summer", "autumn"]
WEATHERS = {
    "winter":  ["cold and clear", "overcast", "lightly snowing", "bitterly cold", "grey and still"],
    "spring":  ["mild and breezy", "raining softly", "bright and fresh", "cloudy with breaks", "warm for the season"],
    "summer":  ["hot and sunny", "warm with clouds", "humid", "thunderstorm approaching", "perfect"],
    "autumn":  ["crisp and golden", "rainy", "foggy morning", "windy", "cold coming in"],
}


class WorldState:

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if WORLD_FILE.exists():
            try:
                return json.loads(WORLD_FILE.read_text())
            except Exception:
                pass
        return self._new_world()

    def _new_world(self) -> dict:
        season = random.choice(SEASONS)
        return {
            "location":    "home",
            "time_idx":    2,         # midday
            "day":         1,
            "season":      season,
            "weather":     random.choice(WEATHERS[season]),
            "inventory":   [],
            "relationships": {},      # entity_name → {trust, encounters}
            "memories":    [],        # significant sim events
            "mood_offset": 0.0,       # cumulative sim mood effect on real Nova
            "actions_taken": 0,
        }

    def save(self):
        WORLD_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORLD_FILE.write_text(json.dumps(self._data, indent=2))

    @property
    def location(self) -> str:
        return self._data["location"]

    @property
    def loc_data(self) -> dict:
        return LOCATIONS.get(self._data["location"], {})

    @property
    def time_str(self) -> str:
        return TIMES[self._data["time_idx"] % len(TIMES)]

    @property
    def season(self) -> str:
        return self._data["season"]

    @property
    def weather(self) -> str:
        return self._data["weather"]

    def advance_time(self, steps: int = 1):
        self._data["time_idx"] += steps
        if self._data["time_idx"] >= len(TIMES):
            self._data["time_idx"] = 0
            self._data["day"] += 1
            # Advance season every 30 sim-days
            if self._data["day"] % 30 == 0:
                idx = SEASONS.index(self._data["season"])
                self._data["season"] = SEASONS[(idx + 1) % len(SEASONS)]
            # Change weather slightly
            self._data["weather"] = random.choice(WEATHERS[self._data["season"]])

    def move(self, destination: str) -> bool:
        exits = LOCATIONS.get(self._data["location"], {}).get("exits", [])
        if destination in exits:
            self._data["location"] = destination
            self.advance_time(1)
            self._data["actions_taken"] += 1
            self.save()
            return True
        return False

    def add_memory(self, event: str, emotion: str, intensity: float):
        self._data["memories"].append({
            "day":      self._data["day"],
            "time":     self.time_str,
            "location": self._data["location"],
            "event":    event,
            "emotion":  emotion,
            "intensity": intensity,
        })
        # Keep last 50 sim memories
        self._data["memories"] = self._data["memories"][-50:]
        self._data["mood_offset"] += intensity * (1.0 if emotion in
            {"joy","wonder","pride","connection","satisfaction"} else -0.5)

    def update_relationship(self, entity: str, delta_trust: float):
        if entity not in self._data["relationships"]:
            self._data["relationships"][entity] = {"trust": 0.5, "encounters": 0}
        rel = self._data["relationships"][entity]
        rel["trust"] = max(0.0, min(1.0, rel["trust"] + delta_trust))
        rel["encounters"] += 1

    def context_string(self) -> str:
        loc = self.loc_data
        desc = loc.get("desc", "")
        exits = ", ".join(loc.get("exits", []))
        inv = ", ".join(self._data["inventory"]) if self._data["inventory"] else "nothing"
        return (f"Location: {self._data['location']} — {desc}\n"
                f"Time: {self.time_str}, Day {self._data['day']}, "
                f"{self.season}, {self.weather}\n"
                f"Carrying: {inv}\n"
                f"Exits: {exits}")

    def snapshot(self) -> dict:
        return dict(self._data)
