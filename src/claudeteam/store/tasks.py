"""Local task store — coordination cards across agents.

One JSON file (`$CLAUDETEAM_STATE_DIR/tasks.json`) with shape:
    {"tasks": [...], "_meta": {"last_id": N}}

Each task:
    {id, title, description, assignee, creator,
     status, created_at, updated_at, completed_at,
     parent_task_id, depends_on}

Pure file-locked CRUD; lifecycle (assignment, completion, etc.) is whatever
the agents agree on — the store is opinion-free.

Status vocabulary: 待处理 / 进行中 / 已完成 / 已取消

Task tree model:
  - parent_task_id: str  — ID of parent task ("" for top-level tasks)
  - depends_on: list[str] — IDs of tasks that must complete before this one
  - subtasks(agent, parent_id) — list children of a parent task
"""

from __future__ import annotations

from pathlib import Path

from claudeteam.runtime import paths
from claudeteam.util import flock, now_ms, read_json, write_json

VALID_STATUSES = {"待处理", "进行中", "已完成", "已取消"}
DEFAULT_STATUS = "待处理"
TERMINAL_STATUSES = {"已完成", "已取消"}


def _file() -> Path:
    return paths.state_dir() / "tasks.json"


def _locked():
    return flock(_file().with_suffix(".lock"))


def _load() -> dict:
    return read_json(_file(), {"tasks": [], "_meta": {"last_id": 0}})


def _save(data: dict) -> None:
    write_json(_file(), data)


# ── public API ────────────────────────────────────────────────────


def create(
    assignee: str,
    title: str,
    *,
    description: str = "",
    creator: str = "",
    parent_task_id: str = "",
    depends_on: list[str] | None = None,
) -> str:
    """Create a new task; return its task_id (T-<n>).

    Args:
        parent_task_id: ID of parent task ("" for top-level).
        depends_on: list of task IDs that must complete before this one.
    """
    if not title.strip():
        raise ValueError("title cannot be empty")
    with _locked():
        data = _load()
        data["_meta"]["last_id"] = data["_meta"].get("last_id", 0) + 1
        tid = f"T-{data['_meta']['last_id']}"
        now = now_ms()
        data.setdefault("tasks", []).append(
            {
                "id": tid,
                "title": title.strip(),
                "description": description,
                "assignee": assignee,
                "creator": creator,
                "status": DEFAULT_STATUS,
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
                "parent_task_id": parent_task_id,
                "depends_on": list(depends_on) if depends_on else [],
            }
        )
        _save(data)
        return tid


def update(
    task_id: str,
    *,
    status: str | None = None,
    assignee: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> bool:
    """Apply non-None fields. Returns False if task_id not found."""
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status} (valid: {sorted(VALID_STATUSES)})")
    with _locked():
        data = _load()
        for task in data.get("tasks", []):
            if task["id"] != task_id:
                continue
            if status is not None:
                task["status"] = status
                if status in TERMINAL_STATUSES:
                    task["completed_at"] = now_ms()
                else:
                    task["completed_at"] = None
            if assignee is not None:
                task["assignee"] = assignee
            if title is not None:
                task["title"] = title.strip()
            if description is not None:
                task["description"] = description
            task["updated_at"] = now_ms()
            _save(data)
            return True
    return False


def get(task_id: str) -> dict | None:
    for task in _load().get("tasks", []):
        if task["id"] == task_id:
            return task
    return None


def list_tasks(*, status: str | None = None, assignee: str | None = None) -> list[dict]:
    """Return tasks filtered by status / assignee, sorted by id."""
    rows = list(_load().get("tasks", []))
    if status is not None:
        rows = [t for t in rows if t.get("status") == status]
    if assignee is not None:
        rows = [t for t in rows if t.get("assignee") == assignee]
    rows.sort(key=lambda t: int(t["id"].split("-")[1]) if "-" in t["id"] else 0)
    return rows


def subtasks(parent_id: str) -> list[dict]:
    """Return direct children of `parent_id`, sorted by id.

    Tasks created before the tree model won't have `parent_task_id`;
    those default to "" (top-level) so they never appear as children.
    """
    rows = [t for t in _load().get("tasks", []) if t.get("parent_task_id") == parent_id]
    rows.sort(key=lambda t: int(t["id"].split("-")[1]) if "-" in t["id"] else 0)
    return rows


def blocked_tasks() -> list[dict]:
    """Return tasks whose `depends_on` includes at least one non-terminal task.

    Useful for agents checking "can I start this task now?".
    """
    data = _load()
    all_tasks = {t["id"]: t for t in data.get("tasks", [])}
    blocked = []
    for task in data.get("tasks", []):
        deps = task.get("depends_on", [])
        if not deps:
            continue
        for dep_id in deps:
            dep = all_tasks.get(dep_id)
            if dep and dep.get("status") not in TERMINAL_STATUSES:
                blocked.append(task)
                break
    return blocked
