"""PyGo ERP — Lot and serial tracking.

Without this you cannot sell food, pharma, chemicals, electronics or anything
with an expiry date or a warranty per unit.

Policies (productos.tracking):
  none   — no tracking (default)
  lot    — quantities grouped in lots, consumed FEFO (first expired, first out)
  serial — one unit per serial, quantity is always 1
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


def tracking_of(db, producto_id):
    row = db.execute(
        "SELECT tracking, shelf_life_days FROM productos WHERE id = ?",
        (producto_id,)).fetchone()
    if not row:
        return "none", None
    return (row["tracking"] or "none"), row["shelf_life_days"]


def _touch_lot_stock(db, lot_id, warehouse_id, delta):
    row = db.execute(
        "SELECT id, quantity FROM lot_stock WHERE lot_id = ? AND warehouse_id = ?",
        (lot_id, warehouse_id)).fetchone()
    if row:
        db.execute("UPDATE lot_stock SET quantity = quantity + ? WHERE id = ?",
                   (delta, row["id"]))
        return float(row["quantity"]) + delta
    db.execute(
        "INSERT INTO lot_stock (lot_id, warehouse_id, quantity) VALUES (?, ?, ?)",
        (lot_id, warehouse_id, delta))
    return delta


def receive_into_lot(db, producto_id, warehouse_id, quantity, lot_code=None,
                     expiry_date=None, supplier_id=None, source_type=None,
                     source_id=None, company_id=None):
    """Put quantity into a lot, creating the lot if needed. Returns lot info."""
    tracking, shelf_life = tracking_of(db, producto_id)
    if tracking == "none":
        return None  # nothing to track

    quantity = float(quantity)
    if tracking == "serial" and abs(quantity - 1.0) > 1e-9:
        raise ValueError("serial-tracked products receive one unit per serial")

    if not lot_code:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        lot_code = f"{'SN' if tracking == 'serial' else 'LOT'}-{producto_id}-{stamp}"

    if not expiry_date and shelf_life:
        expiry_date = (datetime.now() + timedelta(days=int(shelf_life))).strftime("%Y-%m-%d")

    row = db.execute("SELECT * FROM lots WHERE producto_id = ? AND lot_code = ?",
                     (producto_id, lot_code)).fetchone()
    if row:
        if tracking == "serial":
            raise ValueError(f"serial {lot_code} already exists")
        lot_id = row["id"]
    else:
        cur = db.execute(
            "INSERT INTO lots (producto_id, lot_code, tracking_type, expiry_date, "
            "supplier_id, company_id) VALUES (?, ?, ?, ?, ?, ?)",
            (producto_id, lot_code, tracking, expiry_date, supplier_id, company_id))
        lot_id = cur.lastrowid

    _touch_lot_stock(db, lot_id, warehouse_id, quantity)
    db.execute(
        "INSERT INTO lot_movements (lot_id, warehouse_id, quantity, direction, "
        "reason, source_type, source_id) VALUES (?, ?, ?, 'in', ?, ?, ?)",
        (lot_id, warehouse_id, quantity, f"receipt {source_type or 'manual'}",
         source_type, source_id))
    return {"lot_id": lot_id, "lot_code": lot_code, "tracking": tracking,
            "expiry_date": expiry_date, "quantity": quantity}


def consume_from_lots(db, producto_id, warehouse_id, quantity, lot_id=None,
                      source_type=None, source_id=None):
    """Take quantity out of lots. FEFO unless a specific lot is given.

    Returns {"consumed": [...], "shortage": n} — never raises on shortage so
    the caller decides whether to refuse or backorder.
    """
    tracking, _ = tracking_of(db, producto_id)
    if tracking == "none":
        return {"consumed": [], "shortage": 0.0, "tracking": "none"}

    quantity = float(quantity)
    if lot_id:
        rows = db.execute(
            "SELECT ls.*, l.lot_code, l.expiry_date FROM lot_stock ls "
            "JOIN lots l ON l.id = ls.lot_id "
            "WHERE ls.lot_id = ? AND ls.warehouse_id = ? AND ls.quantity > 0",
            (lot_id, warehouse_id)).fetchall()
    else:
        # First expired, first out; lots without expiry go last
        rows = db.execute(
            "SELECT ls.*, l.lot_code, l.expiry_date FROM lot_stock ls "
            "JOIN lots l ON l.id = ls.lot_id "
            "WHERE l.producto_id = ? AND ls.warehouse_id = ? AND ls.quantity > 0 "
            "ORDER BY CASE WHEN l.expiry_date IS NULL THEN 1 ELSE 0 END, "
            "l.expiry_date ASC, l.id ASC",
            (producto_id, warehouse_id)).fetchall()

    remaining = quantity
    consumed = []
    for r in rows:
        if remaining <= 0:
            break
        take = min(float(r["quantity"]), remaining)
        _touch_lot_stock(db, r["lot_id"], warehouse_id, -take)
        db.execute(
            "INSERT INTO lot_movements (lot_id, warehouse_id, quantity, direction, "
            "reason, source_type, source_id) VALUES (?, ?, ?, 'out', ?, ?, ?)",
            (r["lot_id"], warehouse_id, take, f"issue {source_type or 'manual'}",
             source_type, source_id))
        consumed.append({"lot_id": r["lot_id"], "lot_code": r["lot_code"],
                         "expiry_date": r["expiry_date"], "quantity": take})
        remaining -= take

    return {"consumed": consumed, "shortage": round(remaining, 6),
            "tracking": tracking}


# ------------------------------------------------------------------- handlers

@register("core.lots.set_tracking")
def lots_set_tracking(producto_id=None, tracking=None, shelf_life_days=None, **kwargs):
    """Set the tracking policy of a product."""
    allowed = ("none", "lot", "serial")
    if not producto_id or not tracking:
        return {"error": "producto_id and tracking required"}
    if tracking not in allowed:
        return {"error": "unsupported tracking", "allowed": list(allowed)}

    db = get_db()
    if not db.execute("SELECT 1 FROM productos WHERE id = ?", (producto_id,)).fetchone():
        db.close()
        return {"error": "product not found"}
    if shelf_life_days is not None:
        db.execute("UPDATE productos SET tracking = ?, shelf_life_days = ? WHERE id = ?",
                   (tracking, int(shelf_life_days), producto_id))
    else:
        db.execute("UPDATE productos SET tracking = ? WHERE id = ?",
                   (tracking, producto_id))
    db.commit()
    db.close()
    return {"producto_id": producto_id, "tracking": tracking,
            "shelf_life_days": shelf_life_days}


@register("core.lots.list")
def lots_list(producto_id=None, warehouse_id=None, only_available=0, **kwargs):
    """Lots with their stock per warehouse."""
    db = get_db()
    where, params = [], []
    if producto_id:
        where.append("l.producto_id = ?")
        params.append(producto_id)
    if warehouse_id:
        where.append("ls.warehouse_id = ?")
        params.append(warehouse_id)
    if int(only_available or 0):
        where.append("COALESCE(ls.quantity, 0) > 0")
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    rows = db.execute(
        f"SELECT l.*, p.codigo AS producto_codigo, p.nombre AS producto_nombre, "
        f"ls.warehouse_id, COALESCE(ls.quantity, 0) AS quantity, "
        f"w.name AS warehouse_name FROM lots l "
        f"JOIN productos p ON p.id = l.producto_id "
        f"LEFT JOIN lot_stock ls ON ls.lot_id = l.id "
        f"LEFT JOIN warehouses w ON w.id = ls.warehouse_id "
        f"{clause} ORDER BY CASE WHEN l.expiry_date IS NULL THEN 1 ELSE 0 END, "
        f"l.expiry_date ASC, l.id DESC LIMIT 300", params).fetchall()
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    for r in rows:
        d = dict(r)
        exp = d.get("expiry_date")
        d["is_expired"] = bool(exp and exp < today)
        if exp:
            try:
                days = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                d["days_to_expiry"] = days
            except ValueError:
                d["days_to_expiry"] = None
        else:
            d["days_to_expiry"] = None
        out.append(d)
    db.close()
    return out


@register("core.lots.receive")
def lots_receive(producto_id=None, warehouse_id=None, quantity=None, lot_code=None,
                 expiry_date=None, supplier_id=None, company_id=None, **kwargs):
    """Receive quantity into a lot or register a serial."""
    if not producto_id or not warehouse_id or quantity is None:
        return {"error": "producto_id, warehouse_id and quantity required"}
    db = get_db()
    tracking, _ = tracking_of(db, producto_id)
    if tracking == "none":
        db.close()
        return {"error": "product is not lot/serial tracked — set tracking first"}
    try:
        result = receive_into_lot(db, producto_id, warehouse_id, quantity,
                                  lot_code=lot_code, expiry_date=expiry_date,
                                  supplier_id=supplier_id, source_type="manual",
                                  company_id=company_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        db.close()
        return {"error": str(exc)}
    db.close()
    return result


@register("core.lots.consume")
def lots_consume(producto_id=None, warehouse_id=None, quantity=None, lot_id=None,
                 source_type="manual", source_id=None, **kwargs):
    """Issue quantity from lots (FEFO by default)."""
    if not producto_id or not warehouse_id or quantity is None:
        return {"error": "producto_id, warehouse_id and quantity required"}
    db = get_db()
    result = consume_from_lots(db, producto_id, warehouse_id, quantity, lot_id=lot_id,
                               source_type=source_type, source_id=source_id)
    if result["tracking"] == "none":
        db.close()
        return {"error": "product is not lot/serial tracked"}
    db.commit()
    db.close()
    return result


@register("core.lots.trace")
def lots_trace(lot_id=None, lot_code=None, producto_id=None, **kwargs):
    """Full movement history of a lot — the traceability answer."""
    db = get_db()
    if lot_code and producto_id:
        lot = db.execute("SELECT * FROM lots WHERE producto_id = ? AND lot_code = ?",
                         (producto_id, lot_code)).fetchone()
    elif lot_id:
        lot = db.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()
    else:
        db.close()
        return {"error": "lot_id, or lot_code + producto_id, required"}
    if not lot:
        db.close()
        return {"error": "lot not found"}

    movements = db.execute(
        "SELECT m.*, w.name AS warehouse_name FROM lot_movements m "
        "LEFT JOIN warehouses w ON w.id = m.warehouse_id "
        "WHERE m.lot_id = ? ORDER BY m.created_at, m.id", (lot["id"],)).fetchall()
    stock = db.execute(
        "SELECT ls.*, w.name AS warehouse_name FROM lot_stock ls "
        "LEFT JOIN warehouses w ON w.id = ls.warehouse_id WHERE ls.lot_id = ?",
        (lot["id"],)).fetchall()
    received = sum(float(m["quantity"]) for m in movements if m["direction"] == "in")
    issued = sum(float(m["quantity"]) for m in movements if m["direction"] == "out")
    db.close()
    return {"lot": dict(lot), "movements": [dict(m) for m in movements],
            "stock_by_warehouse": [dict(s) for s in stock],
            "total_received": round(received, 6), "total_issued": round(issued, 6),
            "on_hand": round(received - issued, 6)}


@register("core.lots.expiring")
def lots_expiring(days=30, **kwargs):
    """Lots expiring within N days, plus anything already expired."""
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    limit = (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT l.*, p.codigo AS producto_codigo, p.nombre AS producto_nombre, "
        "COALESCE(SUM(ls.quantity), 0) AS on_hand FROM lots l "
        "JOIN productos p ON p.id = l.producto_id "
        "LEFT JOIN lot_stock ls ON ls.lot_id = l.id "
        "WHERE l.expiry_date IS NOT NULL AND l.expiry_date <= ? "
        "GROUP BY l.id HAVING on_hand > 0 ORDER BY l.expiry_date ASC",
        (limit,)).fetchall()
    expired, soon = [], []
    for r in rows:
        d = dict(r)
        if d["expiry_date"] < today:
            expired.append(d)
        else:
            soon.append(d)
    db.close()
    return {"window_days": int(days), "expired": expired, "expiring_soon": soon,
            "expired_count": len(expired), "expiring_count": len(soon)}
