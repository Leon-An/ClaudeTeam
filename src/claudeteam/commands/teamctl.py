"""`claudeteam team-shutdown` / `claudeteam team-restart` — the detached
runners behind the `/shutdown` and `/restart` chat slash commands.

They are normal CLI subcommands (not buried in the slash handler) for two
reasons: they can be unit-tested in isolation, and the slash handler can
launch them with a plain detached Popen — a child process that survives
`down` killing the router, which an in-router thread could not.

Each runs the lifecycle primitive(s), then posts a completion card to the
team chat via `teamctl.notify` (the router is gone by then, so the slash
handler that triggered this can't report the outcome itself).

These are also usable directly by an operator (`claudeteam team-restart`);
they are NOT gated by `allow_lifecycle_slash` — that flag guards the CHAT
surface only. A shell operator already has full host access.
"""
from __future__ import annotations

from claudeteam.commands import down as _down, up as _up
from claudeteam.feishu import cards
from claudeteam.runtime import config, teamctl
from claudeteam.util import maybe_print_help


def shutdown_main(argv: list[str]) -> int:
    if maybe_print_help(argv, "usage: claudeteam team-shutdown"):
        return 0
    rc = _down.main([])
    if rc == 0:
        teamctl.notify(cards.simple_card(
            "团队控制 · /shutdown",
            f"🛑 团队已下线（session `{config.session_name()}`）。"
            "需 `/restart` 或运维 `up` 才能恢复。",
            color="green"))
    else:
        teamctl.notify(cards.simple_card(
            "团队控制 · /shutdown",
            "⚠️ 团队下线过程有告警（有东西没干净退出），请查看容器日志。",
            color="red"))
    return rc


def restart_main(argv: list[str]) -> int:
    if maybe_print_help(argv, "usage: claudeteam team-restart"):
        return 0
    # Phase 1 — robust teardown. `down` already escalates SIGTERM→SIGKILL
    # and reaps the subscribe process group, so it IS the straggler clean:
    # dead/stale pidfiles, orphan tmux session+windows, leftover npx/node
    # from a previous router. If it can't get everything dead, abort —
    # don't stack a fresh team on top of a half-dead one.
    rc = _down.main([])
    if rc != 0:
        teamctl.notify(cards.simple_card(
            "团队控制 · /restart",
            "⚠️ 下线阶段有残留没杀干净，已**中止重启**（不在半死团队上叠新团队）。"
            "请查看容器日志后手动处理，再 `/restart` 或运维 `up`。",
            color="red"))
        return rc
    # Phase 2 — bring it back. up is idempotent and waits on each daemon's
    # pidfile, so a fast-fail (missing chat_id, no agents) surfaces as rc=1.
    rc = _up.main([])
    if rc == 0:
        teamctl.notify(cards.simple_card(
            "团队控制 · /restart",
            f"♻️ 团队已重启完成（session `{config.session_name()}`）。"
            "`/health` 可核验各守护进程。",
            color="green"))
    else:
        teamctl.notify(cards.simple_card(
            "团队控制 · /restart",
            "⚠️ 重启的 up 阶段有错误（某守护进程没起来），请查看容器日志 / `/health`。",
            color="red"))
    return rc
