"""Tests for `claudeteam feishu connect` — the automatic bot-registration flow.

The node sidecar (network + interactive QR) is the one thing we can't run in a
unit test, so we stub `feishu._run_sidecar` with a recorder that returns canned
per-mode JSON (exactly what the real sidecar emits on stdout). That lets us
assert the orchestration: creds persisted 0600, chat_id written to the toml, and
`grant-scope` invoked ONLY when the default scopes don't already cover sending.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from helpers import attr_patch, isolated_env, run_cli
from claudeteam.commands import feishu
from claudeteam.feishu import lark
from claudeteam.runtime import config, tunables


class _SidecarStub:
    """Stand-in for `feishu._run_sidecar`. Records modes called and returns the
    JSON each sidecar mode emits. `granted` controls the scopes mode so a test
    can drive the grant-scope branch."""

    def __init__(self, *, granted, register=...):
        self.calls: list[str] = []
        self.granted = list(granted)
        self._register = (
            {"event": "registered", "client_id": "cli_new",
             "client_secret": "sek", "owner_open_id": "ou_me", "tenant": "feishu"}
            if register is ... else register)

    def __call__(self, mode, *, extra_env=None):
        self.calls.append(mode)
        return {
            "register": self._register,
            "scopes": {"event": "scopes", "granted": self.granted},
            "grant-scope": {"event": "scope_granted", "client_id": "cli_new"},
            "create-group": {"event": "group_created", "chat_id": "oc_new",
                             "invited": "ou_me"},
        }.get(mode)


def _toml_with_empty_chat_id(tmp: Path) -> None:
    """Seed the isolated claudeteam.toml with a top-level chat_id line for
    set_chat_id to replace in place."""
    Path(os.environ["CLAUDETEAM_CONFIG_FILE"]).write_text(
        'chat_id = ""\n[team]\nsession = "S"\n', encoding="utf-8")
    tunables.reset_cache()


def _connect_with(stub: _SidecarStub, tmp: Path):
    sidecar = tmp / "sidecar.js"
    sidecar.write_text("// stub", encoding="utf-8")
    with attr_patch(feishu, _run_sidecar=stub,
                    _sidecar_path=lambda: sidecar,
                    _ensure_node_deps=lambda d: True):
        return run_cli(["feishu", "connect"])


# ── happy path: default scopes already cover sending → no grant-scope ─────────


def test_connect_persists_creds_and_chat_id():
    stub = _SidecarStub(granted={"im:message:send_as_bot", "im:chat:create"})
    with isolated_env(team={"agents": {"manager": {"cli": "claude-code"}}}) as tmp:
        _toml_with_empty_chat_id(tmp)
        rc, out, err = _connect_with(stub, tmp)
        assert rc == 0, err
        creds = lark.load_app_creds()
        assert creds["app_id"] == "cli_new"
        assert creds["app_secret"] == "sek"
        assert creds["owner_open_id"] == "ou_me"
        assert config.chat_id() == "oc_new"
        # send scope present → grant-scope skipped
        assert stub.calls == ["register", "scopes", "create-group"]


def test_connect_writes_creds_file_0600():
    stub = _SidecarStub(granted={"im:message:send_as_bot"})
    with isolated_env(team={"agents": {"manager": {"cli": "claude-code"}}}) as tmp:
        _toml_with_empty_chat_id(tmp)
        _connect_with(stub, tmp)
        mode = stat.S_IMODE(os.stat(lark.app_creds_file()).st_mode)
        assert mode == 0o600, f"creds file is {oct(mode)}, must be 0600"


# ── fallback: send scope missing → grant-scope runs before create-group ───────


def test_connect_runs_grant_scope_when_send_scope_missing():
    stub = _SidecarStub(granted={"im:message:readonly"})  # no send_as_bot
    with isolated_env(team={"agents": {"manager": {"cli": "claude-code"}}}) as tmp:
        _toml_with_empty_chat_id(tmp)
        rc, _, err = _connect_with(stub, tmp)
        assert rc == 0, err
        assert stub.calls == ["register", "scopes", "grant-scope", "create-group"]


# ── failures abort cleanly, nothing persisted ────────────────────────────────


def test_connect_aborts_when_register_fails():
    stub = _SidecarStub(granted=set(), register=None)
    with isolated_env(team={"agents": {"manager": {"cli": "claude-code"}}}) as tmp:
        _toml_with_empty_chat_id(tmp)
        rc, _, err = _connect_with(stub, tmp)
        assert rc != 0
        assert lark.load_app_creds() == {}        # no creds written
        assert config.chat_id() == ""             # chat_id untouched
        assert stub.calls == ["register"]


def test_connect_aborts_when_group_creation_fails():
    """register succeeds (creds saved) but create-group returns nothing → the
    command errors and leaves chat_id empty rather than half-writing it."""
    def runner(mode, *, extra_env=None):
        runner.calls.append(mode)
        return {
            "register": {"client_id": "cli_new", "client_secret": "sek",
                         "owner_open_id": "ou_me", "tenant": "feishu"},
            "scopes": {"granted": ["im:message:send_as_bot"]},
            "create-group": None,
        }.get(mode)
    runner.calls = []

    with isolated_env(team={"agents": {"manager": {"cli": "claude-code"}}}) as tmp:
        _toml_with_empty_chat_id(tmp)
        sidecar = tmp / "sidecar.js"
        sidecar.write_text("// stub", encoding="utf-8")
        with attr_patch(feishu, _run_sidecar=runner,
                        _sidecar_path=lambda: sidecar,
                        _ensure_node_deps=lambda d: True):
            rc, _, _ = run_cli(["feishu", "connect"])
        assert rc != 0
        assert lark.load_app_creds().get("app_id") == "cli_new"  # register persisted
        assert config.chat_id() == ""                            # group failed → no chat_id


# ── dispatch ─────────────────────────────────────────────────────────────────


def test_feishu_no_subcommand_prints_usage():
    rc, out, _ = run_cli(["feishu"])
    assert rc == 0
    assert "feishu connect" in out


def test_feishu_unknown_subcommand_errors():
    rc, _, err = run_cli(["feishu", "bogus"])
    assert rc != 0
    assert "unknown feishu subcommand" in err
