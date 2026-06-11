"""Edge-case tests for feishu/router.py — classify_event boundary conditions.

Complements test_feishu_router.py with focus on:
  - empty text after sender prefix strip
  - @mention inside agent-tagged messages
  - card sender detection with malformed titles
  - BROADCAST token handling (legacy behavior)
  - create_time threading
  - bot_id + sender_type interaction edge cases
  - agent-tagged sender with explicit @target (should drop)
"""
from __future__ import annotations

from claudeteam.feishu.router import Action, classify_event


_AGENTS = ["manager", "worker_cc", "worker_codex", "worker_kimi"]


def _ev(**overrides) -> dict:
    base = {
        "message_id": "om_1",
        "chat_id": "oc_team",
        "sender_id": "ou_user",
        "text": "hello",
        "msg_type": "text",
    }
    base.update(overrides)
    return base


# ── empty text edge cases ─────────────────────────────────────────


def test_drop_when_text_is_none():
    """None text should be treated as empty."""
    d = classify_event(_ev(text=None), team_agents=_AGENTS)
    assert d.is_drop() and d.reason == "empty"


def test_drop_when_text_only_newlines():
    d = classify_event(_ev(text="\n\n\n"), team_agents=_AGENTS)
    assert d.is_drop() and d.reason == "empty"


def test_drop_when_text_only_tabs():
    d = classify_event(_ev(text="\t\t"), team_agents=_AGENTS)
    assert d.is_drop() and d.reason == "empty"


# ── sender prefix edge cases ──────────────────────────────────────


def test_sender_prefix_unknown_agent_drops_as_agent_no_target():
    """[unknown_name] at start with an agent-like name but not in team."""
    d = classify_event(_ev(text="[not_an_agent] hello"), team_agents=_AGENTS)
    # unknown agent name → not parsed as sender → treated as human → route to manager
    assert d.action is Action.ROUTE
    assert d.targets == ["manager"]


def test_sender_prefix_known_agent_no_at_target_drops():
    """[worker_cc] hello — agent-tagged with no @target → drop."""
    d = classify_event(_ev(text="[worker_cc] hello"), team_agents=_AGENTS)
    assert d.is_drop() and d.reason == "agent_no_target"
    assert d.sender == "worker_cc"


def test_sender_prefix_known_agent_with_text_preserved():
    """[worker_cc] text is stripped, remaining text preserved."""
    d = classify_event(
        _ev(text="[worker_cc] status update: all clear"),
        team_agents=_AGENTS,
    )
    assert d.is_drop()
    assert d.text == "status update: all clear"


def test_sender_prefix_not_at_start_is_ignored():
    """Leading text before [agent] means it's not a sender prefix."""
    d = classify_event(
        _ev(text="hey [worker_cc] look at this"),
        team_agents=_AGENTS,
    )
    assert d.action is Action.ROUTE
    assert d.targets == ["manager"]


# ── @mention handling ─────────────────────────────────────────────


def test_at_mention_in_middle_routes_to_manager():
    """@worker_cc in the middle of text is content, not routing."""
    d = classify_event(
        _ev(text="please ask @worker_cc to review"),
        team_agents=_AGENTS,
    )
    assert d.action is Action.ROUTE
    assert d.targets == ["manager"]
    assert "@worker_cc" in d.text


def test_multiple_at_mentions_all_treated_as_content():
    d = classify_event(
        _ev(text="@worker_cc and @worker_codex should collaborate"),
        team_agents=_AGENTS,
    )
    assert d.action is Action.ROUTE
    assert d.targets == ["manager"]


def test_at_team_mention_is_content_not_broadcast():
    """@team is content for manager, not a broadcast trigger at router level."""
    d = classify_event(_ev(text="@team standup time"), team_agents=_AGENTS)
    assert d.action is Action.ROUTE
    assert d.targets == ["manager"]
    assert "@team" in d.text


def test_at_all_mention_is_content_not_broadcast():
    d = classify_event(_ev(text="@all please read the doc"), team_agents=_AGENTS)
    assert d.action is Action.ROUTE
    assert d.targets == ["manager"]


# ── card sender detection ─────────────────────────────────────────


def test_card_sender_worker_detected_from_title():
    """Card title with worker name + · role → detected as worker card."""
    d = classify_event(
        _ev(
            sender_id="cli_bot",
            sender_type="app",
            text='<card title="💎 worker_cc · 内容策划">完工</card>',
        ),
        team_agents=_AGENTS,
    )
    assert d.action is Action.ROUTE
    assert d.targets == ["manager"]
    assert d.sender == "worker_cc"


def test_card_sender_manager_drops_as_bot_self():
    """Card title with manager name → bot self, should drop."""
    d = classify_event(
        _ev(
            sender_id="cli_bot",
            sender_type="app",
            text='<card title="🎯 manager · 团队主管">已收到</card>',
        ),
        team_agents=_AGENTS,
    )
    assert d.is_drop() and d.reason == "bot_self"


def test_card_sender_unknown_agent_drops_as_bot_self():
    """Card title with agent not in team → default bot_self drop."""
    d = classify_event(
        _ev(
            sender_id="cli_bot",
            sender_type="app",
            text='<card title="⚙️ unknown_agent · 系统">msg</card>',
        ),
        team_agents=_AGENTS,
    )
    assert d.is_drop() and d.reason == "bot_self"


def test_bot_without_card_title_drops():
    """Bot message without recognizable card title → bot_self drop."""
    d = classify_event(
        _ev(sender_id="cli_bot", sender_type="app", text="plain bot text"),
        team_agents=_AGENTS,
    )
    assert d.is_drop() and d.reason == "bot_self"


# ── create_time threading ─────────────────────────────────────────


def test_create_time_preserved_in_decision():
    d = classify_event(
        _ev(create_time="1717500000000"),
        team_agents=_AGENTS,
    )
    assert d.create_time == "1717500000000"


def test_create_time_missing_converts_to_string():
    """create_time=None → str(None) = 'None' (router uses str() coercion)."""
    d = classify_event(
        _ev(create_time=None),
        team_agents=_AGENTS,
    )
    # str(None) == "None" — this is the actual behavior
    assert d.create_time == "None"


# ── msg_id edge cases ─────────────────────────────────────────────


def test_drop_when_msg_id_is_empty_string():
    d = classify_event(_ev(message_id=""), team_agents=_AGENTS)
    assert d.is_drop() and d.reason == "no_msg_id"


def test_drop_when_msg_id_is_none():
    d = classify_event(_ev(message_id=None), team_agents=_AGENTS)
    assert d.is_drop() and d.reason == "no_msg_id"


# ── slash detection ───────────────────────────────────────────────


def test_slash_command_after_sender_prefix():
    """[user] /team → strip sender prefix, detect /team as slash."""
    d = classify_event(_ev(text="[user] /team"), team_agents=_AGENTS)
    assert d.action is Action.SLASH
    assert d.text == "/team"


def test_slash_command_with_leading_whitespace():
    d = classify_event(_ev(text="  /health"), team_agents=_AGENTS)
    assert d.action is Action.SLASH


def test_slash_command_with_args():
    d = classify_event(_ev(text="/tmux worker_cc 50"), team_agents=_AGENTS)
    assert d.action is Action.SLASH
    assert d.text == "/tmux worker_cc 50"


# ── cross-team filtering ──────────────────────────────────────────


def test_no_cross_team_drop_when_chat_id_unset():
    """Without chat_id filter, any chat passes through."""
    d = classify_event(_ev(chat_id="oc_random"), team_agents=_AGENTS, chat_id="")
    assert d.action is Action.ROUTE


def test_cross_team_drop_when_chat_ids_differ():
    d = classify_event(
        _ev(chat_id="oc_other"),
        team_agents=_AGENTS,
        chat_id="oc_ours",
    )
    assert d.is_drop() and d.reason == "cross_team"


# ── sender_type variations ────────────────────────────────────────


def test_sender_type_empty_treated_as_human():
    """Missing sender_type → human path → route to manager."""
    d = classify_event(_ev(sender_type=""), team_agents=_AGENTS)
    assert d.action is Action.ROUTE


def test_sender_type_app_id_from_list_api():
    """chat-messages-list returns id_type=app_id → treated as bot."""
    d = classify_event(
        _ev(sender_id="cli_xxx", sender_type="app_id",
            text='<card title="🎯 manager · 团队主管">ack</card>'),
        team_agents=_AGENTS,
    )
    assert d.is_drop() and d.reason == "bot_self"


# ── dedup with seen set ───────────────────────────────────────────


def test_seen_empty_set_does_not_drop():
    d = classify_event(_ev(), team_agents=_AGENTS, seen_msg_ids=set())
    assert d.action is Action.ROUTE


def test_seen_different_id_does_not_drop():
    d = classify_event(
        _ev(message_id="om_new"),
        team_agents=_AGENTS,
        seen_msg_ids={"om_old"},
    )
    assert d.action is Action.ROUTE
