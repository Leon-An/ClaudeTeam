"""`claudeteam feishu <subcommand>` — Feishu app lifecycle.

`feishu connect` registers the bot ClaudeTeam talks through and auto-creates the
team group. Two modes:

  • DEFAULT — **guided self-built app**. You create a 企业自建应用 in the console
    (a few clicks), and the command hands you a ONE-CLICK permission deep-link
    that pre-selects every scope ClaudeTeam needs — crucially `im:message.group_msg`,
    the *sensitive* scope that lets the bot receive un-@'d group messages (plain
    text + slash commands + catchup recovery). It then verifies the scope landed,
    creates the team group, and persists creds. Full group UX; no Playwright.

  • `--quick` — **one-scan PersonalAgent** (`@larksuite/channel` device-flow QR).
    Zero console clicks, but Feishu won't grant a PersonalAgent app
    `im:message.group_msg`, so in GROUPS users must @ the bot. Fine for DM-only use.

Both persist App creds → `state/feishu_app.json` (0600) + `chat_id` →
`claudeteam.toml`, so `claudeteam up` then just works. The sidecar's machine
output (one JSON line per mode) is read off stdout; QR / human logs go to stderr.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from claudeteam.feishu import lark
from claudeteam.runtime import config
from claudeteam.util import (
    error_exit, maybe_print_help, pop_bool_flag, pop_flag, reject_extra_args,
)


USAGE = ("usage: claudeteam feishu connect [--quick] [--group-name NAME] "
         "[--tenant feishu|lark]")

# Scopes a working ClaudeTeam bot MUST have to operate in a GROUP: post cards AND
# receive un-@'d messages (the whole point — "no @ → manager", plus slash commands
# + catchup). `im:message.group_msg` is the *sensitive* one a 自建应用 gets via the
# console + admin approval; a one-scan PersonalAgent can't, so it's the dividing
# line between the guided flow (full) and --quick (DM/@bot-only).
_REQUIRED_SCOPES = frozenset({
    "im:message:send_as_bot",   # post cards into the group
    "im:message.group_msg",     # receive un-@'d group messages (boss types freely)
})

# Full scope set we pre-fill into the one-click permission deep-link so the
# operator approves them all in a single console confirm instead of ticking the
# checkboxes one by one. (Pattern lifted from AstrBot's Lark setup.)
# `application:application:self_manage` is what lets the app READ ITS OWN scopes
# (the `scopes` verify below) and resolve its owner to invite into the group
# (`create-group`'s getAppInfo) — without it a fresh app can't self-read and the
# verify/owner-invite silently fail. It is NOT in _REQUIRED_SCOPES (we don't gate
# on confirming it), just an enabler the deep-link grants.
_DEEPLINK_SCOPES = (
    "im:message:send_as_bot",
    "im:message.group_msg",
    "im:message.group_at_msg",
    "im:message.p2p_msg",
    "im:chat",
    "im:resource",
    "application:application:self_manage",
)


def _deeplink(app_id: str, tenant: str = "feishu") -> str:
    """One-click console link that opens the permission dialog with every
    ClaudeTeam scope pre-selected — the operator just clicks 确认."""
    host = "open.larksuite.com" if tenant == "lark" else "open.feishu.cn"
    return (f"https://{host}/app/{app_id}/auth"
            f"?q={','.join(_DEEPLINK_SCOPES)}&op_from=openapi&token_type=tenant")


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
    Returns the parsed object, or None on non-zero exit / no JSON line."""
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


def _sidecar_ready() -> str:
    """Validate the sidecar file + its node deps. Returns "" if ready, else an
    error message for the caller to error_exit with."""
    sidecar = _sidecar_path()
    if not sidecar.exists():
        return (f"sidecar not found at {sidecar}\n"
                f"   set CLAUDETEAM_FEISHU_SIDECAR_DIR to its directory")
    if not _ensure_node_deps(sidecar.parent):
        return f"failed to install sidecar deps; run `npm install` in {sidecar.parent}"
    return ""


def _granted_scopes(app_id: str, app_secret: str) -> set[str] | None:
    """The app's granted tenant scopes, or None if they couldn't be READ.

    The self-read (`application.get`) itself needs `application:application:
    self_manage`, which only lands after the version is published + approved —
    so an empty/failed read means "unknown", NOT "nothing granted". Callers must
    distinguish: a confirmed-missing scope is an abort; an unreadable app is a
    warn-and-proceed (else a correctly-set-up app dead-ends on a read it can't do
    yet)."""
    sc = _run_sidecar("scopes", extra_env={
        "FEISHU_APP_ID": app_id, "FEISHU_APP_SECRET": app_secret})
    if not sc:
        return None
    granted = sc.get("granted")
    return set(granted) if granted else None


def _create_group_and_persist(app_id: str, app_secret: str, group_name: str,
                              owner: str = "") -> int:
    """Shared tail: bot creates the team group (+ invites the owner) and we write
    chat_id into the config. owner='' → the sidecar resolves it via getAppInfo."""
    grp = _run_sidecar("create-group", extra_env={
        "FEISHU_APP_ID": app_id, "FEISHU_APP_SECRET": app_secret,
        "FEISHU_GROUP_NAME": group_name,
        **({"FEISHU_OWNER_OPEN_ID": owner} if owner else {})})
    if not grp or not grp.get("chat_id"):
        return error_exit("❌ 建群失败")
    chat_id = str(grp["chat_id"])
    ok, msg = config.set_chat_id(chat_id)
    if not ok:
        return error_exit(f"❌ {msg}")
    print(f"✅ 群已创建：{chat_id}")
    print("✅ feishu connect 完成 — 运行 `claudeteam up` 让团队进群报到。")
    return 0


# ── DEFAULT: guided self-built app (full group permissions) ───────────────────
def _connect_guided(argv: list[str], *, prompt=input) -> int:
    rest = list(argv)
    group_name = pop_flag(rest, "--group-name") or "ClaudeTeam"
    tenant = pop_flag(rest, "--tenant") or "feishu"
    if (rc := reject_extra_args(rest, USAGE)) is not None:
        return rc
    if err := _sidecar_ready():
        return error_exit(f"❌ {err}")
    console = "open.larksuite.com" if tenant == "lark" else "open.feishu.cn"

    print("=== 引导注册飞书【自建应用】（全权限：群里免 @ + 斜杠命令 + catchup）===\n")
    print(f"① 打开 https://{console}/app → 「创建企业自建应用」→ 填名字")
    print("② 「添加应用能力」→ 机器人 → 添加")
    print("③ 「凭证与基础信息」→ 复制 App ID + App Secret，粘贴到下面：\n")
    app_id = prompt("   App ID (cli_...): ").strip()
    app_secret = prompt("   App Secret: ").strip()
    if not app_id or not app_secret:
        return error_exit("❌ App ID / Secret 不能为空")
    lark.save_app_creds(app_id=app_id, app_secret=app_secret, tenant=tenant)
    print("\n✅ 凭据已存到 state/feishu_app.json (0600)\n")

    print("④ 点这个链接，一次把全部权限勾上 → 确认（已含敏感权限 im:message.group_msg）：\n")
    print(f"   {_deeplink(app_id, tenant)}\n")
    print("⑤ 「事件与回调」→ 订阅方式 = 使用长连接接收事件 → 添加事件「接收消息」")
    print("⑥ 「应用发布」→ 创建版本 → 申请发布 →（你是管理员就直接批准；个人版免审核）\n")
    prompt("   ④⑤⑥ 都做完后，按回车继续验证…")
    print()

    # Three outcomes — DON'T conflate "couldn't read scopes" with "scope missing":
    # the self-read needs self_manage + publish/approval, so a brand-new app that
    # was set up correctly may still be unreadable here. Only abort on a CONFIRMED
    # miss; otherwise warn and proceed (the group still gets created, and the live
    # round-trip after `up` is the real proof).
    granted = _granted_scopes(app_id, app_secret)
    if granted is None:
        print("⚠️  暂时读不到已授权权限（自建应用要 ⑥ 发版 + 管理员批准后才能自查）——先继续建群。")
        print("   若 `up` 后群里【不 @】的消息主管收不到：回控制台用 ④ 的链接确认勾了 "
              "im:message.group_msg + ⑥ 发版批准了，再重跑本命令即可。")
    elif missing := (_REQUIRED_SCOPES - granted):
        print(f"⚠️  确认还缺权限：{', '.join(sorted(missing))}")
        if "im:message.group_msg" in missing:
            print("   im:message.group_msg 是敏感权限：用 ④ 的链接勾上 + ⑥ 发版 + 管理员批准后才生效。")
        return error_exit("❌ 权限未到位 — 补齐后重跑 `claudeteam feishu connect`")
    else:
        print("✅ 关键权限到位（含 im:message.group_msg → 群里不 @ 也能收）")
    return _create_group_and_persist(app_id, app_secret, group_name)


# ── --quick: one-scan PersonalAgent (DM/@bot-only) ────────────────────────────
def _connect_quick(argv: list[str]) -> int:
    rest = list(argv)
    group_name = pop_flag(rest, "--group-name") or "ClaudeTeam"
    tenant_flag = pop_flag(rest, "--tenant") or ""
    if (rc := reject_extra_args(rest, USAGE)) is not None:
        return rc
    if err := _sidecar_ready():
        return error_exit(f"❌ {err}")

    print("📱 扫码注册【个人版应用】（零后台，但群里要 @bot；终端显示二维码 / 链接）…")
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

    granted = _granted_scopes(app_id, app_secret)
    if granted is None or "im:message.group_msg" not in granted:
        print("⚠️  个人版应用拿不到 im:message.group_msg：群里**必须 @bot** 才收得到消息"
              "（斜杠命令同理），且 catchup 补漏在群里失效。要群里免 @ 请改用默认的 "
              "`claudeteam feishu connect`（自建应用）。")
    return _create_group_and_persist(app_id, app_secret, group_name, owner=owner)


def _connect(argv: list[str]) -> int:
    rest = list(argv)
    if pop_bool_flag(rest, "--quick"):
        return _connect_quick(rest)
    return _connect_guided(rest)


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
