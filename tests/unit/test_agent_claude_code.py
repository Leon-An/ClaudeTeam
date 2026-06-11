"""Tests for Claude Code adapter — lifecycle and configuration.

Covers:
  - spawn_cmd shape and env vars
  - ready_markers / busy_markers / rate_limit_markers content
  - process_name
  - submit_keys (default Enter-based)
  - agent_home resolution (cached writable probe)
  - _read_oauth_token with missing/corrupt credentials
  - _data_writable caching behavior
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from helpers import env_patch
from claudeteam.agents.claude_code import (
    ClaudeCodeAdapter,
    _data_writable,
    _read_oauth_token,
    agent_home,
)
from claudeteam.agents.base import CliAdapter


# ── adapter instance ──────────────────────────────────────────────


def _adapter() -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter()


# ── spawn_cmd ─────────────────────────────────────────────────────


def test_spawn_cmd_contains_claude_bare():
    cmd = _adapter().spawn_cmd("worker_cc", "sonnet")
    assert "claude" in cmd
    assert "--bare" in cmd


def test_spawn_cmd_includes_model_flag():
    cmd = _adapter().spawn_cmd("w", "opus-4")
    assert "--model opus-4" in cmd


def test_spawn_cmd_includes_agent_name():
    cmd = _adapter().spawn_cmd("my_agent", "sonnet")
    assert "--name my_agent" in cmd


def test_spawn_cmd_disables_feedback_and_autoupdate():
    cmd = _adapter().spawn_cmd("w", "sonnet")
    assert "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1" in cmd
    assert "DISABLE_AUTOUPDATER=1" in cmd


def test_spawn_cmd_sets_home_to_agent_home():
    cmd = _adapter().spawn_cmd("w", "sonnet")
    assert "HOME=" in cmd
    # HOME should point to agent_home("w")
    expected = agent_home("w")
    assert f"HOME={expected}" in cmd


def test_spawn_cmd_includes_mimo_env_when_set():
    """ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY are injected when set."""
    with env_patch(
        ANTHROPIC_BASE_URL="https://example.com/v1",
        ANTHROPIC_API_KEY="sk-test-123",
    ):
        cmd = _adapter().spawn_cmd("w", "sonnet")
        assert "ANTHROPIC_BASE_URL=https://example.com/v1" in cmd
        assert "ANTHROPIC_API_KEY=sk-test-123" in cmd


def test_spawn_cmd_omits_mimo_env_when_unset():
    with env_patch(ANTHROPIC_BASE_URL=None, ANTHROPIC_API_KEY=None):
        cmd = _adapter().spawn_cmd("w", "sonnet")
        assert "ANTHROPIC_BASE_URL" not in cmd
        assert "ANTHROPIC_API_KEY" not in cmd


# ── markers ───────────────────────────────────────────────────────


def test_ready_markers_nonempty():
    markers = _adapter().ready_markers()
    assert len(markers) > 0
    assert all(isinstance(m, str) for m in markers)


def test_ready_markers_include_shortcuts_hint():
    markers = _adapter().ready_markers()
    assert any("shortcuts" in m for m in markers)


def test_busy_markers_include_spinners():
    markers = _adapter().busy_markers()
    assert len(markers) > 0
    # Should include at least one spinner char
    from claudeteam.agents.base import SPINNER_CHARS
    assert any(s in markers for s in SPINNER_CHARS)


def test_busy_markers_include_thinking():
    markers = _adapter().busy_markers()
    assert "Thinking" in markers


def test_busy_markers_include_running_tool():
    markers = _adapter().busy_markers()
    assert "Running tool" in markers


def test_process_name_is_claude():
    assert _adapter().process_name() == "claude"


def test_submit_keys_default_enter_based():
    keys = _adapter().submit_keys()
    assert "Enter" in keys


def test_rate_limit_markers_nonempty():
    markers = _adapter().rate_limit_markers()
    assert len(markers) > 0
    assert any("limit" in m.lower() for m in markers)


# ── agent_home ────────────────────────────────────────────────────


def test_agent_home_returns_string():
    home = agent_home("test_agent")
    assert isinstance(home, str)
    assert "test_agent" in home


def test_agent_home_contains_agent_name():
    home = agent_home("worker_cc")
    assert "worker_cc" in home


# ── _read_oauth_token ─────────────────────────────────────────────


def test_read_oauth_token_returns_none_when_no_creds_file():
    """No .credentials.json → returns None, no crash."""
    import claudeteam.agents.claude_code as cc_mod
    from helpers import attr_patch
    with tempfile.TemporaryDirectory() as tmp:
        with attr_patch(cc_mod, agent_home=lambda a: tmp):
            result = _read_oauth_token("test_agent")
            assert result is None


def test_read_oauth_token_returns_none_on_corrupt_json():
    """Corrupt JSON in credentials file → returns None gracefully."""
    import claudeteam.agents.claude_code as cc_mod
    from helpers import attr_patch
    with tempfile.TemporaryDirectory() as tmp:
        cred_dir = Path(tmp) / ".claude"
        cred_dir.mkdir()
        (cred_dir / ".credentials.json").write_text("not valid json{{{")
        with attr_patch(cc_mod, agent_home=lambda a: tmp):
            result = _read_oauth_token("test_agent")
            assert result is None


def test_read_oauth_token_extracts_access_token():
    """Valid credentials file → returns the access token string."""
    import claudeteam.agents.claude_code as cc_mod
    from helpers import attr_patch
    with tempfile.TemporaryDirectory() as tmp:
        cred_dir = Path(tmp) / ".claude"
        cred_dir.mkdir()
        creds = {
            "claudeAiOauth": {
                "accessToken": "test-token-abc-123",
                "refreshToken": "refresh-xyz",
            }
        }
        (cred_dir / ".credentials.json").write_text(json.dumps(creds))
        # Patch agent_home to return tmp so _read_oauth_token finds our file
        with attr_patch(cc_mod, agent_home=lambda a: tmp):
            result = _read_oauth_token("test_agent")
            assert result == "test-token-abc-123"


# ── interface compliance ──────────────────────────────────────────


def test_adapter_is_cli_adapter_subclass():
    assert isinstance(_adapter(), CliAdapter)


def test_spawn_cmd_returns_nonempty_string():
    cmd = _adapter().spawn_cmd("any_agent", "any_model")
    assert isinstance(cmd, str)
    assert len(cmd.strip()) > 0
