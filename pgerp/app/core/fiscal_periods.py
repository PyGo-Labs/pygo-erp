"""PyGo ERP — Fiscal period locking.

fiscal_periods existed but nothing enforced it: a journal entry could be posted
into a "closed" period. assert_period_open() is the guard every posting path
must call.
"""
import os
import sys
import sqlite3
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register  # noqa: E402

DB_PATH = os.environ.get("PYGO_DB", "/tmp/pgerp.db")

_LAST_DAY = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _month_end(year, month):
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        return 29
    return _LAST_DAY[month - 1]


def _normalise(date_str):
    """Accept 'YYYY-MM-DD' or a full timestamp; return the date part."""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    return str(date_str)[:10]


def find_period(db, date_str):
    """Period covering a date, matching by explicit range or by year/month."""
    d = _normalise(date_str)
    row = db.execute(
        "SELECT * FROM fiscal_periods WHERE date_from IS NOT NULL "
        "AND date_to IS NOT NULL AND ? BETWEEN date_from AND date_to LIMIT 1",
        (d,)).fetchone()
    if row:
        return row
    try:
        year, month = int(d[0:4]), int(d[5:7])
    except (ValueError, IndexError):
        return None
    return db.execute(
        "SELECT * FROM fiscal_periods WHERE year = ? AND month = ? LIMIT 1",
        (year, month)).fetchone()


def assert_period_open(db, date_str):
    """Return None when posting is allowed, or an error dict when it is not.

    A date with no period defined is allowed: periods are opt-in, and refusing
    unknown dates would break every install that never created them.
    """
    period = find_period(db, date_str)
    if not period:
        return None
    status = (period["status"] or "open").lower()
    locked = int(period["is_locked"] or 0)
    if locked or status in ("closed", "locked"):
        label = period["name"] or f"{period['year']}-{int(period['month'] or 1):02d}"
        return {"error": f"fiscal period {label} is closed — posting on "
                         f"{_normalise(date_str)} is not allowed",
                "period": label, "status": "locked" if locked else status}
    return None


# ------------------------------------------------------------------- handlers

@register("core.periods.list")
def periods_list(year=None, **kwargs):
    db = get_db()
    if year:
        rows = db.execute(
            "SELECT * FROM fiscal_periods WHERE year = ? ORDER BY year, month",
            (year,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fiscal_periods ORDER BY year DESC, month DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["is_locked"] = bool(d.get("is_locked"))
        d["name"] = d.get("name") or f"{d['year']}-{int(d.get('month') or 1):02d}"
        out.append(d)
    db.close()
    return out


@register("core.periods.create")
def periods_create(year=None, month=None, name=None, company_id=None, **kwargs):
    """Create a monthly period with an explicit date range."""
    if not year or not month:
        return {"error": "year and month required"}
    try:
        year, month = int(year), int(month)
    except (TypeError, ValueError):
        return {"error": "year and month must be numeric"}
    if not 1 <= month <= 12:
        return {"error": "month must be between 1 and 12"}

    db = get_db()
    if db.execute("SELECT 1 FROM fiscal_periods WHERE year = ? AND month = ?",
                  (year, month)).fetchone():
        db.close()
        return {"error": f"period {year}-{month:02d} already exists"}

    date_from = f"{year}-{month:02d}-01"
    date_to = f"{year}-{month:02d}-{_month_end(year, month):02d}"
    label = name or f"{year}-{month:02d}"
    cur = db.execute(
        "INSERT INTO fiscal_periods (year, month, status, date_from, date_to, name) "
        "VALUES (?, ?, 'open', ?, ?, ?)",
        (year, month, date_from, date_to, label))
    db.commit()
    pid = cur.lastrowid
    db.close()
    return {"id": pid, "name": label, "year": year, "month": month,
            "date_from": date_from, "date_to": date_to, "status": "open"}


@register("core.periods.generate_year")
def periods_generate_year(year=None, **kwargs):
    """Create the 12 monthly periods of a fiscal year (idempotent)."""
    if not year:
        return {"error": "year required"}
    created = []
    for month in range(1, 13):
        r = periods_create(year=year, month=month)
        if "error" not in r:
            created.append(r["name"])
    return {"year": int(year), "created": created, "count": len(created)}


@register("core.periods.close")
def periods_close(period_id=None, year=None, month=None, user_id=None, **kwargs):
    """Close a period. Posting into it is refused afterwards."""
    db = get_db()
    if period_id:
        period = db.execute("SELECT * FROM fiscal_periods WHERE id = ?",
                            (period_id,)).fetchone()
    elif year and month:
        period = db.execute(
            "SELECT * FROM fiscal_periods WHERE year = ? AND month = ?",
            (int(year), int(month))).fetchone()
    else:
        db.close()
        return {"error": "period_id or year+month required"}

    if not period:
        db.close()
        return {"error": "period not found"}
    if int(period["is_locked"] or 0) or (period["status"] or "").lower() == "closed":
        db.close()
        return {"error": "period already closed"}

    db.execute(
        "UPDATE fiscal_periods SET status = 'closed', is_locked = 1, "
        "closed_at = CURRENT_TIMESTAMP, locked_by = ? WHERE id = ?",
        (user_id, period["id"]))
    db.commit()

    label = period["name"] or f"{period['year']}-{int(period['month'] or 1):02d}"
    entries = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(debit_total), 0) AS total "
        "FROM journal_entries WHERE date BETWEEN ? AND ?",
        (period["date_from"] or f"{period['year']}-01-01",
         period["date_to"] or f"{period['year']}-12-31")).fetchone()
    db.close()
    return {"closed": True, "period": label, "period_id": period["id"],
            "entries_in_period": entries["n"],
            "total_debits": round(float(entries["total"] or 0), 2)}


@register("core.periods.reopen")
def periods_reopen(period_id=None, year=None, month=None, **kwargs):
    """Reopen a closed period (an audited, deliberate action)."""
    db = get_db()
    if period_id:
        period = db.execute("SELECT * FROM fiscal_periods WHERE id = ?",
                            (period_id,)).fetchone()
    elif year and month:
        period = db.execute(
            "SELECT * FROM fiscal_periods WHERE year = ? AND month = ?",
            (int(year), int(month))).fetchone()
    else:
        db.close()
        return {"error": "period_id or year+month required"}
    if not period:
        db.close()
        return {"error": "period not found"}

    db.execute(
        "UPDATE fiscal_periods SET status = 'open', is_locked = 0, "
        "closed_at = NULL, locked_by = NULL WHERE id = ?", (period["id"],))
    db.commit()
    label = period["name"] or f"{period['year']}-{int(period['month'] or 1):02d}"
    db.close()

    try:
        from core.audit_attachments import audit_record
        conn = get_db()
        audit_record("fiscal_period", period["id"], "update",
                     new_values={"status": "open", "is_locked": 0})
        conn.close()
    except Exception:
        pass
    return {"reopened": True, "period": label, "period_id": period["id"]}


@register("core.periods.check")
def periods_check(date=None, **kwargs):
    """Ask whether posting on a date is allowed."""
    db = get_db()
    problem = assert_period_open(db, date)
    period = find_period(db, date)
    db.close()
    if problem:
        return {"allowed": False, **problem}
    return {"allowed": True,
            "period": (period["name"] if period else None) or "no period defined",
            "date": _normalise(date)}
