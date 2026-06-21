"""Tests for store/team_memory.py — the shared team-experience pool."""
from __future__ import annotations

from helpers import attr_patch, isolated_env
from claudeteam.store import team_memory


def test_append_then_list_round_trips():
    with isolated_env():
        team_memory.append("测试用 python3 tests/run.py",
                           kind="learning", by="worker_cc")
        rows = team_memory.list_recent()
        assert len(rows) == 1
        assert rows[0]["content"] == "测试用 python3 tests/run.py"
        assert rows[0]["kind"] == "learning"
        assert rows[0]["by"] == "worker_cc"


def test_list_is_oldest_first():
    with isolated_env():
        team_memory.append("first", by="a")
        team_memory.append("second", by="b")
        assert [r["content"] for r in team_memory.list_recent()] == ["first", "second"]


def test_render_for_prompt_marks_contributor_and_ref():
    with isolated_env():
        team_memory.append("用两步结账", kind="decision", by="manager", ref="I-7")
        block = team_memory.render_for_prompt()
        assert "团队共享经验" in block
        assert "[decision] 用两步结账 (@manager) (ref=I-7)" in block


def test_render_empty_is_blank():
    """Callers branch on `if block:` — an empty pool must render to ''."""
    with isolated_env():
        assert team_memory.render_for_prompt() == ""


def test_clear_drops_all_and_is_idempotent():
    with isolated_env():
        team_memory.append("x", by="a")
        team_memory.append("y", by="b")
        assert team_memory.clear() == 2
        assert team_memory.list_recent() == []
        assert team_memory.clear() == 0


def test_cap_truncates_from_front():
    """Past the retention cap, oldest entries drop first (bounded growth)."""
    with isolated_env(), attr_patch(team_memory, _max=lambda: 2):
        for i in range(4):
            team_memory.append(f"e{i}", by="a")
        assert [r["content"] for r in team_memory.list_recent()] == ["e2", "e3"]
