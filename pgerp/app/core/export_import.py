"""PyGo ERP V2.0 — CSV/Excel Export/Import."""
import sys
import os
import csv
import io
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


def get_db():
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@register("core.export.csv")
def export_csv(table=None, filters=None, **kwargs):
    if not table:
        return {"error": "table required"}
    db = get_db()
    tables = [r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if table not in tables:
        return {"error": f"table {table} not found", "available": tables}
    rows = db.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return {"error": "no data"}
    output = io.StringIO()
    writer = csv.writer(output)
    headers = rows[0].keys()
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row[h] for h in headers])
    return {"table": table, "format": "csv", "rows": len(rows), "content": output.getvalue(), "filename": f"{table}.csv"}


@register("core.import.csv")
def import_csv(table=None, data=None, has_header=True, **kwargs):
    if not table or not data:
        return {"error": "table and data required"}
    db = get_db()
    tables = [r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if table not in tables:
        return {"error": f"table {table} not found"}
    cols_info = db.execute(f"PRAGMA table_info({table})").fetchall()
    columns = [c["name"] for c in cols_info if c["name"] != "id"]
    lines = data.strip().split("\n") if isinstance(data, str) else data
    if not lines:
        return {"error": "empty"}
    reader = csv.reader(lines)
    headers = next(reader) if has_header else columns[:len(next(reader))]
    import_cols = [h for h in headers if h in columns]
    if not import_cols:
        return {"error": f"no matching columns. Expected: {columns}"}
    inserted = 0
    for row in reader:
        vals = []
        for col in import_cols:
            idx = headers.index(col) if col in headers else -1
            vals.append(row[idx] if idx >= 0 and idx < len(row) else None)
        placeholders = ", ".join(["?"] * len(import_cols))
        db.execute(f"INSERT INTO {table} ({','.join(import_cols)}) VALUES ({placeholders})", vals)
        inserted += 1
    db.commit()
    return {"table": table, "imported": inserted, "columns": import_cols}


@register("core.import.templates")
def import_templates(**kwargs):
    db = get_db()
    tables = {}
    for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_%' AND name NOT LIKE 'sqlite_%'").fetchall():
        table = r["name"]
        cols = db.execute(f"PRAGMA table_info({table})").fetchall()
        tables[table] = [{"name": c["name"], "type": c["type"], "nullable": not c["notnull"]} for c in cols if c["name"] != "id"]
    return {"tables": tables}
