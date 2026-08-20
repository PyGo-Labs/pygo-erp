"""PyGo ERP — Reservations, backorders and reorder rules.

Reservations stop two salespeople from selling the same unit. Backorders keep
what could not be delivered. Reorder rules turn stock levels into purchase
suggestions instead of a number nobody looks at.
"""
import os
import sys
import sqlite3
from datetime import datetime, timedelta

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register  # noqa: E402

DB_PATH = os.environ.get("PYGO_DB", "/tmp/pgerp.db")


def get_db():
    """Use the request-scoped connection owned by core.main when available."""
    try:
        from core.main import get_db as _shared
        return _shared()
    except Exception:
        pass
    import sqlite3
    conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def on_hand(db, producto_id, warehouse_id=None):
    if warehouse_id:
        row = db.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS q FROM stock "
            "WHERE producto_id = ? AND warehouse_id = ?",
            (producto_id, warehouse_id)).fetchone()
    else:
        row = db.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS q FROM stock WHERE producto_id = ?",
            (producto_id,)).fetchone()
    return float(row["q"] or 0)


def reserved_quantity(db, producto_id, warehouse_id=None):
    if warehouse_id:
        row = db.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS q FROM stock_reservations "
            "WHERE producto_id = ? AND warehouse_id = ? AND status = 'active'",
            (producto_id, warehouse_id)).fetchone()
    else:
        row = db.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS q FROM stock_reservations "
            "WHERE producto_id = ? AND status = 'active'", (producto_id,)).fetchone()
    return float(row["q"] or 0)


def available_quantity(db, producto_id, warehouse_id=None):
    """On hand minus what is already promised to other documents."""
    return round(on_hand(db, producto_id, warehouse_id)
                 - reserved_quantity(db, producto_id, warehouse_id), 6)


# --------------------------------------------------------------- reservations

@register("core.stock.availability")
def stock_availability(producto_id=None, warehouse_id=None, **kwargs):
    """On hand, reserved and truly available."""
    if not producto_id:
        return {"error": "producto_id required"}
    db = get_db()
    oh = on_hand(db, producto_id, warehouse_id)
    res = reserved_quantity(db, producto_id, warehouse_id)
    prod = db.execute("SELECT codigo, nombre FROM productos WHERE id = ?",
                      (producto_id,)).fetchone()
    db.close()
    if not prod:
        return {"error": "product not found"}
    return {"producto_id": producto_id, "codigo": prod["codigo"],
            "nombre": prod["nombre"], "warehouse_id": warehouse_id,
            "on_hand": round(oh, 6), "reserved": round(res, 6),
            "available": round(oh - res, 6)}


@register("core.reservations.list")
def reservations_list(producto_id=None, document_type=None, document_id=None,
                      status="active", **kwargs):
    db = get_db()
    where, params = [], []
    if producto_id:
        where.append("r.producto_id = ?")
        params.append(producto_id)
    if document_type:
        where.append("r.document_type = ?")
        params.append(document_type)
    if document_id:
        where.append("r.document_id = ?")
        params.append(document_id)
    if status:
        where.append("r.status = ?")
        params.append(status)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    rows = db.execute(
        f"SELECT r.*, p.codigo AS producto_codigo, p.nombre AS producto_nombre, "
        f"w.name AS warehouse_name FROM stock_reservations r "
        f"JOIN productos p ON p.id = r.producto_id "
        f"LEFT JOIN warehouses w ON w.id = r.warehouse_id "
        f"{clause} ORDER BY r.reserved_at DESC LIMIT 200", params).fetchall()
    db.close()
    return [dict(r) for r in rows]


@register("core.reservations.reserve")
def reservations_reserve(producto_id=None, warehouse_id=None, quantity=None,
                         document_type=None, document_id=None, lot_id=None,
                         company_id=None, **kwargs):
    """Reserve stock for a document. Refuses to over-promise."""
    if not all([producto_id, warehouse_id, quantity, document_type, document_id]):
        return {"error": "producto_id, warehouse_id, quantity, document_type "
                         "and document_id required"}
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return {"error": "quantity must be numeric"}
    if qty <= 0:
        return {"error": "quantity must be > 0"}

    db = get_db()
    available = available_quantity(db, producto_id, warehouse_id)
    if qty > available:
        oh = on_hand(db, producto_id, warehouse_id)
        res = reserved_quantity(db, producto_id, warehouse_id)
        db.close()
        return {"error": "insufficient available stock",
                "requested": qty, "on_hand": round(oh, 6),
                "already_reserved": round(res, 6), "available": available}

    cur = db.execute(
        "INSERT INTO stock_reservations (producto_id, warehouse_id, quantity, "
        "document_type, document_id, lot_id, company_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (producto_id, warehouse_id, qty, document_type, document_id, lot_id, company_id))
    db.commit()
    rid = cur.lastrowid
    remaining = available_quantity(db, producto_id, warehouse_id)
    db.close()
    return {"reservation_id": rid, "producto_id": producto_id, "quantity": qty,
            "document_type": document_type, "document_id": document_id,
            "available_after": remaining}


@register("core.reservations.release")
def reservations_release(reservation_id=None, document_type=None, document_id=None,
                         **kwargs):
    """Release a reservation (cancelled order) so the stock is sellable again."""
    db = get_db()
    if reservation_id:
        rows = db.execute(
            "SELECT * FROM stock_reservations WHERE id = ? AND status = 'active'",
            (reservation_id,)).fetchall()
    elif document_type and document_id:
        rows = db.execute(
            "SELECT * FROM stock_reservations WHERE document_type = ? "
            "AND document_id = ? AND status = 'active'",
            (document_type, document_id)).fetchall()
    else:
        db.close()
        return {"error": "reservation_id, or document_type + document_id, required"}

    if not rows:
        db.close()
        return {"error": "no active reservation found"}

    ids = [r["id"] for r in rows]
    db.execute(
        f"UPDATE stock_reservations SET status = 'released', "
        f"released_at = CURRENT_TIMESTAMP WHERE id IN ({','.join('?' * len(ids))})", ids)
    db.commit()
    db.close()
    return {"released": len(ids), "reservation_ids": ids,
            "quantity_released": round(sum(float(r["quantity"]) for r in rows), 6)}


@register("core.reservations.fulfill")
def reservations_fulfill(document_type=None, document_id=None, **kwargs):
    """Mark reservations as fulfilled once the goods actually shipped."""
    if not document_type or not document_id:
        return {"error": "document_type and document_id required"}
    db = get_db()
    rows = db.execute(
        "SELECT * FROM stock_reservations WHERE document_type = ? AND document_id = ? "
        "AND status = 'active'", (document_type, document_id)).fetchall()
    if not rows:
        db.close()
        return {"error": "no active reservation for that document"}
    ids = [r["id"] for r in rows]
    db.execute(
        f"UPDATE stock_reservations SET status = 'fulfilled', "
        f"released_at = CURRENT_TIMESTAMP WHERE id IN ({','.join('?' * len(ids))})", ids)
    db.commit()
    db.close()
    return {"fulfilled": len(ids),
            "quantity": round(sum(float(r["quantity"]) for r in rows), 6)}


# ----------------------------------------------------------------- backorders

@register("core.backorders.list")
def backorders_list(status="pending", producto_id=None, **kwargs):
    db = get_db()
    where, params = [], []
    if status:
        where.append("b.status = ?")
        params.append(status)
    if producto_id:
        where.append("b.producto_id = ?")
        params.append(producto_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(
        f"SELECT b.*, p.codigo AS producto_codigo, p.nombre AS producto_nombre "
        f"FROM backorders b JOIN productos p ON p.id = b.producto_id "
        f"{clause} ORDER BY b.created_at ASC LIMIT 200", params).fetchall()
    db.close()
    return [dict(r) for r in rows]


@register("core.backorders.create")
def backorders_create(document_type=None, document_id=None, producto_id=None,
                      warehouse_id=None, quantity_ordered=None, quantity_pending=None,
                      expected_date=None, company_id=None, **kwargs):
    """Record what could not be delivered."""
    if not all([document_type, document_id, producto_id]) or quantity_pending is None:
        return {"error": "document_type, document_id, producto_id and "
                         "quantity_pending required"}
    try:
        pending = float(quantity_pending)
        ordered = float(quantity_ordered if quantity_ordered is not None else pending)
    except (TypeError, ValueError):
        return {"error": "quantities must be numeric"}
    if pending <= 0:
        return {"error": "quantity_pending must be > 0"}

    db = get_db()
    cur = db.execute(
        "INSERT INTO backorders (document_type, document_id, producto_id, "
        "warehouse_id, quantity_ordered, quantity_pending, expected_date, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (document_type, document_id, producto_id, warehouse_id, ordered, pending,
         expected_date, company_id))
    db.commit()
    bid = cur.lastrowid
    db.close()
    return {"backorder_id": bid, "producto_id": producto_id,
            "quantity_ordered": ordered, "quantity_pending": pending,
            "status": "pending"}


@register("core.backorders.fulfill")
def backorders_fulfill(backorder_id=None, quantity=None, **kwargs):
    """Deliver against a backorder, fully or partially."""
    if not backorder_id or quantity is None:
        return {"error": "backorder_id and quantity required"}
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return {"error": "quantity must be numeric"}
    if qty <= 0:
        return {"error": "quantity must be > 0"}

    db = get_db()
    bo = db.execute("SELECT * FROM backorders WHERE id = ?", (backorder_id,)).fetchone()
    if not bo:
        db.close()
        return {"error": "backorder not found"}
    if bo["status"] in ("fulfilled", "cancelled"):
        db.close()
        return {"error": f"backorder is already {bo['status']}"}

    pending = float(bo["quantity_pending"])
    if qty > pending + 1e-9:
        db.close()
        return {"error": f"cannot fulfill {qty}, only {pending} pending"}

    left = round(pending - qty, 6)
    status = "fulfilled" if left <= 0 else "partial"
    db.execute(
        "UPDATE backorders SET quantity_pending = ?, status = ?, "
        "fulfilled_at = CASE WHEN ? = 'fulfilled' THEN CURRENT_TIMESTAMP ELSE NULL END "
        "WHERE id = ?", (left, status, status, backorder_id))
    db.commit()
    db.close()
    return {"backorder_id": backorder_id, "delivered": qty,
            "quantity_pending": left, "status": status}


@register("core.backorders.cancel")
def backorders_cancel(backorder_id=None, **kwargs):
    if not backorder_id:
        return {"error": "backorder_id required"}
    db = get_db()
    bo = db.execute("SELECT * FROM backorders WHERE id = ?", (backorder_id,)).fetchone()
    if not bo:
        db.close()
        return {"error": "backorder not found"}
    db.execute("UPDATE backorders SET status = 'cancelled' WHERE id = ?",
               (backorder_id,))
    db.commit()
    db.close()
    return {"cancelled": True, "backorder_id": backorder_id}


# -------------------------------------------------------------- reorder rules

@register("core.reorder.rules")
def reorder_rules_list(producto_id=None, warehouse_id=None, **kwargs):
    db = get_db()
    where, params = ["r.is_active = 1"], []
    if producto_id:
        where.append("r.producto_id = ?")
        params.append(producto_id)
    if warehouse_id:
        where.append("r.warehouse_id = ?")
        params.append(warehouse_id)
    rows = db.execute(
        f"SELECT r.*, p.codigo AS producto_codigo, p.nombre AS producto_nombre, "
        f"w.name AS warehouse_name FROM reorder_rules r "
        f"JOIN productos p ON p.id = r.producto_id "
        f"JOIN warehouses w ON w.id = r.warehouse_id "
        f"WHERE {' AND '.join(where)} ORDER BY p.codigo", params).fetchall()
    db.close()
    return [dict(r) for r in rows]


@register("core.reorder.rules.create")
def reorder_rules_create(producto_id=None, warehouse_id=None, min_quantity=None,
                         max_quantity=None, multiple_of=1, lead_time_days=0,
                         preferred_supplier_id=None, **kwargs):
    """Define min/max for a product in a warehouse."""
    if not producto_id or not warehouse_id or min_quantity is None:
        return {"error": "producto_id, warehouse_id and min_quantity required"}
    try:
        minimum = float(min_quantity)
        maximum = float(max_quantity if max_quantity is not None else min_quantity)
    except (TypeError, ValueError):
        return {"error": "quantities must be numeric"}
    if maximum < minimum:
        return {"error": "max_quantity cannot be lower than min_quantity"}

    db = get_db()
    existing = db.execute(
        "SELECT id FROM reorder_rules WHERE producto_id = ? AND warehouse_id = ?",
        (producto_id, warehouse_id)).fetchone()
    if existing:
        db.execute(
            "UPDATE reorder_rules SET min_quantity = ?, max_quantity = ?, "
            "multiple_of = ?, lead_time_days = ?, preferred_supplier_id = ?, "
            "is_active = 1 WHERE id = ?",
            (minimum, maximum, float(multiple_of or 1), int(lead_time_days or 0),
             preferred_supplier_id, existing["id"]))
        rid = existing["id"]
        action = "updated"
    else:
        cur = db.execute(
            "INSERT INTO reorder_rules (producto_id, warehouse_id, min_quantity, "
            "max_quantity, multiple_of, lead_time_days, preferred_supplier_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (producto_id, warehouse_id, minimum, maximum, float(multiple_of or 1),
             int(lead_time_days or 0), preferred_supplier_id))
        rid = cur.lastrowid
        action = "created"
    db.commit()
    db.close()
    return {"rule_id": rid, "action": action, "producto_id": producto_id,
            "warehouse_id": warehouse_id, "min_quantity": minimum,
            "max_quantity": maximum}


@register("core.reorder.suggestions")
def reorder_suggestions(warehouse_id=None, **kwargs):
    """Products below their minimum, with how much to buy to reach the maximum.

    Availability nets out active reservations, so promised stock does not hide
    a shortage.
    """
    db = get_db()
    where, params = ["r.is_active = 1"], []
    if warehouse_id:
        where.append("r.warehouse_id = ?")
        params.append(warehouse_id)
    rules = db.execute(
        f"SELECT r.*, p.codigo, p.nombre, w.name AS warehouse_name, "
        f"s.name AS supplier_name FROM reorder_rules r "
        f"JOIN productos p ON p.id = r.producto_id "
        f"JOIN warehouses w ON w.id = r.warehouse_id "
        f"LEFT JOIN suppliers s ON s.id = r.preferred_supplier_id "
        f"WHERE {' AND '.join(where)}", params).fetchall()

    suggestions = []
    for rule in rules:
        oh = on_hand(db, rule["producto_id"], rule["warehouse_id"])
        res = reserved_quantity(db, rule["producto_id"], rule["warehouse_id"])
        available = round(oh - res, 6)
        minimum = float(rule["min_quantity"] or 0)
        if available >= minimum:
            continue

        maximum = float(rule["max_quantity"] or minimum)
        needed = maximum - available
        multiple = float(rule["multiple_of"] or 1)
        if multiple > 1:
            import math
            needed = math.ceil(needed / multiple) * multiple

        expected = None
        if rule["lead_time_days"]:
            expected = (datetime.now() + timedelta(days=int(rule["lead_time_days"]))
                        ).strftime("%Y-%m-%d")

        suggestions.append({
            "producto_id": rule["producto_id"], "codigo": rule["codigo"],
            "nombre": rule["nombre"], "warehouse_id": rule["warehouse_id"],
            "warehouse_name": rule["warehouse_name"],
            "on_hand": round(oh, 6), "reserved": round(res, 6), "available": available,
            "min_quantity": minimum, "max_quantity": maximum,
            "suggested_quantity": round(needed, 6),
            "preferred_supplier_id": rule["preferred_supplier_id"],
            "supplier_name": rule["supplier_name"],
            "lead_time_days": rule["lead_time_days"],
            "expected_date": expected,
        })
    db.close()
    suggestions.sort(key=lambda s: s["available"] - s["min_quantity"])
    return {"count": len(suggestions), "suggestions": suggestions}


@register("core.reorder.create_rfq")
def reorder_create_rfq(warehouse_id=None, **kwargs):
    """Turn the current suggestions into a single RFQ."""
    data = reorder_suggestions(warehouse_id=warehouse_id)
    if not data["suggestions"]:
        return {"created": False, "reason": "nothing below its minimum"}

    lines = [{"producto_id": s["producto_id"], "qty": s["suggested_quantity"]}
             for s in data["suggestions"]]
    try:
        from core.purchasing_rfq import rfq_create
    except ImportError:
        return {"error": "purchasing module not available"}

    result = rfq_create(lines=lines, notes="Generated from reorder rules")
    if "error" in result:
        return result
    return {"created": True, "rfq_id": result["id"], "folio": result.get("folio"),
            "lines": len(lines),
            "products": [s["codigo"] for s in data["suggestions"]]}
