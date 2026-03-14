#!/usr/bin/env python3
"""
N.O.V.A Multi-Agent Runner

Spawns specialized sub-agents as async subprocesses.
Agents communicate via the knowledge graph + a shared message bus (JSONL file).

Agent types:
  recon       — light HTTP recon on a target
  research    — research a topic/CVE via nova_research.py
  hypothesize — generate hypotheses from a finding
  summarize   — summarize recent research/findings

Hard limits (from autonomy_guard):
  - Max 3 concurrent agents
  - Each agent has a 5-minute wall-clock timeout
  - All actions respect governance boundaries

Usage:
    from tools.agents.agent_runner import AgentRunner
    runner = AgentRunner()
    runner.dispatch("research", "GitLab SSRF via import", reason="high priority watchlist")
    runner.wait_all()
    results = runner.collect_results()
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE       = Path.home() / "Nova"
AGENTS_DIR = BASE / "memory/agents"
BUS_FILE   = AGENTS_DIR / "message_bus.jsonl"
STATE_FILE = AGENTS_DIR / "agent_state.json"
LOG_FILE   = BASE / "logs/agents.log"

AGENTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

MAX_AGENTS   = 3
AGENT_TIMEOUT = 300  # 5 minutes per agent


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _bus_write(entry: dict):
    """Append one entry to the shared message bus."""
    with open(BUS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _state_load() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"agents": []}


def _state_save(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _state_prune(state: dict) -> dict:
    """Remove finished agents from state."""
    state["agents"] = [a for a in state["agents"] if a.get("status") == "running"]
    return state


class Agent:
    """One running sub-agent."""

    def __init__(self, agent_id: str, agent_type: str, target: str, reason: str = ""):
        self.agent_id   = agent_id
        self.agent_type = agent_type
        self.target     = target
        self.reason     = reason
        self.started_at = datetime.now().isoformat()
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.result: Optional[str] = None
        self.status  = "pending"

    def _cmd(self) -> list[str]:
        py = sys.executable
        nova = str(BASE / "bin/nova")
        if self.agent_type == "research":
            return [py, str(BASE / "bin/nova_research.py"), self.target]
        elif self.agent_type == "recon":
            return [py, nova, "scan", self.target, "--light"]
        elif self.agent_type == "hypothesize":
            # Pass target as JSON finding on stdin (set up by caller)
            return [py, str(BASE / "tools/reasoning/hypothesize.py")]
        elif self.agent_type == "summarize":
            return [py, str(BASE / "bin/nova_memory_summarize.py")]
        elif self.agent_type == "life":
            return [py, str(BASE / "bin/nova_life.py")]
        else:
            return [py, str(BASE / "bin/nova_research.py"), self.target]

    def _run(self):
        try:
            self.status = "running"
            _log(f"[AGENT:{self.agent_id}] starting {self.agent_type} → {self.target}")
            _bus_write({
                "event": "start",
                "agent_id": self.agent_id,
                "type": self.agent_type,
                "target": self.target,
                "ts": self.started_at,
            })

            cmd = self._cmd()
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(BASE),
            )
            try:
                out, err = self.process.communicate(timeout=AGENT_TIMEOUT)
                self.result = (out or "").strip()[-500:] or "(no output)"
                self.status = "done"
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.result = "timeout"
                self.status = "timeout"

            _log(f"[AGENT:{self.agent_id}] {self.status}: {self.result[:100]}")
            _bus_write({
                "event": "done",
                "agent_id": self.agent_id,
                "type": self.agent_type,
                "target": self.target,
                "status": self.status,
                "result": self.result,
                "ts": datetime.now().isoformat(),
            })

            # Push result into knowledge graph
            try:
                _nova_root = str(BASE)
                if _nova_root not in sys.path:
                    sys.path.insert(0, _nova_root)
                from tools.knowledge.graph import node_id_for, add_edge
                a_id = node_id_for("agent", self.agent_id, {
                    "type": self.agent_type, "target": self.target,
                    "status": self.status, "result": self.result[:200],
                })
                t_id = node_id_for("target", self.target, {})
                add_edge(a_id, t_id, "acted_on")
            except Exception:
                pass

        except Exception as e:
            self.status = "error"
            self.result = str(e)
            _log(f"[AGENT:{self.agent_id}] error: {e}")

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def join(self, timeout: float = None):
        if self.thread:
            self.thread.join(timeout=timeout)


class AgentRunner:
    """
    Manages a pool of up to MAX_AGENTS concurrent sub-agents.
    Thread-safe. Results available via collect_results().
    """

    def __init__(self):
        self._agents: list[Agent] = []
        self._lock   = threading.Lock()
        self._seq    = 0

    def _next_id(self) -> str:
        self._seq += 1
        ts = datetime.now().strftime("%H%M%S")
        return f"a{ts}_{self._seq}"

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for a in self._agents if a.is_alive())

    def dispatch(self, agent_type: str, target: str, reason: str = "") -> Optional[Agent]:
        """
        Spawn a new agent if under the cap.
        Returns the Agent, or None if the cap is reached.
        """
        with self._lock:
            alive = [a for a in self._agents if a.is_alive()]
            if len(alive) >= MAX_AGENTS:
                _log(f"[RUNNER] cap reached ({MAX_AGENTS}), queuing {agent_type}:{target}")
                return None

            agent = Agent(self._next_id(), agent_type, target, reason)
            self._agents.append(agent)
            agent.start()
            return agent

    def wait_all(self, timeout: float = AGENT_TIMEOUT):
        """Block until all agents finish or timeout."""
        deadline = time.monotonic() + timeout
        for a in self._agents:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            a.join(timeout=remaining)

    def collect_results(self) -> list[dict]:
        """Return results from all completed agents."""
        results = []
        for a in self._agents:
            if not a.is_alive():
                results.append({
                    "agent_id":   a.agent_id,
                    "type":       a.agent_type,
                    "target":     a.target,
                    "reason":     a.reason,
                    "status":     a.status,
                    "result":     a.result,
                    "started_at": a.started_at,
                })
        return results

    def status_report(self) -> dict:
        alive = [a for a in self._agents if a.is_alive()]
        done  = [a for a in self._agents if not a.is_alive()]
        return {
            "running": len(alive),
            "done":    len(done),
            "agents":  [
                {"id": a.agent_id, "type": a.agent_type,
                 "target": a.target, "status": a.status}
                for a in self._agents
            ]
        }
