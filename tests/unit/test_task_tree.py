"""Tests for task tree model — parent/subtask/depends_on.

Verifies the extended tasks.py schema:
  - create with parent_task_id
  - create with depends_on
  - subtasks() query
  - blocked_tasks() query
  - backward compat: tasks without tree fields still work
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from helpers import env_patch
from claudeteam.store import tasks


def _isolated():
    """Context manager: isolated state dir for task store."""
    return tempfile.TemporaryDirectory()


def test_create_with_parent_task_id():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            parent = tasks.create("alice", "parent task")
            child = tasks.create("bob", "child task", parent_task_id=parent)
            t = tasks.get(child)
            assert t["parent_task_id"] == parent


def test_create_default_parent_is_empty():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            tid = tasks.create("alice", "top-level")
            t = tasks.get(tid)
            assert t["parent_task_id"] == ""


def test_create_with_depends_on():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            dep1 = tasks.create("alice", "dep 1")
            dep2 = tasks.create("alice", "dep 2")
            child = tasks.create("bob", "depends on both", depends_on=[dep1, dep2])
            t = tasks.get(child)
            assert t["depends_on"] == [dep1, dep2]


def test_create_default_depends_on_is_empty():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            tid = tasks.create("alice", "no deps")
            t = tasks.get(tid)
            assert t["depends_on"] == []


def test_subtasks_returns_children():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            parent = tasks.create("alice", "parent")
            c1 = tasks.create("bob", "child 1", parent_task_id=parent)
            c2 = tasks.create("bob", "child 2", parent_task_id=parent)
            tasks.create("alice", "unrelated")
            children = tasks.subtasks(parent)
            assert len(children) == 2
            ids = [c["id"] for c in children]
            assert c1 in ids and c2 in ids


def test_subtasks_empty_for_leaf_task():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            tid = tasks.create("alice", "leaf")
            assert tasks.subtasks(tid) == []


def test_subtasks_empty_for_nonexistent_parent():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            assert tasks.subtasks("T-999") == []


def test_blocked_tasks_returns_tasks_with_incomplete_deps():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            dep = tasks.create("alice", "blocking task")
            blocked = tasks.create("bob", "waiting task", depends_on=[dep])
            free = tasks.create("alice", "free task")
            result = tasks.blocked_tasks()
            ids = [t["id"] for t in result]
            assert blocked in ids
            assert free not in ids


def test_blocked_tasks_empty_when_deps_completed():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            dep = tasks.create("alice", "done task")
            tasks.update(dep, status="已完成")
            tasks.create("bob", "now free", depends_on=[dep])
            result = tasks.blocked_tasks()
            assert len(result) == 0


def test_blocked_tasks_empty_when_no_deps():
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            tasks.create("alice", "independent")
            assert tasks.blocked_tasks() == []


def test_backward_compat_tasks_without_tree_fields():
    """Tasks created before the tree model (no parent_task_id/depends_on)
    should still work — get/list treat missing fields as defaults."""
    with _isolated() as tmp:
        with env_patch(CLAUDETEAM_STATE_DIR=str(Path(tmp) / "state")):
            # Simulate old-format task by writing directly
            from claudeteam.util import write_json
            from claudeteam.runtime import paths
            write_json(
                paths.state_dir() / "tasks.json",
                {
                    "tasks": [
                        {
                            "id": "T-1",
                            "title": "old task",
                            "description": "",
                            "assignee": "alice",
                            "creator": "",
                            "status": "待处理",
                            "created_at": 1000,
                            "updated_at": 1000,
                            "completed_at": None,
                        }
                    ],
                    "_meta": {"last_id": 1},
                },
            )
            # get should work
            t = tasks.get("T-1")
            assert t["title"] == "old task"
            # subtasks should not crash on missing field
            assert tasks.subtasks("T-1") == []
            # list should work
            all_tasks = tasks.list_tasks()
            assert len(all_tasks) == 1
