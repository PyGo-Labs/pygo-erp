"""PyGo ERP — Cost centers (analytic accounting) and budgets."""
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


# --- Cost centers ---

@register("core.cost_centers.list")
def cost_centers_list(**kwargs):
    db = get_db()
    rows = db.execute(
        "SELECT c.*, p.name AS parent_name FROM cost_centers c "
        "LEFT JOIN cost_centers p ON p.id = c.parent_id "
        "WHERE c.is_active = 1 ORDER BY c.code"
    ).fetchall()
    return [dict(r) for r in rows]


@register("core.cost_centers.create")
def cost_centers_create(code=None, name=None, parent_id=None, company_id=None, **kwargs):
    if not code or not name:
        return {"error": "code and name required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO cost_centers (code, name, parent_id, company_id) VALUES (?, ?, ?, ?)",
        (code, name, parent_id, company_id),
    )
    db.commit()
    return {"id": cur.lastrowid, "code": code, "name": name}


@register("core.cost_centers.allocate")
def cost_centers_allocate(
    cost_center_id=None, amount=None, account_id=None,
    journal_entry_id=None, entry_date=None, description=None, **kwargs
):
    """Post an analytic line against a cost center."""
    if not cost_center_id or amount is None:
        return {"error": "cost_center_id and amount required"}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be numeric"}

    db = get_db()
    if not db.execute("SELECT 1 FROM cost_centers WHERE id = ?", (cost_center_id,)).fetchone():
        return {"error": "cost center not found"}

    entry_date = entry_date or datetime.utcnow().strftime("%Y-%m-%d")
    cur = db.execute(
        "INSERT INTO analytic_lines (cost_center_id, account_id, journal_entry_id, amount, entry_date, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (cost_center_id, account_id, journal_entry_id, amount, entry_date, description),
    )
    db.commit()
    return {"id": cur.lastrowid, "cost_center_id": cost_center_id, "amount": amount, "entry_date": entry_date}


@register("core.cost_centers.report")
def cost_centers_report(date_from=None, date_to=None, **kwargs):
    """Spend per cost center in a period."""
    db = get_db()
    sql = (
        "SELECT c.id, c.code, c.name, "
        "COALESCE(SUM(a.amount), 0) AS total, COUNT(a.id) AS lines "
        "FROM cost_centers c LEFT JOIN analytic_lines a ON a.cost_center_id = c.id"
    )
    params = []
    conds = []
    if date_from:
        conds.append("a.entry_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("a.entry_date <= ?")
        params.append(date_to)
    if conds:
        sql += " AND " + " AND ".join(conds)
    sql += " WHERE c.is_active = 1 GROUP BY c.id ORDER BY total DESC"

    rows = db.execute(sql, params).fetchall()
    data = [dict(r) for r in rows]
    return {
        "period": {"from": date_from, "to": date_to},
        "cost_centers": data,
        "grand_total": round(sum(d["total"] for d in data), 2),
    }


# --- Budgets ---

@register("core.budgets.list")
def budgets_list(**kwargs):
    db = get_db()
    budgets = db.execute("SELECT * FROM budgets ORDER BY id DESC").fetchall()
    out = []
    for b in budgets:
        lines = db.execute(
            "SELECT bl.*, a.code AS account_code, a.name AS account_name, "
            "c.name AS cost_center_name FROM budget_lines bl "
            "LEFT JOIN accounts a ON a.id = bl.account_id "
            "LEFT JOIN cost_centers c ON c.id = bl.cost_center_id "
            "WHERE bl.budget_id = ?",
            (b["id"],),
        ).fetchall()
        d = dict(b)
        d["lines"] = [dict(l) for l in lines]
        d["total_planned"] = round(sum(float(l["planned_amount"] or 0) for l in lines), 2)
        out.append(d)
    return out


@register("core.budgets.create")
def budgets_create(
    name=None, fiscal_year=None, date_from=None, date_to=None,
    lines=None, company_id=None, **kwargs
):
    """Create a budget. lines = [{"account_id":1,"cost_center_id":2,"planned_amount":50000}]"""
    if not name:
        return {"error": "name required"}
    lines = _parse(lines) or []

    db = get_db()
    cur = db.execute(
        "INSERT INTO budgets (name, fiscal_year, date_from, date_to, company_id) VALUES (?, ?, ?, ?, ?)",
        (name, fiscal_year, date_from, date_to, company_id),
    )
    budget_id = cur.lastrowid
    for l in lines:
        db.execute(
            "INSERT INTO budget_lines (budget_id, account_id, cost_center_id, planned_amount) "
            "VALUES (?, ?, ?, ?)",
            (budget_id, l.get("account_id"), l.get("cost_center_id"), float(l.get("planned_amount", 0))),
        )
    db.commit()
    return {"id": budget_id, "name": name, "lines": len(lines)}


@register("core.budgets.vs_actual")
def budgets_vs_actual(budget_id=None, **kwargs):
    """Compare budget vs actual spend per line."""
    if not budget_id:
        return {"error": "budget_id required"}
    db = get_db()
    budget = db.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
    if not budget:
        return {"error": "budget not found"}

    lines = db.execute(
        "SELECT bl.*, a.code AS account_code, a.name AS account_name, "
        "c.name AS cost_center_name FROM budget_lines bl "
        "LEFT JOIN accounts a ON a.id = bl.account_id "
        "LEFT JOIN cost_centers c ON c.id = bl.cost_center_id "
        "WHERE bl.budget_id = ?",
        (budget_id,),
    ).fetchall()

    out = []
    total_planned = 0.0
    total_actual = 0.0
    for l in lines:
        planned = float(l["planned_amount"] or 0)

        # actual from journal lines on that account
        actual = 0.0
        if l["account_id"]:
            sql = (
                "SELECT COALESCE(SUM(jel.debit) - SUM(jel.credit), 0) FROM journal_entry_lines jel "
                "JOIN journal_entries je ON je.id = jel.entry_id WHERE jel.account_id = ?"
            )
            params = [l["account_id"]]
            if budget["date_from"]:
                sql += " AND je.entry_date >= ?"
                params.append(budget["date_from"])
            if budget["date_to"]:
                sql += " AND je.entry_date <= ?"
                params.append(budget["date_to"])
            try:
                actual = float(db.execute(sql, params).fetchone()[0] or 0)
            except Exception:
                actual = 0.0

        # add analytic lines if a cost center is set
        if l["cost_center_id"]:
            sql2 = "SELECT COALESCE(SUM(amount), 0) FROM analytic_lines WHERE cost_center_id = ?"
            params2 = [l["cost_center_id"]]
            if budget["date_from"]:
                sql2 += " AND entry_date >= ?"
                params2.append(budget["date_from"])
            if budget["date_to"]:
                sql2 += " AND entry_date <= ?"
                params2.append(budget["date_to"])
            try:
                actual += float(db.execute(sql2, params2).fetchone()[0] or 0)
            except Exception:
                pass

        variance = planned - actual
        pct = (actual / planned * 100) if planned else 0
        out.append({
            "account_code": l["account_code"],
            "account_name": l["account_name"],
            "cost_center": l["cost_center_name"],
            "planned": round(planned, 2),
            "actual": round(actual, 2),
            "variance": round(variance, 2),
            "consumed_pct": round(pct, 1),
            "over_budget": actual > planned,
        })
        total_planned += planned
        total_actual += actual

    return {
        "budget": budget["name"],
        "fiscal_year": budget["fiscal_year"],
        "period": {"from": budget["date_from"], "to": budget["date_to"]},
        "lines": out,
        "totals": {
            "planned": round(total_planned, 2),
            "actual": round(total_actual, 2),
            "variance": round(total_planned - total_actual, 2),
            "consumed_pct": round(total_actual / total_planned * 100, 1) if total_planned else 0,
        },
    }


@register("core.cost_centers.seed")
def cost_centers_seed(**kwargs):
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM cost_centers").fetchone()[0] > 0:
        return {"seeded": False, "reason": "already seeded"}
    presets = [
        ("ADM", "Administration"),
        ("SAL", "Sales & Marketing"),
        ("OPS", "Operations"),
        ("PRD", "Production"),
        ("RND", "Research & Development"),
        ("IT", "Information Technology"),
    ]
    for code, name in presets:
        db.execute("INSERT INTO cost_centers (code, name) VALUES (?, ?)", (code, name))
    db.commit()
    return {"seeded": True, "cost_centers": len(presets)}
