"""PyGo ERP V2.0 — File upload handlers."""
import sys
import os
import uuid
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.registry import register


UPLOAD_DIR = os.environ.get("PYGO_UPLOADS", "/tmp/pgerp_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def save_file(file_data, filename, mime_type, related_type=None, related_id=None, user_id=None):
    """Save file to filesystem and database."""
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    
    with open(file_path, 'wb') as f:
        if isinstance(file_data, str):
            f.write(file_data.encode())
        else:
            f.write(file_data)
    
    size = os.path.getsize(file_path)
    
    db = get_db()
    cursor = db.execute(
        """INSERT INTO files (filename, original_name, mime_type, size, path, related_type, related_id, user_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (unique_name, filename, mime_type, size, file_path, related_type, related_id, user_id, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {
        "id": cursor.lastrowid,
        "filename": unique_name,
        "original_name": filename,
        "mime_type": mime_type,
        "size": size,
    }


@register("core.files.list")
def files_list(related_type=None, related_id=None, **kwargs):
    """List files (optionally filtered)."""
    db = get_db()
    query = "SELECT * FROM files"
    filters = []
    params = []
    if related_type:
        filters.append("related_type = ?")
        params.append(related_type)
    if related_id:
        filters.append("related_id = ?")
        params.append(related_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.files.get")
def files_get(file_id=None, **kwargs):
    """Get file info."""
    if not file_id:
        return {"error": "file_id required"}
    db = get_db()
    row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    return dict(row)


@register("core.files.delete")
def files_delete(file_id=None, **kwargs):
    """Delete file."""
    if not file_id:
        return {"error": "file_id required"}
    db = get_db()
    row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    try:
        os.unlink(row["path"])
    except FileNotFoundError:
        pass
    db.execute("DELETE FROM files WHERE id = ?", (file_id,))
    db.commit()
    return {"deleted": True, "file_id": file_id}
