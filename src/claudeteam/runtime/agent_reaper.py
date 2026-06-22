"""Respawn agents whose CLI has exited.

The watchdog supervises the router daemon but NOT the agent CLIs running in
tmux panes. When an agent's CLI exits (crash, rate-limit, OOM, network
blip), its pane drops to a bare shell and stays dead until the next message
lazily wakes it — to a watching operator the agent "exited on its own". This
module lets the watchdog detect that and bring the agent back proactively.

Conservative by design (a wrong respawn is worse than a late one):
  - Only the unambiguous "CLI gone → bash prompt" pane state (pane_state 🛑)
    triggers a respawn; the ambiguous tail-fallback state (🔘) does not.
  - A pane showing a login/auth screen is left alone — respawning can't fix
    expired credentials and would just loop.
  - Lazy (a never-woken placeholder also shows a bare shell) and retired
    (fired) agents are skipped.
  - A per-agent cooldown prevents respawn thrashing.
"""
from __future__ import annotations

import time
from typing import Callable

from claudeteam.runtime import tmux


# Login / auth screens — respawning won't fix expired creds, would just loop.
_AUTH_MARKERS = (
    "not logged in", "/login", "please log in", "log in to", "sign in",
    "authenticate", "authentication", "token expired", "401", "unauthorized",
    "需要登录", "重新登录", "请登录",
)


def _looks_like_auth(buf: str) -> bool:
    low = buf.lower()
    return any(m in low for m in _AUTH_MARKERS)


def find_dead_agents(agents, *, session: str,
                     capture: Callable | None = None,
                     is_retired: Callable[[str], bool] | None = None,
                     lazy=frozenset()) -> list[str]:
    """Agents whose CLI is gone (pane sitting at a bare shell prompt),
    excluding lazy / retired agents and panes showing an auth screen."""
    from claudeteam.feishu import pane_state   # lazy: keep import light
    capture = capture or tmux.capture_pane
    dead = []
    for a in agents:
        if a in lazy:
            continue
        if is_retired is not None and is_retired(a):
            continue
        buf = capture(tmux.Target(session, a), lines=40)
        emoji, _ = pane_state.parse(buf)
        if emoji != "🛑":                  # only the clear 'CLI exited' state
            continue
        if _looks_like_auth(buf):           # don't loop-respawn on auth failure
            continue
        dead.append(a)
    return dead


def reap(agents, *, session: str, respawn: Callable[[str], bool],
         cooldown_s: float = 300.0,
         last_respawn: dict | None = None,
         now: Callable[[], float] | None = None,
         capture: Callable | None = None,
         is_retired: Callable[[str], bool] | None = None,
         lazy=frozenset(),
         log: Callable[[str], None] = print) -> list[str]:
    """Respawn dead agents that are past their per-agent cooldown.

    `last_respawn` is a dict mutated in place (agent → last respawn time);
    the caller keeps it across cycles so the cooldown survives. Returns the
    names respawned this call. `respawn(agent) -> bool` does the actual
    rebuild (True on success)."""
    now = now or time.monotonic
    last_respawn = last_respawn if last_respawn is not None else {}
    out = []
    for a in find_dead_agents(agents, session=session, capture=capture,
                              is_retired=is_retired, lazy=lazy):
        t = now()
        prev = last_respawn.get(a)
        if prev is not None and (t - prev) < cooldown_s:
            log(f"  ⏳ {a} dead but within respawn cooldown "
                f"({cooldown_s:.0f}s) — leaving for lazy-wake")
            continue
        last_respawn[a] = t
        try:
            if respawn(a):
                out.append(a)
                log(f"  ♻️  respawned dead agent {a}")
            else:
                log(f"  ⚠️ respawn {a} returned failure")
        except Exception as e:
            log(f"  ⚠️ respawn {a} raised: {e}")
    return out
