"""Tests for commands/teamctl.py — the detached team-shutdown/team-restart
runners that orchestrate down/up and post the completion card."""
from __future__ import annotations

from helpers import attr_patch, isolated_env
from claudeteam.commands import teamctl as tc
from claudeteam.runtime import teamctl as rtc


def _stub_main(rc):
    return type("M", (), {"main": staticmethod(lambda argv: rc)})


def _capture_notify():
    cards = []
    return cards, (lambda card: cards.append(card))


def _card_text(card) -> str:
    return "\n".join(
        e.get("content", "")
        for e in card.get("body", {}).get("elements", card.get("elements", []))
        if e.get("tag") == "markdown")


# ── team-shutdown ──────────────────────────────────────────────────


def test_shutdown_runs_down_and_posts_success_card():
    cards, cap = _capture_notify()
    with isolated_env(), attr_patch(tc, _down=_stub_main(0)), \
            attr_patch(rtc, notify=cap):
        rc = tc.shutdown_main([])
    assert rc == 0
    assert len(cards) == 1
    assert "已下线" in _card_text(cards[0])


def test_shutdown_warns_on_down_failure():
    cards, cap = _capture_notify()
    with isolated_env(), attr_patch(tc, _down=_stub_main(1)), \
            attr_patch(rtc, notify=cap):
        rc = tc.shutdown_main([])
    assert rc == 1
    assert "告警" in _card_text(cards[0])


# ── team-restart ───────────────────────────────────────────────────


def test_restart_down_then_up_success():
    order = []
    cards, cap = _capture_notify()
    down = type("D", (), {"main": staticmethod(lambda a: order.append("down") or 0)})
    up = type("U", (), {"main": staticmethod(lambda a: order.append("up") or 0)})
    with isolated_env(), attr_patch(tc, _down=down, _up=up), \
            attr_patch(rtc, notify=cap):
        rc = tc.restart_main([])
    assert rc == 0
    assert order == ["down", "up"]      # down BEFORE up
    assert "已重启" in _card_text(cards[0])


def test_restart_aborts_up_when_down_leaves_stragglers():
    """If down can't kill everything, never stack a fresh team on a
    half-dead one — abort before up."""
    order = []
    cards, cap = _capture_notify()
    down = type("D", (), {"main": staticmethod(lambda a: order.append("down") or 1)})
    up = type("U", (), {"main": staticmethod(lambda a: order.append("up") or 0)})
    with isolated_env(), attr_patch(tc, _down=down, _up=up), \
            attr_patch(rtc, notify=cap):
        rc = tc.restart_main([])
    assert rc == 1
    assert order == ["down"]            # up NEVER ran
    assert "中止重启" in _card_text(cards[0])


def test_restart_reports_up_failure():
    cards, cap = _capture_notify()
    with isolated_env(), attr_patch(tc, _down=_stub_main(0), _up=_stub_main(1)), \
            attr_patch(rtc, notify=cap):
        rc = tc.restart_main([])
    assert rc == 1
    assert "up 阶段" in _card_text(cards[0])
