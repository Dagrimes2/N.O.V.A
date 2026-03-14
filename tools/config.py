#!/usr/bin/env python3
"""
N.O.V.A Centralized Configuration Loader.

Usage:
    from tools.config import cfg

    model   = cfg.model("reasoning")
    temp    = cfg.temperature("creative")
    timeout = cfg.timeout("heavy")
    url     = cfg.ollama_url
"""
import os, json
from pathlib import Path
from functools import lru_cache

try:
    import yaml
    _YAML = True
except ImportError:
    _YAML = False

CONFIG_PATH = Path.home() / "Nova/config/models.yaml"

# Fallback defaults if YAML unavailable or file missing
_DEFAULTS = {
    "models": {
        "reasoning":        "gemma2:2b",
        "general":          "gemma2:2b",
        "creative":         "gemma2:2b",
        "code":             "gemma2:2b",
        "vision":           "moondream:latest",
        "autonomous":       "gemma2:2b",
        "gan_generator":    "gemma2:2b",
        "gan_discriminator":"gemma2:2b",
    },
    "temperatures": {
        "reasoning":  0.1,
        "triage":     0.1,
        "balanced":   0.4,
        "autonomous": 0.7,
        "creative":   0.85,
        "summarize":  0.3,
    },
    "timeouts": {
        "fast":     60,
        "standard": 180,
        "heavy":    300,
        "dream":    600,
    },
    "ollama_url": "http://localhost:11434/api/generate",
}


@lru_cache(maxsize=1)
def _load() -> dict:
    if _YAML and CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return _DEFAULTS


class _Config:
    """Thin wrapper providing typed accessors for the config dict."""

    def model(self, role: str) -> str:
        """Return model name for a given role.
        Env var NOVA_MODEL overrides reasoning/general roles.
        Env var NOVA_MODEL_<ROLE> overrides specific roles.
        """
        env_specific = os.getenv(f"NOVA_MODEL_{role.upper()}")
        if env_specific:
            return env_specific
        env_global = os.getenv("NOVA_MODEL")
        if env_global and role in ("reasoning", "general", "autonomous"):
            return env_global
        return _load().get("models", {}).get(role, "gemma2:2b")

    def temperature(self, style: str) -> float:
        return float(_load().get("temperatures", {}).get(style, 0.5))

    def timeout(self, size: str) -> int:
        return int(_load().get("timeouts", {}).get(size, 180))

    @property
    def ollama_url(self) -> str:
        return _load().get("ollama_url", "http://localhost:11434/api/generate")

    def reload(self):
        """Force config reload (clears lru_cache)."""
        _load.cache_clear()

    def dump(self) -> dict:
        return _load()


cfg = _Config()


# ── CLI: nova config models ───────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    data = _load()
    print("\nN.O.V.A Model Configuration\n")

    print("  Models:")
    for role, model in data.get("models", {}).items():
        override = os.getenv(f"NOVA_MODEL_{role.upper()}", "")
        flag = f"  ← overridden by env" if override else ""
        print(f"    {role:<22} {model}{flag}")

    print("\n  Temperatures:")
    for style, temp in data.get("temperatures", {}).items():
        print(f"    {style:<22} {temp}")

    print("\n  Timeouts (seconds):")
    for size, secs in data.get("timeouts", {}).items():
        print(f"    {size:<22} {secs}")

    print(f"\n  Ollama: {data.get('ollama_url')}\n")
