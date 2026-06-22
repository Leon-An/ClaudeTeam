"""Live agent state classification from a tmux pane capture buffer.

`/team` and friends use this to surface what each agent is *actually*
doing right now (not just whatever they upserted into status.json).
The classifier is content-aware: looks at trailing prompts, working
spinners, compacting markers, etc.

The emoji/brief vocabulary here is the single source of truth for pane
state, so operators see a consistent label wherever a pane is surfaced
(`/team`, `peek`, …).
"""
from __future__ import annotations

import re


_BASH_PROMPT_RE = re.compile(r"root@[0-9a-f]+:[^#]*#\s*$")
_PERM_PROMPT_RE = re.compile(r"❯\s*\d\.")
_BYPASS_RE = re.compile(r"⏵⏵\s*bypass permissions")
_WORK_TIME_RE = re.compile(r"\((\d+m\s*\d+s|\d+s)(?:\s*·[^)]*)?\)")
# Codex idle: status line shows "gpt-5.5 default · ~/path" or
# "permissions: YOLO" inside the boxed banner.
_CODEX_IDLE_RE = re.compile(r"\b(?:gpt-\d|o1|o3|o4|codex)\S*\s+default\b")
# Kimi idle: ready markers from adapter — "context:" line or "── input"
_KIMI_IDLE_RE = re.compile(r"context:\s*[\d.]+%|── input|Send /help for help")
# Gemini / Qwen (Ink) idle: the ready cursor (`Gemini>` / `qwen>`) sits at the
# tail when waiting for input; qwen's welcome banner shows "Type your request".
# These mirror the gemini/qwen adapters' declared ready_markers — without them
# a healthy idle gemini/qwen pane fell through to 🔘 and falsely painted the
# /team card yellow.
_GEMINI_QWEN_IDLE_RE = re.compile(r"(?i)(?:gemini|qwen)\s*>\s*$")


def parse(buf: str) -> tuple[str, str]:
    """Classify a tmux pane capture into (emoji, brief).

    Returns the shared pane-state vocabulary:
      ⬜ no window / empty buffer
      🛑 CLI not running (back to bash)
      ⚠️ awaiting permission prompt
      🗜️ compacting context
      🔄 working / thinking (with elapsed time when available)
      💤 idle (CLI ready, no active task)
      🔘 unknown — show last non-empty line tail
    """
    if not buf:
        return ("⬜", "no window")
    low = buf.lower()
    tail_lines = [line for line in buf.splitlines() if line.strip()]
    tail = tail_lines[-1] if tail_lines else ""

    if _BASH_PROMPT_RE.search(tail):
        return ("🛑", "CLI not running (bash)")
    if "do you want to proceed" in low or _PERM_PROMPT_RE.search(buf):
        return ("⚠️", "awaiting permission")
    if "compacting conversation" in low or "compacting…" in low:
        return ("🗜️", "compacting")
    if "esc to interrupt" in low:
        m = _WORK_TIME_RE.search(buf)
        return ("🔄", f"working {m.group(1) if m else ''}".strip())
    if "manifesting" in low:
        return ("🔄", "thinking")
    if _BYPASS_RE.search(buf) or "new task?" in low:
        return ("💤", "idle")
    if "permissions: yolo" in low or _CODEX_IDLE_RE.search(buf):
        return ("💤", "idle")
    if _KIMI_IDLE_RE.search(buf):
        return ("💤", "idle")
    if _GEMINI_QWEN_IDLE_RE.search(tail) or "type your request" in low:
        return ("💤", "idle")
    return ("🔘", tail.strip()[:40])
