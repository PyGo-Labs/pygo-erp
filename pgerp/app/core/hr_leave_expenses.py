"""PyGo ERP — HR leave management and expense reports."""
import os
import sys
import json
from datetime import datetime, timedelta

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


def _business_days(d1, d2):
    """Count weekdays inclusive between two ISO dates."""
    try:
        a = datetime.strptime(str(d1)[:10], "%Y-%m-%d")
        b = datetime.strptime(str(d2)[:10], "%Y-%m-%d")
    except Exception:
        return 0
    if b < a:
        return 0
    days = 0
    cur = a
    while cur <= b:
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return days


def _next_folio(doc_type):
    try:
        from core.commercial_terms import sequences_next
        return sequences_next(doc_type=doc_type).get("folio")
    except Exception:
        return None


# --- Leave types ---

@register("core.hr.leave_types.list")
def leave_types_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM leave_types ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@register("core.hr.leave_types.create")
def leave_types_create(name=None, code=None, days_per_year=0, is_paid=1, requires_approval=1, **kwargs):
    if not name:
        return {"error": "name required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO leave_types (name, code, days_per_year, is_paid, requires_approval) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, code, float(days_per_year or 0), int(is_paid), int(requires_approval)),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "days_per_year": days_per_year}


@register("core.hr.leave_types.seed")
def leave_types_seed(**kwargs):
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM leave_types").fetchone()[0] > 0:
        return {"seeded": False, "reason": "already seeded"}
    presets = [
        ("Annual Leave", "ANNUAL", 20, 1, 1),
        ("Sick Leave", "SICK", 10, 1, 0),
        ("Unpaid Leave", "UNPAID", 0, 0, 1),
        ("Parental Leave", "PARENTAL", 90, 1, 1),
        ("Bereavement", "BEREAVE", 3, 1, 0),
        ("Training", "TRAINING", 5, 1, 1),
    ]
    for name, code, days, paid, appr in presets:
        db.execute(
            "INSERT INTO leave_types (name, code, days_per_year, is_paid, requires_approval) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, code, days, paid, appr),
        )
    db.commit()
    return {"seeded": True, "leave_types": len(presets)}


# --- Leave requests ---

@register("core.hr.leave.list")
def leave_list(employee_id=None, status=None, **kwargs):
    db = get_db()
    sql = (
        "SELECT r.*, e.first_name || ' ' || e.last_name AS employee_name, "
        "t.name AS leave_type_name, t.is_paid FROM leave_requests r "
        "LEFT JOIN employees e ON e.id = r.employee_id "
        "LEFT JOIN leave_types t ON t.id = r.leave_type_id WHERE 1=1"
    )
    params = []
    if employee_id:
        sql += " AND r.employee_id = ?"
        params.append(employee_id)
    if status:
        sql += " AND r.status = ?"
        params.append(status)
    sql += " ORDER BY r.date_from DESC"
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@register("core.hr.leave.request")
def leave_request(employee_id=None, leave_type_id=None, date_from=None, date_to=None, reason=None, **kwargs):
    if not employee_id or not leave_type_id or not date_from or not date_to:
        return {"error": "employee_id, leave_type_id, date_from and date_to required"}

    db = get_db()
    emp = db.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    if not emp:
        return {"error": "employee not found"}
    if emp["status"] != "active":
        return {"error": "employee is not active"}
    lt = db.execute("SELECT * FROM leave_types WHERE id = ?", (leave_type_id,)).fetchone()
    if not lt:
        return {"error": "leave type not found"}

    days = _business_days(date_from, date_to)
    if days <= 0:
        return {"error": "invalid date range"}

    # overlap check against approved/pending requests
    overlap = db.execute(
        "SELECT id, date_from, date_to FROM leave_requests WHERE employee_id = ? "
        "AND status IN ('pending','approved') AND NOT (date_to < ? OR date_from > ?)",
        (employee_id, date_from, date_to),
    ).fetchone()
    if overlap:
        return {"error": f"overlaps existing request {overlap['id']} ({overlap['date_from']}..{overlap['date_to']})"}

    # balance check when the type has an annual allowance
    if float(lt["days_per_year"] or 0) > 0:
        year = str(date_from)[:4]
        alloc = db.execute(
            "SELECT COALESCE(SUM(days_allocated),0) FROM leave_allocations "
            "WHERE employee_id = ? AND leave_type_id = ? AND year = ?",
            (employee_id, leave_type_id, year),
        ).fetchone()[0]
        allowance = float(alloc or 0) or float(lt["days_per_year"])
        taken = db.execute(
            "SELECT COALESCE(SUM(days),0) FROM leave_requests WHERE employee_id = ? "
            "AND leave_type_id = ? AND status = 'approved' AND date_from LIKE ?",
            (employee_id, leave_type_id, f"{year}%"),
        ).fetchone()[0]
        if float(taken or 0) + days > allowance:
            return {
                "error": "insufficient leave balance",
                "allowance": allowance,
                "already_taken": float(taken or 0),
                "requested": days,
                "remaining": round(allowance - float(taken or 0), 2),
            }

    status = "pending" if int(lt["requires_approval"] or 0) else "approved"
    cur = db.execute(
        "INSERT INTO leave_requests (employee_id, leave_type_id, date_from, date_to, days, reason, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (employee_id, leave_type_id, date_from, date_to, days, reason, status),
    )
    db.commit()
    return {
        "id": cur.lastrowid,
        "employee_id": employee_id,
        "leave_type": lt["name"],
        "days": days,
        "status": status,
    }


@register("core.hr.leave.approve")
def leave_approve(request_id=None, approved_by=None, **kwargs):
    if not request_id:
        return {"error": "request_id required"}
    db = get_db()
    r = db.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
    if not r:
        return {"error": "request not found"}
    if r["status"] != "pending":
        return {"error": f"request is {r['status']}, expected pending"}
    db.execute(
        "UPDATE leave_requests SET status = 'approved', approved_by = ?, approved_at = ? WHERE id = ?",
        (approved_by, datetime.utcnow().isoformat(), request_id),
    )
    db.commit()
    return {"id": request_id, "status": "approved", "days": r["days"]}


@register("core.hr.leave.reject")
def leave_reject(request_id=None, approved_by=None, **kwargs):
    if not request_id:
        return {"error": "request_id required"}
    db = get_db()
    r = db.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
    if not r:
        return {"error": "request not found"}
    if r["status"] != "pending":
        return {"error": f"request is {r['status']}, expected pending"}
    db.execute(
        "UPDATE leave_requests SET status = 'rejected', approved_by = ?, approved_at = ? WHERE id = ?",
        (approved_by, datetime.utcnow().isoformat(), request_id),
    )
    db.commit()
    return {"id": request_id, "status": "rejected"}


@register("core.hr.leave.balance")
def leave_balance(employee_id=None, year=None, **kwargs):
    if not employee_id:
        return {"error": "employee_id required"}
    db = get_db()
    year = year or datetime.utcnow().strftime("%Y")
    types = db.execute("SELECT * FROM leave_types ORDER BY name").fetchall()

    out = []
    for t in types:
        alloc = db.execute(
            "SELECT COALESCE(SUM(days_allocated),0) FROM leave_allocations "
            "WHERE employee_id = ? AND leave_type_id = ? AND year = ?",
            (employee_id, t["id"], year),
        ).fetchone()[0]
        allowance = float(alloc or 0) or float(t["days_per_year"] or 0)
        taken = db.execute(
            "SELECT COALESCE(SUM(days),0) FROM leave_requests WHERE employee_id = ? "
            "AND leave_type_id = ? AND status = 'approved' AND date_from LIKE ?",
            (employee_id, t["id"], f"{year}%"),
        ).fetchone()[0]
        pending = db.execute(
            "SELECT COALESCE(SUM(days),0) FROM leave_requests WHERE employee_id = ? "
            "AND leave_type_id = ? AND status = 'pending' AND date_from LIKE ?",
            (employee_id, t["id"], f"{year}%"),
        ).fetchone()[0]
        out.append({
            "leave_type": t["name"],
            "code": t["code"],
            "allowance": allowance,
            "taken": float(taken or 0),
            "pending": float(pending or 0),
            "remaining": round(allowance - float(taken or 0), 2),
        })
    return {"employee_id": employee_id, "year": year, "balances": out}


# --- Expense reports ---

@register("core.hr.expenses.list")
def expenses_list(employee_id=None, status=None, **kwargs):
    db = get_db()
    sql = (
        "SELECT r.*, e.first_name || ' ' || e.last_name AS employee_name "
        "FROM expense_reports r LEFT JOIN employees e ON e.id = r.employee_id WHERE 1=1"
    )
    params = []
    if employee_id:
        sql += " AND r.employee_id = ?"
        params.append(employee_id)
    if status:
        sql += " AND r.status = ?"
        params.append(status)
    sql += " ORDER BY r.id DESC"
    rows = db.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        lines = db.execute("SELECT * FROM expense_lines WHERE report_id = ?", (r["id"],)).fetchall()
        d["lines"] = [dict(l) for l in lines]
        out.append(d)
    return out


@register("core.hr.expenses.create")
def expenses_create(employee_id=None, title=None, lines=None, currency="USD", company_id=None, **kwargs):
    """Create an expense report. lines = [{"expense_date":"2026-08-01","category":"travel","amount":250}]"""
    if not employee_id:
        return {"error": "employee_id required"}
    lines = _parse(lines)
    if not lines:
        return {"error": "lines required"}

    db = get_db()
    if not db.execute("SELECT 1 FROM employees WHERE id = ?", (employee_id,)).fetchone():
        return {"error": "employee not found"}

    total = sum(float(l.get("amount", 0)) + float(l.get("tax_amount", 0) or 0) for l in lines)
    folio = _next_folio("expense")
    try:
        cur = db.execute(
            "INSERT INTO expense_reports (folio, employee_id, title, total, currency, company_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (folio, employee_id, title, total, currency, company_id),
        )
        report_id = cur.lastrowid
        for l in lines:
            db.execute(
                "INSERT INTO expense_lines (report_id, expense_date, category, description, amount, "
                "tax_amount, cost_center_id, account_id, receipt_file_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (report_id, l.get("expense_date"), l.get("category"), l.get("description"),
                 float(l.get("amount", 0)), float(l.get("tax_amount", 0) or 0),
                 l.get("cost_center_id"), l.get("account_id"), l.get("receipt_file_id")),
            )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"expense report failed: {e}"}
    finally:
        db.close()

    return {"id": report_id, "folio": folio, "total": round(total, 2), "lines": len(lines), "status": "draft"}


@register("core.hr.expenses.submit")
def expenses_submit(report_id=None, **kwargs):
    if not report_id:
        return {"error": "report_id required"}
    db = get_db()
    r = db.execute("SELECT * FROM expense_reports WHERE id = ?", (report_id,)).fetchone()
    if not r:
        return {"error": "report not found"}
    if r["status"] != "draft":
        return {"error": f"report is {r['status']}, expected draft"}
    db.execute(
        "UPDATE expense_reports SET status = 'submitted', submitted_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), report_id),
    )
    db.commit()
    return {"id": report_id, "status": "submitted", "total": r["total"]}


@register("core.hr.expenses.approve")
def expenses_approve(report_id=None, approved_by=None, **kwargs):
    if not report_id:
        return {"error": "report_id required"}
    db = get_db()
    r = db.execute("SELECT * FROM expense_reports WHERE id = ?", (report_id,)).fetchone()
    if not r:
        return {"error": "report not found"}
    if r["status"] != "submitted":
        return {"error": f"report is {r['status']}, expected submitted"}

    try:
        db.execute(
            "UPDATE expense_reports SET status = 'approved', approved_by = ?, approved_at = ? WHERE id = ?",
            (approved_by, datetime.utcnow().isoformat(), report_id),
        )
        # push analytic lines to cost centers
        for l in db.execute("SELECT * FROM expense_lines WHERE report_id = ?", (report_id,)).fetchall():
            if l["cost_center_id"]:
                db.execute(
                    "INSERT INTO analytic_lines (cost_center_id, account_id, amount, entry_date, description) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (l["cost_center_id"], l["account_id"],
                     float(l["amount"] or 0) + float(l["tax_amount"] or 0),
                     l["expense_date"], f"Expense {r['folio'] or report_id}: {l['description'] or ''}"),
                )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"approval failed: {e}"}
    finally:
        db.close()

    return {"id": report_id, "status": "approved", "total": r["total"]}


@register("core.hr.expenses.reimburse")
def expenses_reimburse(report_id=None, bank_account_id=None, payment_date=None, **kwargs):
    """Reimburse an approved expense report by registering an outbound payment."""
    if not report_id:
        return {"error": "report_id required"}
    db = get_db()
    r = db.execute("SELECT * FROM expense_reports WHERE id = ?", (report_id,)).fetchone()
    if not r:
        return {"error": "report not found"}
    if r["status"] != "approved":
        return {"error": f"report is {r['status']}, expected approved"}

    try:
        from core.accounting_treasury import payments_register
        pay = payments_register(
            amount=float(r["total"] or 0),
            partner_type="employee",
            partner_id=r["employee_id"],
            payment_type="outbound",
            payment_date=payment_date,
            bank_account_id=bank_account_id,
            reference=f"Expense reimbursement {r['folio'] or report_id}",
            allocations=[{"document_type": "expense_report", "document_id": report_id,
                          "amount": float(r["total"] or 0)}],
        )
    except Exception as e:
        return {"error": f"payment failed: {e}"}

    if isinstance(pay, dict) and pay.get("error"):
        return pay

    db.execute(
        "UPDATE expense_reports SET status = 'paid', paid_at = ?, payment_id = ? WHERE id = ?",
        (payment_date or datetime.utcnow().strftime("%Y-%m-%d"), pay.get("payment_id"), report_id),
    )
    db.commit()
    return {
        "id": report_id,
        "status": "paid",
        "total": r["total"],
        "payment_id": pay.get("payment_id"),
        "payment_folio": pay.get("folio"),
    }
