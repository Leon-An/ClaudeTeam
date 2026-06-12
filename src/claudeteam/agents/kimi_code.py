"""Moonshot Kimi Code adapter."""
from __future__ import annotations

from .base import CliAdapter, MULTILINE_SUBMIT_KEYS, SPINNER_CHARS


class KimiCodeAdapter(CliAdapter):
    def spawn_cmd(self, agent: str, model: str) -> str:
        # model is currently a no-op for kimi; CLI picks per its config
        return f"DISABLE_UPDATE_CHECK=1 KIMI_AGENT={agent} kimi --yolo"

    def display_model(self, model: str) -> str:
        # model is a no-op for kimi (see spawn_cmd) — it runs whatever its
        # own config selects, so don't label the agent with the team alias.
        return "kimi 自身配置"

    def native_memory_path(self, agent: str) -> str | None:
        # Deliberately no native memory file (stays the base None).
        #
        # Unlike codex/gemini/qwen, kimi has no HOME-global memory file —
        # it only loads AGENTS.md by walking the git-root→cwd chain. Giving
        # each pane an isolated, non-colliding AGENTS.md would mean moving
        # the pane's cwd off the real repo into a per-agent dir (+ --add-dir
        # the repo back), which is a real UX regression for a coding agent
        # (relative paths / ls / git default to an empty home).
        #
        # So kimi keeps cwd = repo and skips the native file. The intent
        # anchor still reaches it via the one-shot init prompt; kimi writes
        # that startup-rendered system prompt back into context after its
        # own /compact, so the anchor survives compaction. Mid-session
        # task-change refresh is handled by the reidentify fallback shared
        # with codex/qwen (none of which re-read a disk file either).
        return None

    def ready_markers(self) -> list[str]:
        return [
            "Welcome to Kimi Code CLI",
            "Send /help for help information",
            "── input",
            "context:",
        ]

    def busy_markers(self) -> list[str]:
        return [*SPINNER_CHARS, "Thinking", "Using Shell", "Booting"]

    def process_name(self) -> str:
        return "kimi"

    def submit_keys(self) -> list[str]:
        return list(MULTILINE_SUBMIT_KEYS)
