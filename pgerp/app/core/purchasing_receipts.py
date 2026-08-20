"""PyGo ERP — Partial receipts and purchase returns."""
import os
import sys
import json
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


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


def _parse_lines(lines):
    if isinstance(lines, str):
        try:
            return json.loads(lines)
        except Exception:
            return None
    return lines


def _next_folio(doc_type):
    try:
        from core.commercial_terms import sequences_next
        return sequences_next(doc_type=doc_type).get("folio")
    except Exception:
        return None


def _add_stock(db, producto_id, warehouse_id, qty, reason, movement_type="purchase"):
    """Increment (or decrement) stock and log the movement.

    Matches the existing inventory schema: stock_movements uses
    from_warehouse_id / to_warehouse_id and a `type` column constrained to
    ('transfer', 'adjustment', 'sale', 'purchase').
    """
    row = db.execute(
        "SELECT * FROM stock WHERE producto_id = ? AND warehouse_id = ?",
        (producto_id, warehouse_id),
    ).fetchone()
    if row:
        db.execute(
            "UPDATE stock SET quantity = quantity + ? WHERE id = ?",
            (qty, row["id"]),
        )
    else:
        db.execute(
            "INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
            (producto_id, warehouse_id, qty),
        )

    if qty >= 0:
        db.execute(
            "INSERT INTO stock_movements (producto_id, to_warehouse_id, quantity, type, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (producto_id, warehouse_id, abs(qty), movement_type, reason),
        )
    else:
        db.execute(
            "INSERT INTO stock_movements (producto_id, from_warehouse_id, quantity, type, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (producto_id, warehouse_id, abs(qty), movement_type, reason),
        )


@register("core.purchase.receipts.list")
def receipts_list(purchase_order_id=None, **kwargs):
    db = get_db()
    if purchase_order_id:
        rows = db.execute(
            "SELECT * FROM purchase_receipts WHERE purchase_order_id = ? ORDER BY id DESC",
            (purchase_order_id,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM purchase_receipts ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        lines = db.execute(
            "SELECT l.*, p.nombre AS producto_nombre FROM purchase_receipt_lines l "
            "LEFT JOIN productos p ON p.id = l.producto_id WHERE l.receipt_id = ?",
            (r["id"],),
        ).fetchall()
        d["lines"] = [dict(l) for l in lines]
        out.append(d)
    return out


@register("core.purchase.receipts.create")
def receipts_create(purchase_order_id=None, warehouse_id=None, lines=None, notes=None, **kwargs):
    """Register a (possibly partial) receipt against a purchase order.

    lines = [{"producto_id": 1, "qty_received": 5}]
    Omitting lines receives everything still pending.
    """
    if not purchase_order_id:
        return {"error": "purchase_order_id required"}

    db = get_db()
    po = db.execute("SELECT * FROM purchase_orders WHERE id = ?", (purchase_order_id,)).fetchone()
    if not po:
        return {"error": "purchase order not found"}
    if po["status"] in ("received", "cancelled"):
        return {"error": f"purchase order is {po['status']}"}

    po_items = db.execute(
        "SELECT * FROM purchase_order_items WHERE order_id = ?", (purchase_order_id,)
    ).fetchall()
    if not po_items:
        return {"error": "purchase order has no items"}

    pending = {
        it["producto_id"]: float(it["quantity"]) - float(it["qty_received"] or 0)
        for it in po_items
    }
    price_by_prod = {it["producto_id"]: float(it["precio_unitario"] or 0) for it in po_items}

    lines = _parse_lines(lines)
    if not lines:
        lines = [
            {"producto_id": pid, "qty_received": qty}
            for pid, qty in pending.items() if qty > 0
        ]
    if not lines:
        return {"error": "nothing pending to receive"}

    wh = warehouse_id or po["warehouse_id"]
    if not wh:
        first_wh = db.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()
        wh = first_wh["id"] if first_wh else None
    if not wh:
        return {"error": "no warehouse available; create one first"}

    # validate
    for l in lines:
        pid = l.get("producto_id")
        qty = float(l.get("qty_received", 0))
        if pid not in pending:
            return {"error": f"producto_id {pid} is not in this purchase order"}
        if qty <= 0:
            return {"error": f"qty_received must be > 0 for producto_id {pid}"}
        if qty > pending[pid] + 1e-9:
            return {"error": f"qty_received {qty} exceeds pending {pending[pid]} for producto_id {pid}"}

    folio = _next_folio("receipt")
    try:
        cur = db.execute(
            "INSERT INTO purchase_receipts (folio, purchase_order_id, supplier_id, warehouse_id, "
            "status, received_at, notes, company_id) VALUES (?, ?, ?, ?, 'done', ?, ?, ?)",
            (folio, purchase_order_id, po["supplier_id"], wh,
             datetime.utcnow().isoformat(), notes,
             po["company_id"] if "company_id" in po.keys() else None),
        )
        receipt_id = cur.lastrowid

        received_total = 0.0
        for l in lines:
            pid = l.get("producto_id")
            qty = float(l.get("qty_received", 0))
            price = price_by_prod.get(pid, 0)
            db.execute(
                "INSERT INTO purchase_receipt_lines (receipt_id, producto_id, qty_received, unit_price) "
                "VALUES (?, ?, ?, ?)",
                (receipt_id, pid, qty, price),
            )
            db.execute(
                "UPDATE purchase_order_items SET qty_received = COALESCE(qty_received,0) + ? "
                "WHERE order_id = ? AND producto_id = ?",
                (qty, purchase_order_id, pid),
            )
            _add_stock(db, pid, wh, qty, f"purchase receipt {folio or receipt_id}", "purchase")
            # Every inbound quantity becomes a cost layer at its real purchase
            # price, so later outbound movements can compute a true COGS.
            try:
                from core.valuation import add_layer
                add_layer(db, pid, wh, qty, price,
                          source_type="purchase_receipt", source_id=receipt_id)
            except Exception:
                pass  # valuation must never block a receipt
            # Tracked products also get their lot/serial recorded
            try:
                from core.lots import receive_into_lot
                receive_into_lot(db, pid, wh, qty,
                                 lot_code=(l.get("lot_code") if isinstance(l, dict) else None),
                                 expiry_date=(l.get("expiry_date") if isinstance(l, dict) else None),
                                 source_type="purchase_receipt", source_id=receipt_id)
            except Exception:
                pass
            received_total += qty * price

        # recompute PO status
        items_after = db.execute(
            "SELECT quantity, COALESCE(qty_received,0) AS rec FROM purchase_order_items WHERE order_id = ?",
            (purchase_order_id,),
        ).fetchall()
        fully = all(float(i["rec"]) >= float(i["quantity"]) - 1e-9 for i in items_after)
        new_status = "received" if fully else "partially_received"
        db.execute("UPDATE purchase_orders SET status = ? WHERE id = ?", (new_status, purchase_order_id))
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"receipt failed: {e}"}
    finally:
        db.close()

    return {
        "receipt_id": receipt_id,
        "folio": folio,
        "purchase_order_id": purchase_order_id,
        "warehouse_id": wh,
        "lines": len(lines),
        "received_value": round(received_total, 2),
        "purchase_order_status": new_status,
    }


@register("core.purchase.receipts.pending")
def receipts_pending(purchase_order_id=None, **kwargs):
    """Show pending quantities per line for a purchase order."""
    if not purchase_order_id:
        return {"error": "purchase_order_id required"}
    db = get_db()
    rows = db.execute(
        "SELECT i.producto_id, p.nombre AS producto_nombre, i.quantity, "
        "COALESCE(i.qty_received,0) AS qty_received "
        "FROM purchase_order_items i LEFT JOIN productos p ON p.id = i.producto_id "
        "WHERE i.order_id = ?",
        (purchase_order_id,),
    ).fetchall()
    out = []
    for r in rows:
        pend = float(r["quantity"]) - float(r["qty_received"])
        out.append({
            "producto_id": r["producto_id"],
            "producto_nombre": r["producto_nombre"],
            "ordered": r["quantity"],
            "received": r["qty_received"],
            "pending": round(pend, 4),
        })
    return {"purchase_order_id": purchase_order_id, "lines": out,
            "fully_received": all(l["pending"] <= 0 for l in out) if out else False}


@register("core.purchase.returns.list")
def returns_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM purchase_returns ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        lines = db.execute(
            "SELECT l.*, p.nombre AS producto_nombre FROM purchase_return_lines l "
            "LEFT JOIN productos p ON p.id = l.producto_id WHERE l.return_id = ?",
            (r["id"],),
        ).fetchall()
        d["lines"] = [dict(l) for l in lines]
        out.append(d)
    return out


@register("core.purchase.returns.create")
def returns_create(receipt_id=None, lines=None, reason=None, **kwargs):
    """Return goods to supplier. Decrements stock. lines = [{"producto_id":1,"qty":2}]"""
    if not receipt_id:
        return {"error": "receipt_id required"}
    lines = _parse_lines(lines)
    if not lines:
        return {"error": "lines required"}

    db = get_db()
    receipt = db.execute("SELECT * FROM purchase_receipts WHERE id = ?", (receipt_id,)).fetchone()
    if not receipt:
        return {"error": "receipt not found"}

    rec_lines = db.execute(
        "SELECT * FROM purchase_receipt_lines WHERE receipt_id = ?", (receipt_id,)
    ).fetchall()
    received = {l["producto_id"]: float(l["qty_received"]) for l in rec_lines}
    prices = {l["producto_id"]: float(l["unit_price"] or 0) for l in rec_lines}

    for l in lines:
        pid = l.get("producto_id")
        qty = float(l.get("qty", 0))
        if pid not in received:
            return {"error": f"producto_id {pid} was not in this receipt"}
        if qty <= 0:
            return {"error": f"qty must be > 0 for producto_id {pid}"}
        if qty > received[pid] + 1e-9:
            return {"error": f"cannot return {qty}, only {received[pid]} received for producto_id {pid}"}

    folio = _next_folio("credit_note")
    total = sum(float(l.get("qty", 0)) * prices.get(l.get("producto_id"), 0) for l in lines)
    try:
        cur = db.execute(
            "INSERT INTO purchase_returns (folio, receipt_id, supplier_id, warehouse_id, reason, status, total) "
            "VALUES (?, ?, ?, ?, ?, 'done', ?)",
            (folio, receipt_id, receipt["supplier_id"], receipt["warehouse_id"], reason, total),
        )
        return_id = cur.lastrowid

        for l in lines:
            pid = l.get("producto_id")
            qty = float(l.get("qty", 0))
            db.execute(
                "INSERT INTO purchase_return_lines (return_id, producto_id, qty, unit_price) VALUES (?, ?, ?, ?)",
                (return_id, pid, qty, prices.get(pid, 0)),
            )
            _add_stock(db, pid, receipt["warehouse_id"], -qty,
                       f"purchase return {folio or return_id}", "purchase")
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"return failed: {e}"}
    finally:
        db.close()

    return {
        "return_id": return_id,
        "folio": folio,
        "receipt_id": receipt_id,
        "supplier_id": receipt["supplier_id"],
        "total": round(total, 2),
        "lines": len(lines),
    }
