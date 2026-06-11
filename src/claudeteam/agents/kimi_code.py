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
