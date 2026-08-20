"""PyGo ERP — Universal audit trail and entity attachments.

audit_record() is generic: any module can log a change on any entity without
the core needing to know that entity exists.
"""
import os
import sys
import json
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


def get_db():
    import sqlite3
    conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=15000")
    except Exception:
        pass
    return conn


def _parse(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return None
    return x


def _diff(old, new):
    """Field-level diff between two dicts."""
    old = old or {}
    new = new or {}
    changes = {}
    for key in set(list(old.keys()) + list(new.keys())):
        o = old.get(key)
        n = new.get(key)
        if o != n:
            changes[key] = {"from": o, "to": n}
    return changes


def audit_record(entity_type, entity_id, action, user_id=None, user_email=None,
                 old_values=None, new_values=None, ip_address=None, company_id=None):
    """Internal API: log an audit entry. Never raises — auditing must not break writes."""
    try:
        db = get_db()
        changes = _diff(old_values, new_values) if (old_values or new_values) else {}
        db.execute(
            "INSERT INTO audit_log (entity_type, entity_id, action, user_id, user_email, "
            "changes, old_values, new_values, ip_address, company_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_type, entity_id, action, user_id, user_email,
             json.dumps(changes, default=str),
             json.dumps(old_values, default=str) if old_values else None,
             json.dumps(new_values, default=str) if new_values else None,
             ip_address, company_id),
        )
        db.commit()
        return True
    except Exception:
        return False


@register("core.audit.record")
def audit_record_handler(
    entity_type=None, entity_id=None, action=None, user_id=None, user_email=None,
    old_values=None, new_values=None, ip_address=None, company_id=None, **kwargs
):
    """Log an audit entry for any entity."""
    if not entity_type or not action:
        return {"error": "entity_type and action required"}
    if action not in ("create", "update", "delete", "view", "approve", "reject",
                      "confirm", "cancel", "login", "logout", "export", "import"):
        return {"error": "unsupported action",
                "allowed": ["create", "update", "delete", "view", "approve", "reject",
                            "confirm", "cancel", "login", "logout", "export", "import"]}

    old_values = _parse(old_values)
    new_values = _parse(new_values)
    ok = audit_record(entity_type, entity_id, action, user_id, user_email,
                      old_values, new_values, ip_address, company_id)
    if not ok:
        return {"error": "failed to record audit entry"}
    return {
        "recorded": True,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "changed_fields": list(_diff(old_values, new_values).keys()),
    }


@register("core.audit.history")
def audit_history(entity_type=None, entity_id=None, limit=50, **kwargs):
    """Full change history for one entity."""
    if not entity_type:
        return {"error": "entity_type required"}
    db = get_db()
    sql = "SELECT * FROM audit_log WHERE entity_type = ?"
    params = [entity_type]
    if entity_id:
        sql += " AND entity_id = ?"
        params.append(entity_id)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(int(limit))

    rows = db.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for field in ("changes", "old_values", "new_values"):
            try:
                d[field] = json.loads(r[field]) if r[field] else None
            except Exception:
                pass
        out.append(d)
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entries": out,
        "count": len(out),
    }


@register("core.audit.by_user")
def audit_by_user(user_id=None, date_from=None, date_to=None, limit=100, **kwargs):
    """Everything a user did (accountability trail)."""
    if not user_id:
        return {"error": "user_id required"}
    db = get_db()
    sql = "SELECT * FROM audit_log WHERE user_id = ?"
    params = [user_id]
    if date_from:
        sql += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND created_at <= ?"
        params.append(date_to)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))

    rows = db.execute(sql, params).fetchall()
    by_action = {}
    by_entity = {}
    for r in rows:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
        by_entity[r["entity_type"]] = by_entity.get(r["entity_type"], 0) + 1

    return {
        "user_id": user_id,
        "entries": [dict(r) for r in rows],
        "count": len(rows),
        "by_action": by_action,
        "by_entity": by_entity,
    }


@register("core.audit.summary")
def audit_summary(date_from=None, date_to=None, **kwargs):
    """Audit activity overview."""
    db = get_db()
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if date_from:
        sql += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND created_at <= ?"
        params.append(date_to)
    rows = db.execute(sql, params).fetchall()

    by_action, by_entity, by_user = {}, {}, {}
    for r in rows:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
        by_entity[r["entity_type"]] = by_entity.get(r["entity_type"], 0) + 1
        key = r["user_email"] or f"user_{r['user_id']}" if r["user_id"] else "system"
        by_user[key] = by_user.get(key, 0) + 1

    return {
        "period": {"from": date_from, "to": date_to},
        "total_entries": len(rows),
        "by_action": by_action,
        "by_entity": dict(sorted(by_entity.items(), key=lambda x: -x[1])),
        "by_user": dict(sorted(by_user.items(), key=lambda x: -x[1])),
    }


# --- Attachments ---

@register("core.attachments.list")
def attachments_list(entity_type=None, entity_id=None, **kwargs):
    """Files attached to an entity."""
    db = get_db()
    sql = "SELECT * FROM attachments WHERE 1=1"
    params = []
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        sql += " AND entity_id = ?"
        params.append(entity_id)
    sql += " ORDER BY created_at DESC"
    rows = db.execute(sql, params).fetchall()
    total = sum(int(r["size_bytes"] or 0) for r in rows)
    return {
        "attachments": [dict(r) for r in rows],
        "count": len(rows),
        "total_size_bytes": total,
        "total_size_kb": round(total / 1024, 2),
    }


@register("core.attachments.attach")
def attachments_attach(
    entity_type=None, entity_id=None, filename=None, file_id=None,
    mime_type=None, size_bytes=0, storage_path=None, description=None,
    uploaded_by=None, company_id=None, **kwargs
):
    """Attach a file to any entity. Works for records the core doesn't know about."""
    if not entity_type or not entity_id:
        return {"error": "entity_type and entity_id required"}
    if not filename and not file_id:
        return {"error": "filename or file_id required"}

    db = get_db()
    resolved_name = filename
    resolved_path = storage_path
    resolved_size = int(size_bytes or 0)
    resolved_mime = mime_type

    # If it points at an uploaded file, inherit its metadata
    if file_id:
        f = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if f:
            cols = f.keys()
            resolved_name = resolved_name or (f["original_name"] if "original_name" in cols else None) \
                or (f["filename"] if "filename" in cols else None)
            resolved_path = resolved_path or (f["path"] if "path" in cols else None)
            if not resolved_size and "size" in cols:
                resolved_size = int(f["size"] or 0)
            resolved_mime = resolved_mime or (f["mime_type"] if "mime_type" in cols else None)

    cur = db.execute(
        "INSERT INTO attachments (entity_type, entity_id, file_id, filename, mime_type, "
        "size_bytes, storage_path, description, uploaded_by, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_type, entity_id, file_id, resolved_name, resolved_mime,
         resolved_size, resolved_path, description, uploaded_by, company_id),
    )
    db.commit()

    audit_record(entity_type, entity_id, "update", user_id=uploaded_by,
                 new_values={"attachment": resolved_name}, company_id=company_id)

    return {
        "id": cur.lastrowid,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "filename": resolved_name,
        "attached": True,
    }


@register("core.attachments.detach")
def attachments_detach(id=None, attachment_id=None, **kwargs):
    """Remove an attachment link."""
    aid = attachment_id or id
    if not aid:
        return {"error": "attachment_id required"}
    db = get_db()
    row = db.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if not row:
        return {"error": "attachment not found"}
    db.execute("DELETE FROM attachments WHERE id = ?", (aid,))
    db.commit()
    return {
        "detached": True,
        "id": aid,
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "note": "the stored file itself is preserved",
    }


@register("core.attachments.summary")
def attachments_summary(**kwargs):
    """Attachment usage grouped by entity type."""
    db = get_db()
    rows = db.execute(
        "SELECT entity_type, COUNT(*) AS count, COALESCE(SUM(size_bytes),0) AS bytes "
        "FROM attachments GROUP BY entity_type ORDER BY count DESC"
    ).fetchall()
    total = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM attachments"
    ).fetchone()
    return {
        "by_entity": [
            {"entity_type": r["entity_type"], "count": r["count"],
             "size_kb": round(float(r["bytes"]) / 1024, 2)}
            for r in rows
        ],
        "total_attachments": total[0],
        "total_size_kb": round(float(total[1] or 0) / 1024, 2),
    }
