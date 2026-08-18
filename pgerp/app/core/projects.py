"""PyGo ERP V2.0 — Projects module.

Provides:
- Project management (proyectos)
- Task management (tareas) with hierarchy
- Time tracking (timesheets / registros de tiempo)
- Milestones (hitos)
- Project status workflow
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.auth import Session, User
from core.registry import register


def get_db():
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# --- Projects ---

@register("core.projects.list")
def projects_list(status=None, **kwargs):
    """List projects (optionally filtered by status)."""
    db = get_db()
    query = "SELECT * FROM projects"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.projects.create")
def projects_create(name=None, description=None, start_date=None, end_date=None, token=None, **kwargs):
    """Create a project."""
    if not name:
        return {"error": "name required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
        user_id = user.id
    else:
        user_id = None
    
    cursor = db.execute(
        """INSERT INTO projects (name, description, status, start_date, end_date, user_id, created_at)
           VALUES (?, ?, 'planning', ?, ?, ?, ?)""",
        (name, description, start_date, end_date, user_id, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "status": "planning"}


@register("core.projects.update")
def projects_update(project_id=None, token=None, **kwargs):
    """Update a project."""
    if not project_id:
        return {"error": "project_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    
    allowed = ["name", "description", "status", "start_date", "end_date"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [project_id]
        db.execute(f"UPDATE projects SET {sets} WHERE id = ?", vals)
        db.commit()
    
    return dict(db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


@register("core.projects.delete")
def projects_delete(project_id=None, token=None):
    """Delete a project."""
    if not project_id:
        return {"error": "project_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    # Check for tasks
    task_count = db.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (project_id,)).fetchone()[0]
    if task_count > 0:
        return {"error": "project has tasks, delete them first"}
    
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    return {"deleted": True, "project_id": project_id}


# --- Tasks ---

@register("core.projects.tasks.list")
def tasks_list(project_id=None, status=None, **kwargs):
    """List tasks (optionally filtered)."""
    db = get_db()
    query = """
        SELECT t.*, p.name as project_name, u.full_name as assigned_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u ON t.assigned_to = u.id
    """
    filters = []
    params = []
    if project_id:
        filters.append("t.project_id = ?")
        params.append(project_id)
    if status:
        filters.append("t.status = ?")
        params.append(status)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY t.created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.projects.tasks.create")
def tasks_create(project_id=None, title=None, description=None, assigned_to=None, priority="medium", due_date=None, token=None, **kwargs):
    """Create a task."""
    if not project_id or not title:
        return {"error": "project_id and title required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
    
    cursor = db.execute(
        """INSERT INTO tasks (project_id, title, description, assigned_to, priority, status, due_date, created_at)
           VALUES (?, ?, ?, ?, ?, 'todo', ?, ?)""",
        (project_id, title, description, assigned_to, priority, due_date, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "status": "todo"}


@register("core.projects.tasks.update")
def tasks_update(task_id=None, token=None, **kwargs):
    """Update a task."""
    if not task_id:
        return {"error": "task_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    
    allowed = ["title", "description", "assigned_to", "priority", "status", "due_date", "completed_at"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [task_id]
        db.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
        db.commit()
    
    return dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


@register("core.projects.tasks.complete")
def tasks_complete(token=None, **kwargs):
    task_id = kwargs.get("task_id") or kwargs.get("id")
    """Mark task as completed."""
    if not task_id:
        return {"error": "task_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    db.execute("UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
               (datetime.utcnow().isoformat(), task_id))
    db.commit()
    
    return {"completed": True, "task_id": task_id}


@register("core.projects.tasks.delete")
def tasks_delete(task_id=None, token=None):
    """Delete a task."""
    if not task_id:
        return {"error": "task_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    # Delete timesheets
    db.execute("DELETE FROM timesheets WHERE task_id = ?", (task_id,))
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    
    return {"deleted": True, "task_id": task_id}


# --- Timesheets ---

@register("core.projects.timesheets.list")
def timesheets_list(task_id=None, user_id=None, **kwargs):
    """List time entries."""
    db = get_db()
    query = """
        SELECT ts.*, t.title as task_title, p.name as project_name, u.full_name as user_name
        FROM timesheets ts
        LEFT JOIN tasks t ON ts.task_id = t.id
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u ON ts.user_id = u.id
    """
    filters = []
    params = []
    if task_id:
        filters.append("ts.task_id = ?")
        params.append(task_id)
    if user_id:
        filters.append("ts.user_id = ?")
        params.append(user_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY ts.date DESC LIMIT 200"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.projects.timesheets.create")
def timesheets_create(task_id=None, hours=None, description=None, date=None, token=None, **kwargs):
    """Log time on a task."""
    if not task_id or not hours:
        return {"error": "task_id and hours required"}
    
    try:
        hrs = float(hours)
    except ValueError:
        return {"error": "invalid hours"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
        user_id = user.id
    else:
        user_id = None
    
    cursor = db.execute(
        """INSERT INTO timesheets (task_id, user_id, hours, description, date, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (task_id, user_id, hrs, description, date or datetime.utcnow().isoformat()[:10], datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "hours": hrs}


@register("core.projects.timesheets.summary")
def timesheets_summary(project_id=None, **kwargs):
    """Time summary per project or task."""
    db = get_db()
    
    if project_id:
        rows = db.execute("""
            SELECT t.id, t.title, COALESCE(SUM(ts.hours), 0) as total_hours
            FROM tasks t
            LEFT JOIN timesheets ts ON ts.task_id = t.id
            WHERE t.project_id = ?
            GROUP BY t.id
        """, (project_id,)).fetchall()
        return [dict(r) for r in rows]
    else:
        rows = db.execute("""
            SELECT p.id, p.name, COALESCE(SUM(ts.hours), 0) as total_hours
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            LEFT JOIN timesheets ts ON ts.task_id = t.id
            GROUP BY p.id
        """).fetchall()
        return [dict(r) for r in rows]


# --- Milestones ---

@register("core.projects.milestones.list")
def milestones_list(project_id=None, **kwargs):
    """List milestones."""
    db = get_db()
    query = "SELECT * FROM milestones"
    params = []
    if project_id:
        query += " WHERE project_id = ?"
        params.append(project_id)
    query += " ORDER BY due_date"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.projects.milestones.create")
def milestones_create(project_id=None, name=None, due_date=None, description=None, token=None, **kwargs):
    """Create a milestone."""
    if not project_id or not name:
        return {"error": "project_id and name required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    cursor = db.execute(
        "INSERT INTO milestones (project_id, name, description, due_date, created_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, name, description, due_date, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid}


@register("core.projects.dashboard")
def projects_dashboard(**kwargs):
    """Projects dashboard stats."""
    db = get_db()
    
    return {
        "total_projects": db.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
        "active_projects": db.execute("SELECT COUNT(*) FROM projects WHERE status IN ('planning', 'in_progress')").fetchone()[0],
        "completed_projects": db.execute("SELECT COUNT(*) FROM projects WHERE status = 'completed'").fetchone()[0],
        "total_tasks": db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
        "pending_tasks": db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'todo'").fetchone()[0],
        "in_progress_tasks": db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'").fetchone()[0],
        "completed_tasks": db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'").fetchone()[0],
        "total_hours": db.execute("SELECT COALESCE(SUM(hours), 0) FROM timesheets").fetchone()[0],
    }
