"""PyGo ERP — Customer credit limits.

Exposure = unpaid invoices + confirmed-but-uninvoiced orders, minus open credit
notes. Without this the ERP happily sells unlimited amounts to a customer who
never pays.
"""
import os
import sys
import sqlite3

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register  # noqa: E402


def get_db():
    """Use the request-scoped connection owned by core.main when available."""
    try:
        from core.main import get_db as _shared
        return _shared()
    except Exception:
        pass
    conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _table_has(db, table, column):
    return column in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def exposure_of(db, cliente_id):
    """What the customer currently owes us, in detail.

    Counts unpaid invoices plus confirmed orders that have not been invoiced
    yet (they are a real commitment), less any open credit note.
    """
    invoices = db.execute(
        "SELECT COALESCE(SUM(total - COALESCE(amount_paid, 0)), 0) AS due "
        "FROM facturas WHERE cliente_id = ? "
        "AND (total - COALESCE(amount_paid, 0)) > 0.01", (cliente_id,)).fetchone()
    open_invoices = round(float(invoices["due"] or 0), 2)

    # Confirmed orders not yet invoiced: a promise already made
    orders = db.execute(
        "SELECT COALESCE(SUM(so.total), 0) AS pending FROM sales_orders so "
        "WHERE so.cliente_id = ? AND so.status IN ('confirmed', 'delivered') "
        "AND NOT EXISTS (SELECT 1 FROM facturas f WHERE f.sales_order_id = so.id)",
        (cliente_id,)).fetchone()
    pending_orders = round(float(orders["pending"] or 0), 2)

    credit = 0.0
    try:
        row = db.execute(
            "SELECT COALESCE(SUM(amount - COALESCE(applied_amount, 0)), 0) AS c "
            "FROM credit_notes WHERE cliente_id = ? AND status != 'cancelled'",
            (cliente_id,)).fetchone()
        credit = round(float(row["c"] or 0), 2)
    except sqlite3.OperationalError:
        credit = 0.0

    total = round(open_invoices + pending_orders - credit, 2)
    return {"open_invoices": open_invoices, "pending_orders": pending_orders,
            "open_credit_notes": credit, "exposure": total}


def check_credit(db, cliente_id, additional_amount=0):
    """Decide whether `additional_amount` may be added to the customer's debt.

    Returns {"allowed": bool, ...}. A limit of 0 means unlimited, so existing
    installs are not suddenly blocked.
    """
    customer = db.execute(
        "SELECT id, nombre, credit_limit, credit_hold FROM clientes WHERE id = ?",
        (cliente_id,)).fetchone()
    if not customer:
        return {"allowed": False, "error": "customer not found"}

    limit = float(customer["credit_limit"] or 0)
    on_hold = bool(customer["credit_hold"])
    detail = exposure_of(db, cliente_id)
    exposure = detail["exposure"]
    requested = round(float(additional_amount or 0), 2)
    projected = round(exposure + requested, 2)

    if on_hold:
        return {"allowed": False, "reason": "customer is on credit hold",
                "cliente_id": cliente_id, "nombre": customer["nombre"],
                "credit_limit": limit, "exposure": exposure,
                "requested": requested, "projected": projected, **detail}

    if limit <= 0:
        return {"allowed": True, "reason": "no credit limit set",
                "cliente_id": cliente_id, "nombre": customer["nombre"],
                "credit_limit": 0.0, "exposure": exposure,
                "requested": requested, "projected": projected,
                "available": None, **detail}

    available = round(limit - exposure, 2)
    if projected > limit + 0.01:
        return {"allowed": False,
                "reason": f"credit limit exceeded: {projected} > {limit}",
                "cliente_id": cliente_id, "nombre": customer["nombre"],
                "credit_limit": limit, "exposure": exposure,
                "requested": requested, "projected": projected,
                "available": available, "over_by": round(projected - limit, 2),
                **detail}

    return {"allowed": True, "cliente_id": cliente_id, "nombre": customer["nombre"],
            "credit_limit": limit, "exposure": exposure, "requested": requested,
            "projected": projected, "available": available, **detail}


def log_credit_event(db, cliente_id, event_type, document_type=None,
                     document_id=None, amount=0, decision=None, notes=None):
    """Record a credit decision so a block can be explained afterwards."""
    try:
        before = (decision or {}).get("exposure", 0)
        after = (decision or {}).get("projected", before)
        db.execute(
            "INSERT INTO credit_events (cliente_id, event_type, document_type, "
            "document_id, amount, exposure_before, exposure_after, credit_limit, "
            "blocked, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cliente_id, event_type, document_type, document_id, amount,
             before, after, (decision or {}).get("credit_limit", 0),
             0 if (decision or {}).get("allowed") else 1,
             notes or (decision or {}).get("reason")))
    except sqlite3.OperationalError:
        pass


# ------------------------------------------------------------------- handlers

@register("core.credit.set_limit")
def credit_set_limit(cliente_id=None, credit_limit=None, credit_hold=None, **kwargs):
    """Set the credit limit (0 = unlimited) and/or put the customer on hold."""
    if not cliente_id:
        return {"error": "cliente_id required"}
    if credit_limit is None and credit_hold is None:
        return {"error": "credit_limit or credit_hold required"}

    db = get_db()
    if not db.execute("SELECT 1 FROM clientes WHERE id = ?", (cliente_id,)).fetchone():
        return {"error": "customer not found"}

    sets, params = [], []
    if credit_limit is not None:
        try:
            limit = float(credit_limit)
        except (TypeError, ValueError):
            return {"error": "credit_limit must be numeric"}
        if limit < 0:
            return {"error": "credit_limit cannot be negative"}
        sets.append("credit_limit = ?")
        params.append(limit)
    if credit_hold is not None:
        sets.append("credit_hold = ?")
        params.append(1 if str(credit_hold) in ("1", "True", "true", "yes") else 0)

    params.append(cliente_id)
    db.execute(f"UPDATE clientes SET {', '.join(sets)} WHERE id = ?", params)
    db.commit()

    row = db.execute(
        "SELECT nombre, credit_limit, credit_hold FROM clientes WHERE id = ?",
        (cliente_id,)).fetchone()
    return {"cliente_id": cliente_id, "nombre": row["nombre"],
            "credit_limit": float(row["credit_limit"] or 0),
            "credit_hold": bool(row["credit_hold"])}


@register("core.credit.check")
def credit_check(cliente_id=None, amount=0, **kwargs):
    """Ask whether an extra amount fits within the customer's credit."""
    if not cliente_id:
        return {"error": "cliente_id required"}
    db = get_db()
    return check_credit(db, cliente_id, amount)


@register("core.credit.exposure")
def credit_exposure(cliente_id=None, **kwargs):
    """Credit position per customer, or for one customer in detail."""
    db = get_db()
    if cliente_id:
        customer = db.execute(
            "SELECT id, nombre, credit_limit, credit_hold FROM clientes WHERE id = ?",
            (cliente_id,)).fetchone()
        if not customer:
            return {"error": "customer not found"}
        detail = exposure_of(db, cliente_id)
        limit = float(customer["credit_limit"] or 0)
        return {"cliente_id": cliente_id, "nombre": customer["nombre"],
                "credit_limit": limit, "credit_hold": bool(customer["credit_hold"]),
                "available": round(limit - detail["exposure"], 2) if limit else None,
                "utilisation_pct": round(detail["exposure"] / limit * 100, 2)
                                   if limit else None, **detail}

    rows = db.execute(
        "SELECT id, nombre, credit_limit, credit_hold FROM clientes "
        "ORDER BY credit_limit DESC").fetchall()
    out, over = [], 0
    for r in rows:
        detail = exposure_of(db, r["id"])
        if detail["exposure"] <= 0 and not float(r["credit_limit"] or 0):
            continue
        limit = float(r["credit_limit"] or 0)
        exceeded = bool(limit and detail["exposure"] > limit + 0.01)
        if exceeded:
            over += 1
        out.append({"cliente_id": r["id"], "nombre": r["nombre"],
                    "credit_limit": limit, "credit_hold": bool(r["credit_hold"]),
                    "available": round(limit - detail["exposure"], 2) if limit else None,
                    "utilisation_pct": round(detail["exposure"] / limit * 100, 2)
                                       if limit else None,
                    "over_limit": exceeded, **detail})
    return {"customers": out, "count": len(out), "over_limit_count": over}


@register("core.credit.events")
def credit_events(cliente_id=None, blocked_only=0, limit=100, **kwargs):
    """Audit trail of credit decisions."""
    db = get_db()
    where, params = [], []
    if cliente_id:
        where.append("e.cliente_id = ?")
        params.append(cliente_id)
    if int(blocked_only or 0):
        where.append("e.blocked = 1")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(int(limit))
    rows = db.execute(
        f"SELECT e.*, c.nombre AS cliente_nombre FROM credit_events e "
        f"LEFT JOIN clientes c ON c.id = e.cliente_id "
        f"{clause} ORDER BY e.created_at DESC, e.id DESC LIMIT ?", params).fetchall()
    out = [dict(r) for r in rows]
    for d in out:
        d["blocked"] = bool(d["blocked"])
    return {"events": out, "count": len(out)}
