"""Anthropic Claude Code adapter."""
from __future__ import annotations

import shlex
from pathlib import Path

from claudeteam.runtime import paths
from claudeteam.util import env_str

from .base import AuthSlots, CliAdapter


def agent_home(agent: str) -> str:
    """Per-agent HOME — the `home/` subdir of the agent's own state dir.

    Defaults to `<state_dir>/agents/<agent>/home`, so each agent's CLI
    dotfiles (`.claude` / `.codex` / `.gemini` / ...) sit in the same tree
    as its `identity.md` + `memory.jsonl` — one directory per agent.

    Set `CLAUDETEAM_AGENT_HOME_ROOT` to relocate the homes onto a separate
    mount (e.g. a Docker volume that persists credentials across image
    rebuilds, or a writable path on macOS where `~` is a read-only
    firmlink); the home is then `<root>/<agent>`.
    """
    root = env_str("CLAUDETEAM_AGENT_HOME_ROOT")
    if root:
        return str(Path(root) / agent)
    return str(paths.agent_dir(agent) / "home")


class ClaudeCodeAdapter(CliAdapter):
    def spawn_cmd(self, agent: str, model: str) -> str:
        # Full silent-launch recipe — bypass-permissions confirm, theme picker, etc.
        # - IS_SANDBOX=1: claude allows --dangerously-skip-permissions
        # - CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1 / DISABLE_AUTOUPDATER=1:
        #   silence survey + autoupdate banners.
        # - HOME=<agent_home>: per-agent home so each pane has its own
        #   ~/.claude.json — multiple panes sharing one config raced into
        #   "JSON Parse error" on restart. Lifecycle materialises the
        #   per-agent .claude/ from the live keychain.
        #
        # Auth (OAuth token / API key, plus the keychain-avoidance trick of
        # feeding the login file's accessToken back in as
        # CLAUDE_CODE_OAUTH_TOKEN) is resolved by runtime.agent_auth and
        # prepended at the spawn site — see its module docstring for the
        # token > login > api_key precedence.
        return (
            f"HOME={shlex.quote(agent_home(agent))} "
            f"CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1 DISABLE_AUTOUPDATER=1 "
            f"IS_SANDBOX=1 claude --dangerously-skip-permissions "
            f"--model {shlex.quote(model)} --name {shlex.quote(agent)}"
        )

    def ready_markers(self) -> list[str]:
        return ["bypass permissions on", "? for shortcuts"]

    def process_name(self) -> str:
        return "claude"

    def auth_slots(self) -> AuthSlots:
        # token (setup-token) > login (.credentials.json, fed back in as the
        # OAuth token to dodge the per-agent-HOME keychain dialog) > api key.
        return AuthSlots(
            token_env="CLAUDE_CODE_OAUTH_TOKEN",
            api_key_envs=("ANTHROPIC_API_KEY",),
            login_credfile=".claude/.credentials.json",
            login_token_env="CLAUDE_CODE_OAUTH_TOKEN",
        )

    def native_memory_reloads(self) -> bool:
        # claude re-reads ~/.claude/CLAUDE.md after /compact, so an on-disk
        # anchor rewrite reaches the running agent without a re-inject.
        return True

    def native_memory_path(self, agent: str) -> str | None:
        # ~/.claude/CLAUDE.md inside the agent's isolated HOME. claude
        # loads this as user-level memory on every session start and
        # re-reads it after /compact, so the agent's identity + remember
        # policy + memory digest survive context compaction. The per-agent
        # HOME means each agent gets its own file — zero cross-agent
        # collision and no project-repo pollution.
        return f"{agent_home(agent)}/.claude/CLAUDE.md"
