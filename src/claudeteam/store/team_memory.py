"""Team-shared experience — durable lessons the whole team reads and writes.

Distinct from per-agent `memory.py` (each agent's own notes) and from
`local_facts` logs (the raw audit trail): this is the *one* pool of
distilled team experience — conventions, gotchas, cross-agent decisions —
injected into every agent's wake prompt so hard-won lessons aren't
relearned per agent.

One append-only file: `<state_dir>/share/experience.jsonl`. Each entry:
  {kind, content, by, ref?, created_at}
`kind` reuses `memory.KNOWN_KINDS`; `by` records the contributing agent.

API mirrors the per-agent store but takes no `agent` key (the pool is
shared):
  `append(content, *, kind, by, ref)`   → write 1 entry
  `list_recent(*, limit=30)`            → list, oldest-first
  `clear()`                             → drop all entries
  `render_for_prompt(*, limit=20)`      → markdown for the wake prompt
"""
from __future__ import annotations

import json

from claudeteam.runtime import paths
from claudeteam.util import flock, now_ms, read_jsonl


_MAX = 300  # default cap; override via tunable share.max_experience


def _max() -> int:
    """Retention cap for the shared pool. Larger than the per-agent cap
    since it serves the whole team; tunable `share.max_experience`."""
    try:
        from claudeteam.runtime import tunables
        return max(1, int(tunables.tunable("share.max_experience", _MAX)))
    except Exception:
        return _MAX


def _file():
    return paths.share_dir() / "experience.jsonl"


def append(content: str, *, kind: str = "note", by: str = "",
           ref: str = "") -> dict:
    """Append one team-experience entry; returns the persisted record.

    fcntl-locked so concurrent writers from different panes don't
    interleave bytes. Truncates from the front past the cap, same as the
    per-agent store."""
    entry = {
        "kind": str(kind),
        "content": str(content or ""),
        "by": str(by or ""),
        "ref": str(ref or ""),
        "created_at": now_ms(),
    }
    paths.share_dir().mkdir(parents=True, exist_ok=True)
    path = _file()
    with flock(paths.share_dir() / ".experience.lock"):
        rows = read_jsonl(path)
        rows.append(entry)
        cap = _max()
        if len(rows) > cap:
            rows = rows[-cap:]
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
    return entry


def list_recent(*, limit: int = 30) -> list[dict]:
    """Return up to `limit` most recent entries, oldest-first."""
    return read_jsonl(_file())[-limit:]


def clear() -> int:
    """Wipe the shared experience file. Returns the number of dropped entries."""
    path = _file()
    if not path.exists():
        return 0
    n = sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
    path.unlink()
    return n


def render_for_prompt(*, limit: int = 20) -> str:
    """Format the shared experience as a markdown block for the wake
    prompt. Empty → empty string (callers branch on `if block:`)."""
    rows = list_recent(limit=limit)
    if not rows:
        return ""
    lines = ["## 团队共享经验（全队可见）"]
    for r in rows:
        by = f" (@{r['by']})" if r.get("by") else ""
        ref = f" (ref={r['ref']})" if r.get("ref") else ""
        lines.append(f"- [{r.get('kind', '?')}] {r.get('content', '')}{by}{ref}")
    return "\n".join(lines)
