"""Anthropic Claude Code adapter."""
from __future__ import annotations

import json
import shlex
from pathlib import Path

from claudeteam.runtime import paths
from claudeteam.util import env_str

from .base import CliAdapter


def _read_oauth_token(agent: str) -> str | None:
    """Read the access token from the per-agent .credentials.json.

    Returns None if the file is missing or its shape doesn't match what
    claude writes. Best-effort: we'd rather spawn claude without the env
    var (and let it fall back to keychain) than crash the pane on a
    parse error.
    """
    cred = Path(agent_home(agent)) / ".claude" / ".credentials.json"
    if not cred.exists():
        return None
    try:
        data = json.loads(cred.read_text())
        token = data.get("claudeAiOauth", {}).get("accessToken")
        return token if isinstance(token, str) and token else None
    except (OSError, json.JSONDecodeError):
        return None


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
        #   per-agent .claude/ from the live keychain (regular file, not
        #   symlink — claude's atomic-write replaces a symlink anyway).
        # - CLAUDE_CODE_OAUTH_TOKEN: hand claude the access token directly
        #   so it never asks the OS keychain. With per-agent HOME, claude's
        #   keychain *write* path on token refresh would otherwise pop the
        #   macOS "Keychain Not Found — Reset To Defaults" dialog (the
        #   storage keychain selection fails because the agent's HOME is
        #   off the user's login session). Pulling the token from
        #   ~/.claude/.credentials.json (lifecycle just refreshed it from
        #   keychain) and threading it through env keeps claude in
        #   file-only auth mode for the lifetime of the pane.
        oauth_token = _read_oauth_token(agent)
        token_prefix = (f"CLAUDE_CODE_OAUTH_TOKEN={shlex.quote(oauth_token)} "
                        if oauth_token else "")
        return (
            f"HOME={agent_home(agent)} "
            f"{token_prefix}"
            f"CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1 DISABLE_AUTOUPDATER=1 "
            f"IS_SANDBOX=1 claude --dangerously-skip-permissions "
            f"--model {model} --name {agent}"
        )

    def ready_markers(self) -> list[str]:
        return ["bypass permissions on", "? for shortcuts"]

    def process_name(self) -> str:
        return "claude"

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
