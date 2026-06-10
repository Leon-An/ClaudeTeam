"""Tests for `claudeteam task` subcommand dispatcher."""
from __future__ import annotations

import io

from helpers import isolated_env, run_cli
from claudeteam.store import local_facts, tasks


# ── create ────────────────────────────────────────────────────────


def test_task_create_minimal():
    with isolated_env():
        rc, out, _ = run_cli(["task", "create", "worker", "do task X"])
        assert rc == 0
        assert "created T-1" in out
        rows = tasks.list_tasks()
        assert rows[0]["title"] == "do task X"
        assert rows[0]["assignee"] == "worker"


def test_task_create_with_by_and_desc():
    with isolated_env():
        run_cli(["task", "create", "worker", "task name",
              "--by", "manager", "--desc", "root cause Y"])
        t = tasks.list_tasks()[0]
        assert t["creator"] == "manager"
        assert t["description"] == "root cause Y"


def test_task_create_title_with_spaces():
    with isolated_env():
        run_cli(["task", "create", "worker", "fix", "the", "broken", "thing"])
        t = tasks.list_tasks()[0]
        assert t["title"] == "fix the broken thing"


def test_task_create_missing_args_returns_one():
    with isolated_env():
        rc, _, err = run_cli(["task", "create", "worker"])
        assert rc == 1
        assert "usage:" in err


# ── update ────────────────────────────────────────────────────────


def test_task_update_status():
    with isolated_env():
        tasks.create("w", "x")
        rc, out, _ = run_cli(["task", "update", "T-1", "--status", "进行中"])
        assert rc == 0
        assert tasks.get("T-1")["status"] == "进行中"


def test_task_update_invalid_status_returns_one():
    with isolated_env():
        tasks.create("w", "x")
        rc, _, err = run_cli(["task", "update", "T-1", "--status", "bogus"])
        assert rc == 1
        assert "invalid status" in err


def test_task_update_unknown_id_returns_one():
    with isolated_env():
        rc, _, err = run_cli(["task", "update", "T-99", "--status", "已完成"])
        assert rc == 1
        assert "no such task" in err


def test_task_update_can_reassign_and_retitle():
    with isolated_env():
        tasks.create("w1", "old")
        run_cli(["task", "update", "T-1", "--assignee", "w2", "--title", "new"])
        t = tasks.get("T-1")
        assert t["assignee"] == "w2"
        assert t["title"] == "new"


# ── done shortcut ────────────────────────────────────────────────


def test_task_done_marks_completed():
    with isolated_env():
        tasks.create("w", "x")
        rc, out, _ = run_cli(["task", "done", "T-1"])
        assert rc == 0
        t = tasks.get("T-1")
        assert t["status"] == "已完成"
        assert t["completed_at"] is not None


# ── list / get ────────────────────────────────────────────────────


def test_task_list_empty():
    with isolated_env():
        rc, out, _ = run_cli(["task", "list"])
        assert rc == 0
        assert "no matching tasks" in out


def test_task_list_shows_count_and_each_row():
    with isolated_env():
        tasks.create("w", "first task")
        tasks.create("w", "second task")
        rc, out, _ = run_cli(["task", "list"])
        assert rc == 0
        assert "2 tasks" in out
        assert "first task" in out and "second task" in out


def test_task_list_filter_by_status_and_assignee():
    with isolated_env():
        tasks.create("alice", "a-task")
        tasks.create("bob", "b-task")
        tasks.create("alice", "a-done")
        tasks.update("T-3", status="已完成")

        rc, out, _ = run_cli(["task", "list", "--assignee", "alice"])
        assert rc == 0
        assert "a-task" in out and "a-done" in out
        assert "b-task" not in out

        rc, out, _ = run_cli(["task", "list", "--status", "已完成"])
        assert rc == 0
        assert "a-done" in out
        assert "a-task" not in out


def test_task_get_existing_renders_full_card():
    with isolated_env():
        tasks.create("w", "task one", description="d")
        rc, out, _ = run_cli(["task", "get", "T-1"])
        assert rc == 0
        assert "T-1" in out and "task one" in out
        assert "desc: d" in out


def test_task_get_unknown_id_returns_one():
    with isolated_env():
        rc, _, err = run_cli(["task", "get", "T-99"])
        assert rc == 1
        assert "no such task" in err


# ── dispatcher ───────────────────────────────────────────────────


def test_task_no_args_prints_usage():
    rc, out, _ = run_cli(["task"])
    # treated as "show usage"; behaviour-wise rc==1 since no subcmd
    assert "usage:" in out
    assert rc == 1


def test_task_unknown_subcommand_returns_one():
    rc, _, err = run_cli(["task", "invent"])
    assert rc == 1
    assert "unknown task subcommand" in err


# ── intent ────────────────────────────────────────────────────────


def test_task_intent_create_and_get():
    with isolated_env():
        rc, out, _ = run_cli(["task", "intent", "create", "把首页改深色",
                              "--src", "msg_9"])
        assert rc == 0 and "I-1" in out
        rc, out, _ = run_cli(["task", "intent", "get", "I-1"])
        assert rc == 0
        assert "把首页改深色" in out


def test_task_create_with_intent_backlink():
    with isolated_env():
        tasks.create_intent("原话")            # I-1
        run_cli(["task", "create", "w", "子任务", "--intent", "I-1"])
        assert tasks.get("T-1")["intent_id"] == "I-1"


def test_task_intent_get_unknown_returns_one():
    with isolated_env():
        rc, _, err = run_cli(["task", "intent", "get", "I-99"])
        assert rc == 1
        assert "no such intent" in err


# ── pause / approve / reject ──────────────────────────────────────


def _make_in_progress(assignee="w"):
    tasks.create(assignee, "t")
    tasks.update("T-1", status="进行中")


def test_task_pause_suspends_and_routes_to_approver():
    with isolated_env():
        _make_in_progress()
        rc, out, _ = run_cli(["task", "pause", "T-1", "--note", "要拍板",
                              "--by", "w"])
        assert rc == 0 and "需审批" in out
        assert tasks.get("T-1")["status"] == "需审批"
        # an approval-request message lands in the boss inbox, tagged task_id
        msgs = local_facts.list_messages("user")
        assert any(m["task_id"] == "T-1" for m in msgs)


def test_task_pause_non_in_progress_returns_one():
    with isolated_env():
        tasks.create("w", "t")                # 待处理
        rc, _, err = run_cli(["task", "pause", "T-1"])
        assert rc == 1
        assert "cannot pause" in err


def test_task_approve_continue():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        rc, out, _ = run_cli(["task", "approve", "T-1"])
        assert rc == 0
        assert tasks.get("T-1")["status"] == "进行中"
        # decision echoed back to the assignee inbox
        assert any(m["task_id"] == "T-1" for m in local_facts.list_messages("w"))


def test_task_approve_done():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        rc, _, _ = run_cli(["task", "approve", "T-1", "--done"])
        assert rc == 0
        assert tasks.get("T-1")["status"] == "已完成"


def test_task_approve_non_suspended_returns_one():
    with isolated_env():
        _make_in_progress()
        rc, _, err = run_cli(["task", "approve", "T-1"])
        assert rc == 1
        assert "cannot approve" in err


def test_task_reject_rework_with_feedback():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        rc, _, _ = run_cli(["task", "reject", "T-1", "方向", "错了"])
        assert rc == 0
        t = tasks.get("T-1")
        assert t["status"] == "进行中"
        assert t["approval_note"] == "方向 错了"


def test_task_reject_cancel():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        rc, _, _ = run_cli(["task", "reject", "T-1", "不做了", "--cancel"])
        assert rc == 0
        assert tasks.get("T-1")["status"] == "已取消"


def test_task_update_cannot_bypass_gate_via_cli():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        rc, _, err = run_cli(["task", "update", "T-1", "--status", "已完成"])
        assert rc == 1
        assert "需审批" in err
        assert tasks.get("T-1")["status"] == "需审批"


def test_task_transition_writes_audit_log():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        run_cli(["task", "approve", "T-1", "--done"])
        logs = local_facts.list_logs("w")
        kinds = [(l["type"], l["ref"]) for l in logs]
        assert ("task_transition", "T-1") in kinds


def test_task_reject_non_suspended_returns_one():
    with isolated_env():
        _make_in_progress()                       # 进行中, not 需审批
        rc, _, err = run_cli(["task", "reject", "T-1", "无效打回"])
        assert rc == 1
        assert "cannot reject" in err
        assert tasks.get("T-1")["status"] == "进行中"


def test_task_reject_rework_echoes_to_assignee_and_logs():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        run_cli(["task", "reject", "T-1", "方向错了"])
        # decision echoes back to the assignee inbox, tagged with task_id
        assert any(m["task_id"] == "T-1"
                   for m in local_facts.list_messages("w"))
        # and the transition is audited
        kinds = [(l["type"], l["ref"]) for l in local_facts.list_logs("w")]
        assert ("task_transition", "T-1") in kinds


def test_task_reject_cancel_echoes_to_assignee_and_logs():
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        run_cli(["task", "reject", "T-1", "作废", "--cancel"])
        assert tasks.get("T-1")["status"] == "已取消"
        assert any(m["task_id"] == "T-1"
                   for m in local_facts.list_messages("w"))


def test_task_pause_routes_to_explicit_approver_via_to():
    """`--to manager` sends the approval request to that inbox (not boss),
    and records awaiting=manager on the task."""
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1", "--note", "拍板", "--to", "manager"])
        assert tasks.get("T-1")["awaiting"] == "manager"
        assert any(m["task_id"] == "T-1"
                   for m in local_facts.list_messages("manager"))
        # boss inbox should NOT receive it when routed elsewhere
        assert not any(m["task_id"] == "T-1"
                       for m in local_facts.list_messages("user"))


def test_task_intent_create_empty_returns_one():
    with isolated_env():
        rc, _, err = run_cli(["task", "intent", "create", "   "])
        assert rc == 1
        assert "empty" in err


# ── gate: no CLI path may bypass the 需审批 suspend ────────────────


def test_task_done_shortcut_cannot_bypass_gate():
    """`task done` is sugar for `update --status 已完成`; on a suspended task
    it must hit the same gate and refuse."""
    with isolated_env():
        _make_in_progress()
        run_cli(["task", "pause", "T-1"])
        rc, _, err = run_cli(["task", "done", "T-1"])
        assert rc == 1
        assert "需审批" in err
        assert tasks.get("T-1")["status"] == "需审批"


def test_task_update_cannot_force_into_suspend_via_cli():
    with isolated_env():
        _make_in_progress()                       # 进行中
        rc, _, err = run_cli(["task", "update", "T-1", "--status", "需审批"])
        assert rc == 1
        assert "需审批" in err
        assert tasks.get("T-1")["status"] == "进行中"
