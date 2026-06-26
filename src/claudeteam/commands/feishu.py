"""`claudeteam feishu <subcommand>` — Feishu app lifecycle.

`feishu connect` is the automatic bot-registration flow that **replaces the old
Playwright bot-creator**. It drives the `@larksuite/channel` sidecar
(`scripts/feishu_channel/sidecar.js`) through a device-flow QR scan to:
  1. create (or top-up) a PersonalAgent app  — `register` (+ `scopes`/`grant-scope`)
  2. auto-create the team group with you invited — `create-group`
  3. persist App creds (state/feishu_app.json, 0600) + chat_id (claudeteam.toml)
so `claudeteam up` then just works. The QR / links render straight to the
operator's terminal (sidecar stderr); the machine result (one JSON line per
mode) is captured off stdout.

Shape note: unlike the `health.py` reference (a read-only report), this command
is an interactive orchestrator — a straight-line sequence of sidecar calls with
early error-exits — so it has no accumulator/`_emit_*`.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from claudeteam.feishu import lark
from claudeteam.runtime import config
from claudeteam.util import error_exit, maybe_print_help, pop_flag


USAGE = "usage: claudeteam feishu connect [--group-name NAME] [--tenant feishu|lark]"

# The must-have egress scope. PersonalAgent apps are granted a rich default set
# (send_as_bot + im:chat:create + message-read), so `grant-scope` is a rarely-hit
# safety net — addons requested at register are silently dropped on tenants
# without the platform gray-scale. Checking this one scope is enough to decide.
_REQUIRED_SCOPE = "im:message:send_as_bot"


def _sidecar_path() -> Path:
    """Resolve `scripts/feishu_channel/sidecar.js` (shared with the router
    ingress; honors CLAUDETEAM_FEISHU_SIDECAR_DIR)."""
    return lark.sidecar_path()


def _ensure_node_deps(sidecar_dir: Path) -> bool:
    """Install the sidecar's node_modules on first run (no-op once present)."""
    if (sidecar_dir / "node_modules" / "@larksuite" / "channel").exists():
        return True
    print("📦 installing sidecar deps (npm install)…")
    try:
        rc = subprocess.run(
            ["npm", "install", "--omit=dev", "--no-fund", "--no-audit"],
            cwd=str(sidecar_dir)).returncode
    except OSError:
        return False
    return rc == 0


def _run_sidecar(mode: str, *, extra_env: dict | None = None) -> dict | None:
    """Run `node sidecar.js <mode>`. stderr (QR + human logs) passes through to
    the operator's terminal; stdout (one JSON line) is captured and parsed.
    Returns the parsed object, or None on non-zero exit / no JSON line.
    Interactive modes (`register`, `grant-scope`) block until the operator
    scans + authorizes — that's intended for a first-run setup command."""
    sidecar = _sidecar_path()
    env = {**os.environ, **(extra_env or {})}
    try:
        proc = subprocess.run(["node", str(sidecar), mode], env=env,
                              stdout=subprocess.PIPE, text=True)
    except OSError as e:
        print(f"  ✗ cannot run node sidecar: {e}")
        return None
    if proc.returncode != 0:
        return None
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _connect(argv: list[str]) -> int:
    rest = list(argv)
    group_name = pop_flag(rest, "--group-name") or "ClaudeTeam"
    tenant_flag = pop_flag(rest, "--tenant") or ""

    sidecar = _sidecar_path()
    if not sidecar.exists():
        return error_exit(f"❌ sidecar not found at {sidecar}\n"
                          f"   set CLAUDETEAM_FEISHU_SIDECAR_DIR to its directory")
    if not _ensure_node_deps(sidecar.parent):
        return error_exit(f"❌ failed to install sidecar deps; "
                          f"run `npm install` in {sidecar.parent}")

    # 1. register — interactive QR; blocks until the operator scans + authorizes.
    print("📱 扫码注册飞书机器人（终端将显示二维码 / 授权链接）…")
    reg = _run_sidecar("register")
    if not reg or not reg.get("client_id"):
        return error_exit("❌ registration failed or was cancelled")
    app_id = str(reg["client_id"])
    app_secret = str(reg.get("client_secret", ""))
    owner = str(reg.get("owner_open_id") or "")
    tenant = tenant_flag or str(reg.get("tenant") or "feishu")
    lark.save_app_creds(app_id=app_id, app_secret=app_secret,
                        owner_open_id=owner, tenant=tenant)
    print(f"✅ 应用已注册并保存凭据：{app_id}")

    app_env = {"FEISHU_APP_ID": app_id, "FEISHU_APP_SECRET": app_secret}

    # 2. scopes — only grant if the defaults don't already cover the essentials.
    sc = _run_sidecar("scopes", extra_env=app_env)
    granted = set(sc.get("granted", [])) if sc else set()
    if _REQUIRED_SCOPE not in granted:
        print("🔑 申请缺失的权限（增量授权，需再次扫码确认）…")
        _run_sidecar("grant-scope", extra_env=app_env)

    # 3. create-group — the bot creates the team group + invites you (the scanner).
    grp = _run_sidecar("create-group", extra_env={
        **app_env, "FEISHU_OWNER_OPEN_ID": owner, "FEISHU_GROUP_NAME": group_name})
    if not grp or not grp.get("chat_id"):
        return error_exit("❌ group creation failed")
    chat_id = str(grp["chat_id"])
    ok, msg = config.set_chat_id(chat_id)
    if not ok:
        return error_exit(f"❌ {msg}")
    print(f"✅ 群已创建并已邀请你：{chat_id}")

    print("✅ feishu connect 完成 — 运行 `claudeteam up` 让团队进群报到。")
    return 0


_SUBCOMMANDS = {"connect": _connect}


def main(argv: list[str]) -> int:
    rest = list(argv)
    if maybe_print_help(rest, USAGE):
        return 0
    if not rest:
        print(USAGE)
        return 0
    sub = rest.pop(0)
    handler = _SUBCOMMANDS.get(sub)
    if handler is None:
        return error_exit(f"unknown feishu subcommand: {sub!r}\n{USAGE}")
    return handler(rest)
