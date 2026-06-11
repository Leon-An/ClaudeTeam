"""Tests for the CLI adapter registry + each adapter's spawn / markers contract."""
from __future__ import annotations

from claudeteam.agents import get_adapter, known_clis
from claudeteam.agents.base import CliAdapter
from claudeteam.agents.claude_code import ClaudeCodeAdapter
from claudeteam.agents.codex_cli import CodexCliAdapter
from claudeteam.agents.kimi_code import KimiCodeAdapter
from claudeteam.agents.gemini_cli import GeminiCliAdapter
from claudeteam.agents.qwen_code import QwenCodeAdapter


# ── registry ──────────────────────────────────────────────────────


def test_registry_lists_known_clis_plus_kimi_and_qwen_aliases():
    """Round-85 added gemini-cli; round-101 added qwen-code (+qwen-cli
    alias). kimi-cli + qwen-cli are aliases so both forms in team.json
    work."""
    names = set(known_clis())
    assert names == {
        "claude-code", "codex-cli", "gemini-cli",
        "kimi-code", "kimi-cli",
        "qwen-code", "qwen-cli",
    }


def test_get_adapter_returns_matching_concrete_type():
    assert isinstance(get_adapter("claude-code"), ClaudeCodeAdapter)
    assert isinstance(get_adapter("codex-cli"), CodexCliAdapter)
    assert isinstance(get_adapter("kimi-code"), KimiCodeAdapter)


def test_kimi_alias_returns_same_instance():
    assert get_adapter("kimi-code") is get_adapter("kimi-cli")


def test_get_adapter_unknown_raises_keyerror_with_known_list():
    try:
        get_adapter("not-a-cli")
    except KeyError as exc:
        msg = str(exc)
        assert "unknown cli" in msg
        for name in ("claude-code", "codex-cli", "kimi-code"):
            assert name in msg
    else:
        raise AssertionError("expected KeyError for unknown cli")


# ── base + interface compliance ──────────────────────────────────


def _all_adapters() -> list[CliAdapter]:
    return [ClaudeCodeAdapter(), CodexCliAdapter(), KimiCodeAdapter()]


def test_every_adapter_implements_required_methods():
    for adapter in _all_adapters():
        assert isinstance(adapter, CliAdapter)
        cmd = adapter.spawn_cmd("worker_x", "sonnet")
        assert isinstance(cmd, str) and cmd.strip()
        ready = adapter.ready_markers()
        assert ready and isinstance(ready, list)
        busy = adapter.busy_markers()
        assert busy and isinstance(busy, list)
        assert adapter.process_name()
        assert adapter.submit_keys()


def test_default_submit_keys_are_enter_variants():
    # base default lists Enter / C-m / C-j; ClaudeCode keeps it, Codex/Kimi prepend M-Enter
    cc = ClaudeCodeAdapter().submit_keys()
    assert cc[0] == "Enter"
    for adapter in (CodexCliAdapter(), KimiCodeAdapter()):
        keys = adapter.submit_keys()
        assert keys[0] == "M-Enter"
        assert "Enter" in keys


# ── per-adapter spawn shape ──────────────────────────────────────


def test_claude_code_spawn_is_dangerously_skip_permissions_with_model():
    cmd = ClaudeCodeAdapter().spawn_cmd("worker_cc", "sonnet-4-6")
    assert "claude --dangerously-skip-permissions" in cmd
    assert "--model sonnet-4-6" in cmd
    assert "--name worker_cc" in cmd
    assert "IS_SANDBOX=1" in cmd


def test_codex_spawn_passes_openai_model_through():
    cmd = CodexCliAdapter().spawn_cmd("worker_codex", "gpt-5.5")
    assert "codex" in cmd
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "--model gpt-5.5" in cmd
    assert "CODEX_AGENT=worker_codex" in cmd


def test_codex_spawn_drops_non_openai_model():
    cmd = CodexCliAdapter().spawn_cmd("worker_codex", "sonnet")
    assert "--model" not in cmd  # silently dropped
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd


def test_codex_spawn_quotes_agent_name_with_special_chars():
    cmd = CodexCliAdapter().spawn_cmd("worker x", "")
    assert "'worker x'" in cmd  # shlex.quote


def test_codex_spawn_sets_per_agent_codex_home():
    from claudeteam.agents.codex_cli import codex_home
    cmd = CodexCliAdapter().spawn_cmd("worker_codex", "")
    assert f"CODEX_HOME={codex_home('worker_codex')}" in cmd
    assert codex_home("worker_codex").endswith("/worker_codex/.codex")


def test_codex_native_memory_path_is_agents_md_under_codex_home():
    from claudeteam.agents.codex_cli import codex_home
    path = CodexCliAdapter().native_memory_path("worker_codex")
    assert path == f"{codex_home('worker_codex')}/AGENTS.md"


def test_codex_display_model_passes_openai_through_but_labels_dropped():
    a = CodexCliAdapter()
    assert a.display_model("gpt-5.5") == "gpt-5.5"
    assert a.display_model("o3") == "o3"
    # Dropped (non-OpenAI) → label the real source, not the stale alias.
    assert a.display_model("opus") == "codex 自身配置"
    assert a.display_model("") == "codex 自身配置"


def test_noop_model_adapters_label_their_own_config():
    """gemini/qwen/kimi ignore the team/argv model → never echo it back."""
    for adapter in (GeminiCliAdapter(), QwenCodeAdapter(), KimiCodeAdapter()):
        label = adapter.display_model("opus")
        assert "opus" not in label
        assert "自身配置" in label


def test_claude_display_model_is_verbatim():
    """claude-code actually runs the resolved model, so its label is the
    model itself (base default), empty → 默认."""
    assert ClaudeCodeAdapter().display_model("sonnet") == "sonnet"
    assert ClaudeCodeAdapter().display_model("") == "默认"


def test_native_memory_reloads_only_claude_and_gemini():
    """The mid-session disk-reload capability gates the G reidentify
    fallback: claude (re-reads after /compact) + gemini (every-prompt +
    /memory reload) → True; codex/qwen/kimi load once at startup → False,
    so they need a reidentify re-inject to pick up a fresh anchor."""
    assert ClaudeCodeAdapter().native_memory_reloads() is True
    assert GeminiCliAdapter().native_memory_reloads() is True
    assert CodexCliAdapter().native_memory_reloads() is False
    assert QwenCodeAdapter().native_memory_reloads() is False
    assert KimiCodeAdapter().native_memory_reloads() is False


def test_kimi_has_no_native_memory_file_by_design():
    """E/Plan-B: kimi loads memory only via the git-root→cwd chain, so
    isolating a per-agent AGENTS.md would force the pane's cwd off the
    repo. We deliberately keep cwd=repo and skip the native file — kimi
    relies on the init-prompt anchor (+ reidentify fallback) instead.
    Pin it so a future change can't silently flip kimi to a colliding or
    cwd-moving native path without revisiting the rationale."""
    assert KimiCodeAdapter().native_memory_path("worker_kimi") is None


def test_kimi_spawn_uses_yolo_flag_and_disable_update():
    cmd = KimiCodeAdapter().spawn_cmd("worker_kimi", "")
    assert "kimi --yolo" in cmd
    assert "DISABLE_UPDATE_CHECK=1" in cmd
    assert "KIMI_AGENT=worker_kimi" in cmd


# ── markers ──────────────────────────────────────────────────────


def test_codex_busy_markers_include_boot_phase():
    """R-busy fix carries over: Booting MCP server must be a busy marker so
    inject_when_idle waits past the boot race."""
    assert "Booting MCP server" in CodexCliAdapter().busy_markers()


def test_kimi_busy_markers_include_using_shell():
    assert "Using Shell" in KimiCodeAdapter().busy_markers()
    assert "Booting" in KimiCodeAdapter().busy_markers()


def test_process_names_match_expected_binaries():
    assert ClaudeCodeAdapter().process_name() == "claude"
    assert CodexCliAdapter().process_name() == "codex"
    assert KimiCodeAdapter().process_name() == "kimi"


# ── codex_cli.ensure_workdir_trusted ─────────────────────────────


def test_ensure_workdir_trusted_writes_entry_when_config_missing(tmp_path=None):
    import tempfile
    from pathlib import Path
    from claudeteam.agents.codex_cli import ensure_workdir_trusted

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "codex" / "config.toml"
        workdir = Path("/some/work/dir")
        ensure_workdir_trusted(workdir, config_path=cfg)
        text = cfg.read_text(encoding="utf-8")
        assert '[projects."/some/work/dir"]' in text
        assert 'trust_level = "trusted"' in text


def test_ensure_workdir_trusted_appends_when_other_entries_present():
    import tempfile
    from pathlib import Path
    from claudeteam.agents.codex_cli import ensure_workdir_trusted

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.toml"
        cfg.write_text('[projects."/other/dir"]\ntrust_level = "trusted"\n', encoding="utf-8")
        ensure_workdir_trusted(Path("/new/dir"), config_path=cfg)
        text = cfg.read_text(encoding="utf-8")
        assert '[projects."/other/dir"]' in text
        assert '[projects."/new/dir"]' in text


def test_ensure_workdir_trusted_idempotent_when_entry_exists():
    import tempfile
    from pathlib import Path
    from claudeteam.agents.codex_cli import ensure_workdir_trusted

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.toml"
        original = '[projects."/already/here"]\ntrust_level = "trusted"\n'
        cfg.write_text(original, encoding="utf-8")
        ensure_workdir_trusted(Path("/already/here"), config_path=cfg)
        # File unchanged
        assert cfg.read_text(encoding="utf-8") == original
