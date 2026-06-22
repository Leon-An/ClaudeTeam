"""Tests for runtime/agent_reaper.py — detect + respawn dead agent CLIs."""
from __future__ import annotations

from claudeteam.runtime import agent_reaper, tmux


_BASH = "root@abc123:/app# "                 # pane_state -> 🛑 (CLI exited)
_READY = "...\n⏵⏵ bypass permissions on\n"   # -> 💤 (alive, idle)
_BUSY = "...\nesc to interrupt (1m · ↓ 99 tokens)\n"   # -> 🔄 (alive, working)


def _cap(buffers: dict):
    """Fake capture_pane keyed by window name."""
    return lambda target, lines=40: buffers.get(target.window, "")


# ── find_dead_agents ─────────────────────────────────────────────


def test_flags_only_bash_prompt_panes():
    buffers = {"worker_cc": _BASH, "manager": _READY, "worker_x": _BUSY}
    dead = agent_reaper.find_dead_agents(
        ["manager", "worker_cc", "worker_x"], session="S", capture=_cap(buffers))
    assert dead == ["worker_cc"]            # only the exited-to-shell pane


def test_skips_lazy_agents():
    """A never-woken lazy agent is also a bare shell — must not be respawned."""
    buffers = {"worker_lazy": _BASH}
    dead = agent_reaper.find_dead_agents(
        ["worker_lazy"], session="S", capture=_cap(buffers),
        lazy=frozenset({"worker_lazy"}))
    assert dead == []


def test_skips_retired_agents():
    buffers = {"worker_fired": _BASH}
    dead = agent_reaper.find_dead_agents(
        ["worker_fired"], session="S", capture=_cap(buffers),
        is_retired=lambda a: a == "worker_fired")
    assert dead == []


def test_skips_auth_screen_to_avoid_respawn_loop():
    """A shell pane showing a login/auth prompt is left alone — a respawn
    can't fix expired creds and would just loop."""
    buffers = {"worker_cc": _BASH + "\nNot logged in — run /login\n"}
    dead = agent_reaper.find_dead_agents(
        ["worker_cc"], session="S", capture=_cap(buffers))
    assert dead == []


# ── reap (respawn + cooldown) ────────────────────────────────────


def test_reap_respawns_dead_and_records_time():
    respawned = []
    last: dict = {}
    out = agent_reaper.reap(
        ["worker_cc"], session="S",
        capture=_cap({"worker_cc": _BASH}),
        respawn=lambda a: respawned.append(a) or True,
        last_respawn=last, now=lambda: 1000.0, log=lambda _m: None)
    assert out == ["worker_cc"]
    assert respawned == ["worker_cc"]
    assert last["worker_cc"] == 1000.0


def test_reap_skips_within_cooldown():
    respawned = []
    last = {"worker_cc": 1000.0}
    out = agent_reaper.reap(
        ["worker_cc"], session="S",
        capture=_cap({"worker_cc": _BASH}),
        respawn=lambda a: respawned.append(a) or True,
        cooldown_s=300.0, last_respawn=last,
        now=lambda: 1200.0,            # only 200s later — still cooling down
        log=lambda _m: None)
    assert out == []
    assert respawned == []


def test_reap_respawns_again_after_cooldown_elapses():
    last = {"worker_cc": 1000.0}
    out = agent_reaper.reap(
        ["worker_cc"], session="S",
        capture=_cap({"worker_cc": _BASH}),
        respawn=lambda a: True,
        cooldown_s=300.0, last_respawn=last,
        now=lambda: 1400.0,            # 400s later — past cooldown
        log=lambda _m: None)
    assert out == ["worker_cc"]
    assert last["worker_cc"] == 1400.0


def test_reap_swallows_respawn_failure():
    def boom(_a):
        raise RuntimeError("spawn blew up")
    out = agent_reaper.reap(
        ["worker_cc"], session="S",
        capture=_cap({"worker_cc": _BASH}),
        respawn=boom, last_respawn={}, now=lambda: 1.0, log=lambda _m: None)
    assert out == []                   # error swallowed, no crash
