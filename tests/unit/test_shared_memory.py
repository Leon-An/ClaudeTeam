"""Tests for cross-agent memory search and shared context.

Verifies store/memory.py additions:
  - cross_agent_search with kind/keyword filters
  - shared_context_for builds markdown summary
  - Cross-agent visibility of memories
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from helpers import env_patch
from claudeteam.store import memory


def _isolated():
    return tempfile.TemporaryDirectory()


def test_cross_agent_search_by_kind():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("alice", "learning", "Python 3.12 has tomllib")
            memory.append("alice", "blocker", "missing GH PAT")
            memory.append("bob", "learning", "ruff replaces flake8")
            results = memory.cross_agent_search(kind="learning")
            assert "alice" in results and "bob" in results
            assert len(results["alice"]) == 1
            assert len(results["bob"]) == 1
            # blocker should not appear
            for agent, entries in results.items():
                for e in entries:
                    assert e["kind"] == "learning"


def test_cross_agent_search_by_keyword():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("alice", "note", "API rate limit is 100/min")
            memory.append("bob", "note", "use tmux for agent isolation")
            memory.append("alice", "note", "API key rotation needed")
            results = memory.cross_agent_search(keyword="API")
            assert "alice" in results
            assert len(results["alice"]) == 2
            assert "bob" not in results


def test_cross_agent_search_by_kind_and_keyword():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("alice", "learning", "auth uses bcrypt")
            memory.append("alice", "blocker", "auth service down")
            memory.append("bob", "learning", "tmux session naming")
            results = memory.cross_agent_search(kind="learning", keyword="auth")
            assert "alice" in results
            assert len(results["alice"]) == 1
            assert "bob" not in results


def test_cross_agent_search_empty_when_no_matches():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("alice", "note", "hello")
            results = memory.cross_agent_search(keyword="nonexistent")
            assert len(results) == 0


def test_cross_agent_search_returns_empty_for_fresh_state():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            results = memory.cross_agent_search()
            assert len(results) == 0


def test_shared_context_for_excludes_self():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("alice", "learning", "Alice's learning")
            memory.append("bob", "learning", "Bob's learning")
            ctx = memory.shared_context_for("alice")
            assert "Bob's learning" in ctx
            assert "Alice's learning" not in ctx


def test_shared_context_for_only_shares_relevant_kinds():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("bob", "learning", "visible learning")
            memory.append("bob", "note", "invisible note")
            memory.append("bob", "task_assigned", "invisible assigned")
            memory.append("bob", "blocker", "visible blocker")
            ctx = memory.shared_context_for("alice")
            assert "visible learning" in ctx
            assert "visible blocker" in ctx
            assert "invisible note" not in ctx
            assert "invisible assigned" not in ctx


def test_shared_context_for_empty_when_no_other_agents():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("alice", "learning", "only agent")
            ctx = memory.shared_context_for("alice")
            assert ctx == ""


def test_shared_context_for_includes_agent_headers():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            memory.append("bob", "decision", "use ruff")
            memory.append("charlie", "learning", "pytest fixtures")
            ctx = memory.shared_context_for("alice")
            assert "### bob" in ctx
            assert "### charlie" in ctx
            assert "## 团队共享知识" in ctx
