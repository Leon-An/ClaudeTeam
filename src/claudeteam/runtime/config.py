"""Team and runtime configuration.

Two files:
  team.json       — static team layout (which agents, which CLI, which model)
  runtime_config.json — per-deployment runtime values (chat_id, lark profile)

Both paths come from env so tests get isolation by setting CLAUDETEAM_TEAM_FILE
and CLAUDETEAM_RUNTIME_CONFIG.

Schema (team.json):
    {
      "session": "ClaudeTeam",
      "agents": {
        "manager":      {"cli": "claude-code", "model": "opus", "role": "..."},
        "worker_cc":    {"cli": "claude-code", "model": "sonnet"},
        "worker_codex": {"cli": "codex-cli",   "model": "gpt-5.5"},
        "worker_kimi":  {"cli": "kimi-code"}
      },
      "default_model": "opus"
    }

Reading is no-cache (re-read on every call) so editing team.json picks up
without restart.  Writes are explicit via save_runtime_config().
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from claudeteam.util import env_path, env_str, read_json, write_json

# ── path resolution ───────────────────────────────────────────────


def team_file() -> Path:
    return env_path("CLAUDETEAM_TEAM_FILE") or Path.cwd() / "team.json"


def runtime_config_file() -> Path:
    return env_path("CLAUDETEAM_RUNTIME_CONFIG") or Path.cwd() / "runtime_config.json"


# ── team.json ────────────────────────────────────────────────────


_DEFAULT_TEAM: dict = {"session": "ClaudeTeam", "agents": {}, "default_model": "opus"}


def _read_json_lenient(path: Path, default: dict, label: str) -> dict:
    """Like util.read_json but degrades gracefully on parse / I/O errors —
    prints a stderr warning and returns the default dict instead of
    raising. Used at config load points where a malformed or unreadable
    team.json / runtime_config.json shouldn't kill every claudeteam
    command; the operator sees the warning + can still run
    `claudeteam health` to get a structured corruption report.

    Catches:
      - JSONDecodeError: file present but not valid JSON
      - OSError: PermissionError, file vanished mid-read, encoding
        errors. Ditto for "cannot access this config file"; CLI
        should still answer.
    """
    try:
        return read_json(path, dict(default))
    except json.JSONDecodeError as e:
        print(f"  ⚠️ {label} ({path}) is not valid JSON: {e}", file=sys.stderr)
    except OSError as e:
        print(f"  ⚠️ {label} ({path}) unreadable: {e}", file=sys.stderr)
    return dict(default)


_TEAM_CACHE: tuple[float, tuple[float, float], dict] | None = None  # (expires_at, (toml_mtime, json_mtime), data)
_TEAM_CACHE_TTL_S = 5.0  # 5-second TTL for hot-path callers (slash handlers)


def _config_mtimes() -> tuple[float, float]:
    """Return (toml_mtime, json_mtime) for both config files.
    Returns 0 for any file that doesn't exist. Both are checked so that
    a newly-created TOML file (same mtime as existing JSON) is detected."""
    from claudeteam.runtime import paths
    cf = paths.config_file()
    toml_mtime = 0.0
    try:
        toml_mtime = cf.stat().st_mtime
    except FileNotFoundError:
        pass
    tf = team_file()
    json_mtime = 0.0
    try:
        json_mtime = tf.stat().st_mtime
    except FileNotFoundError:
        pass
    return (toml_mtime, json_mtime)


def load_team() -> dict:
    """Return team config in legacy shape `{session, agents, default_model}`.

    Prefers `claudeteam.toml` `[team]` section; falls back to legacy
    `team.json` so existing deployments keep working until they migrate
    via `claudeteam init --upgrade`.

    Result is cached with a 5-second TTL AND dual-mtime check: if either
    config file's mtime changes (live edit), the cache is invalidated
    immediately regardless of TTL. Both files are tracked because a
    newly-created TOML may have the same mtime as the existing JSON
    (filesystem granularity), and we need to detect the file appearing.
    """
    import time

    global _TEAM_CACHE
    now = time.monotonic()
    current_mtimes = _config_mtimes()
    if _TEAM_CACHE is not None:
        expires_at, cached_mtimes, data = _TEAM_CACHE
        if now < expires_at and cached_mtimes == current_mtimes:
            return data

    from claudeteam.runtime import tunables

    toml_team = tunables.load().get("team")
    if isinstance(toml_team, dict) and toml_team:
        result = {
            "session": toml_team.get("session", "ClaudeTeam"),
            "agents": dict(toml_team.get("agents", {})),
            "default_model": toml_team.get("default_model", "opus"),
        }
    else:
        result = _read_json_lenient(team_file(), _DEFAULT_TEAM, "team.json")
    _TEAM_CACHE = (now + _TEAM_CACHE_TTL_S, current_mtimes, result)
    return result


def reset_cache() -> None:
    """Clear the load_team TTL cache. Tests call this between cases that
    modify team.json / claudeteam.toml so stale data doesn't leak."""
    global _TEAM_CACHE
    _TEAM_CACHE = None


def session_name() -> str:
    return load_team().get("session", "ClaudeTeam")


def agent_names() -> list[str]:
    return sorted(load_team().get("agents", {}))


def agent_config(agent: str) -> dict:
    """Return the per-agent dict from team.json. Raises KeyError on miss."""
    agents = load_team().get("agents", {})
    if agent not in agents:
        raise KeyError(f"agent {agent!r} not in team.json")
    return dict(agents[agent])


def agent_cli(agent: str) -> str:
    """Return the CLI identifier for an agent (defaults to 'claude-code')."""
    return agent_config(agent).get("cli", "claude-code")


def agent_model(agent: str) -> str:
    """Resolve model: agent-specific → CLAUDETEAM_DEFAULT_MODEL → team default → 'opus'."""
    cfg = agent_config(agent)
    return cfg.get("model") or env_str("CLAUDETEAM_DEFAULT_MODEL") or load_team().get("default_model", "opus")


# ── runtime_config.json ──────────────────────────────────────────


def load_runtime_config() -> dict:
    return _read_json_lenient(runtime_config_file(), {}, "runtime_config.json")


def save_runtime_config(cfg: dict) -> None:
    write_json(runtime_config_file(), cfg)


def chat_id() -> str:
    """Prefer claudeteam.toml `chat_id` (top-level), fall back to legacy
    runtime_config.json."""
    from claudeteam.runtime import tunables

    toml_val = tunables.load().get("chat_id")
    if toml_val:
        return str(toml_val)
    return load_runtime_config().get("chat_id", "")


def lark_profile() -> str:
    """Resolve the lark-cli profile name. Priority: env > toml > legacy json."""
    if env := env_str("LARK_CLI_PROFILE"):
        return env
    from claudeteam.runtime import tunables

    toml_val = tunables.load().get("lark_profile")
    if toml_val is not None:
        return str(toml_val)
    return load_runtime_config().get("lark_profile", "")
