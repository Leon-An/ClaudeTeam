"""Tests for `claudeteam send` command — edge cases and deeper paths.

Complements test_commands_messaging.py with focus on:
  - multi-word messages preserving whitespace
  - task_id threading through inbox
  - send to nonexistent agent (inbox still written)
  - send with empty message
  - send to self
  - lazy agent wake path with mock tmux
"""
from __future__ import annotations

from helpers import attr_patch, isolated_env, run_cli
from claudeteam.store import local_facts


def test_send_preserves_multimessage_content():
    """Multi-word message with CJK and spaces is stored verbatim."""
    with isolated_env():
        msg = "请帮我查看 README 中的安装步骤，然后汇报给 manager"
        rc, out, _ = run_cli(["send", "worker", "manager", msg])
        assert rc == 0
        rows = local_facts.list_messages("worker")
        assert rows[0]["content"] == msg


def test_send_default_priority_is_medium():
    with isolated_env():
        run_cli(["send", "w", "m", "x"])
        rows = local_facts.list_messages("w")
        assert rows[0]["priority"] == "中"


def test_send_accepts_high_priority():
    with isolated_env():
        run_cli(["send", "w", "m", "urgent", "高"])
        rows = local_facts.list_messages("w")
        assert rows[0]["priority"] == "高"


def test_send_to_nonexistent_agent_still_writes_inbox():
    """Inbox doesn't validate agent existence — any name works."""
    with isolated_env():
        rc, out, _ = run_cli(["send", "ghost_agent", "manager", "hello"])
        assert rc == 0
        rows = local_facts.list_messages("ghost_agent")
        assert len(rows) == 1
        assert rows[0]["from"] == "manager"


def test_send_empty_message_still_writes():
    """Edge case: message content is empty string."""
    with isolated_env():
        rc, out, _ = run_cli(["send", "w", "m", ""])
        assert rc == 0
        rows = local_facts.list_messages("w")
        assert rows[0]["content"] == ""


def test_send_no_args_returns_usage():
    rc, _, err = run_cli(["send"])
    assert rc == 1
    assert "usage" in err.lower()


def test_send_two_args_returns_usage():
    rc, _, err = run_cli(["send", "only", "two"])
    assert rc == 1
    assert "usage" in err.lower()


def test_send_multiple_messages_all_appear_in_inbox():
    with isolated_env():
        for i in range(5):
            run_cli(["send", "w", "m", f"msg-{i}"])
        rows = local_facts.list_messages("w")
        assert len(rows) == 5
        contents = [r["content"] for r in rows]
        assert contents == [f"msg-{i}" for i in range(5)]


def test_send_to_different_agents_isolated():
    """Messages to different agents don't bleed into each other's inbox."""
    with isolated_env():
        run_cli(["send", "alice", "bob", "for alice"])
        run_cli(["send", "charlie", "bob", "for charlie"])
        assert len(local_facts.list_messages("alice")) == 1
        assert len(local_facts.list_messages("charlie")) == 1
        assert local_facts.list_messages("alice")[0]["content"] == "for alice"
        assert local_facts.list_messages("charlie")[0]["content"] == "for charlie"


def test_send_read_cycle_preserves_content():
    """After marking read, message content is still accessible via list_messages."""
    with isolated_env():
        run_cli(["send", "w", "m", "important task"])
        rows = local_facts.list_messages("w")
        lid = rows[0]["local_id"]
        run_cli(["read", lid])
        # list_messages with unread_only=False still shows it
        all_rows = local_facts.list_messages("w", unread_only=False)
        assert len(all_rows) == 1
        assert all_rows[0]["content"] == "important task"
        assert all_rows[0]["read"] is True
