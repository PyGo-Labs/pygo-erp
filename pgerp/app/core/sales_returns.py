"""PyGo ERP — Sales returns and credit notes.

Purchase returns existed; the sales side did not. A customer return has to put
stock back, give value back to the cost layers, and produce a credit note the
customer can apply to an invoice.
"""
import os
import sys
import sqlite3
from datetime import datetime

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


def _next_folio(db, doc_type, prefix):
    """Try the shared sequence service, else fall back to a local counter."""
    try:
        from core.commercial_terms import sequences_next
        r = sequences_next(doc_type=doc_type)
        if isinstance(r, dict) and r.get("folio"):
            return r["folio"]
    except Exception:
        pass
    year = datetime.now().year
    table = "sales_returns" if doc_type == "sales_return" else "credit_notes"
    n = db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
    return f"{prefix}-{year}-{int(n) + 1:05d}"


def _line_total(quantity, unit_price, discount_pct):
    gross = float(quantity) * float(unit_price or 0)
    disc = gross * (float(discount_pct or 0) / 100.0)
    return round(gross - disc, 6)


# ------------------------------------------------------------- sales returns

@register("core.sales_returns.list")
def sales_returns_list(status=None, cliente_id=None, **kwargs):
    db = get_db()
    where, params = [], []
    if status:
        where.append("r.status = ?")
        params.append(status)
    if cliente_id:
        where.append("r.cliente_id = ?")
        params.append(cliente_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(
        f"SELECT r.*, c.nombre AS cliente_nombre, w.name AS warehouse_name "
        f"FROM sales_returns r "
        f"LEFT JOIN clientes c ON c.id = r.cliente_id "
        f"LEFT JOIN warehouses w ON w.id = r.warehouse_id "
        f"{clause} ORDER BY r.created_at DESC, r.id DESC LIMIT 200", params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["restock"] = bool(d.get("restock"))
        d["lines"] = [dict(x) for x in db.execute(
            "SELECT l.*, p.codigo, p.nombre FROM sales_return_lines l "
            "JOIN productos p ON p.id = l.producto_id WHERE l.return_id = ?",
            (r["id"],)).fetchall()]
        out.append(d)
    return out


@register("core.sales_returns.create")
def sales_returns_create(cliente_id=None, lines=None, sales_order_id=None,
                        invoice_id=None, warehouse_id=None, reason=None,
                        restock=1, company_id=None, **kwargs):
    """Register a customer return. Validates against what was actually sold."""
    if not cliente_id or not lines:
        return {"error": "cliente_id and lines required"}
    if not isinstance(lines, list) or not lines:
        return {"error": "lines must be a non-empty list"}

    db = get_db()
    if not db.execute("SELECT 1 FROM clientes WHERE id = ?", (cliente_id,)).fetchone():
        return {"error": "customer not found"}

    # A return cannot exceed what the order actually shipped
    sold = {}
    if sales_order_id:
        order = db.execute("SELECT * FROM sales_orders WHERE id = ?",
                           (sales_order_id,)).fetchone()
        if not order:
            return {"error": "sales order not found"}
        if order["cliente_id"] != int(cliente_id):
            return {"error": "the order belongs to a different customer"}
        for it in db.execute(
                "SELECT producto_id, quantity FROM sales_order_items WHERE order_id = ?",
                (sales_order_id,)).fetchall():
            sold[it["producto_id"]] = float(it["quantity"])

        already = db.execute(
            "SELECT l.producto_id, COALESCE(SUM(l.quantity), 0) AS q "
            "FROM sales_return_lines l JOIN sales_returns r ON r.id = l.return_id "
            "WHERE r.sales_order_id = ? AND r.status != 'cancelled' "
            "GROUP BY l.producto_id", (sales_order_id,)).fetchall()
        for row in already:
            sold[row["producto_id"]] = sold.get(row["producto_id"], 0) - float(row["q"])

    prepared, subtotal = [], 0.0
    for l in lines:
        pid = l.get("producto_id")
        if not pid:
            return {"error": "every line needs a producto_id"}
        try:
            qty = float(l.get("quantity", l.get("qty", 0)) or 0)
        except (TypeError, ValueError):
            return {"error": "quantity must be numeric"}
        if qty <= 0:
            return {"error": f"quantity for product {pid} must be > 0"}

        if sales_order_id:
            available = sold.get(int(pid))
            if available is None:
                return {"error": f"product {pid} was not in order {sales_order_id}"}
            if qty > available + 1e-9:
                return {"error": f"cannot return {qty} of product {pid}: "
                                 f"only {round(available, 6)} available to return",
                        "producto_id": pid, "returnable": round(available, 6)}

        price = l.get("unit_price")
        if price is None:
            row = db.execute(
                "SELECT precio_unitario FROM sales_order_items "
                "WHERE order_id = ? AND producto_id = ?",
                (sales_order_id, pid)).fetchone() if sales_order_id else None
            if row:
                price = row["precio_unitario"]
            else:
                prod = db.execute("SELECT precio_unitario FROM productos WHERE id = ?",
                                  (pid,)).fetchone()
                price = prod["precio_unitario"] if prod else 0

        disc = float(l.get("discount_pct", 0) or 0)
        total = _line_total(qty, price, disc)
        subtotal += total
        prepared.append((pid, qty, float(price or 0), disc, total, l.get("lot_id")))

    folio = _next_folio(db, "sales_return", "DEV")
    cur = db.execute(
        "INSERT INTO sales_returns (folio, cliente_id, sales_order_id, invoice_id, "
        "warehouse_id, reason, status, restock, subtotal, total, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)",
        (folio, cliente_id, sales_order_id, invoice_id, warehouse_id, reason,
         1 if str(restock) in ("1", "True", "true", "yes") else 0,
         round(subtotal, 2), round(subtotal, 2), company_id))
    return_id = cur.lastrowid

    for pid, qty, price, disc, total, lot_id in prepared:
        db.execute(
            "INSERT INTO sales_return_lines (return_id, producto_id, quantity, "
            "unit_price, discount_pct, line_total, lot_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (return_id, pid, qty, price, disc, total, lot_id))
    db.commit()

    return {"id": return_id, "folio": folio, "cliente_id": cliente_id,
            "status": "draft", "lines": len(prepared),
            "subtotal": round(subtotal, 2), "total": round(subtotal, 2)}


@register("core.sales_returns.receive")
def sales_returns_receive(return_id=None, warehouse_id=None, **kwargs):
    """Take the goods back: stock in, cost layers restored, lots re-entered."""
    if not return_id:
        return {"error": "return_id required"}
    db = get_db()
    ret = db.execute("SELECT * FROM sales_returns WHERE id = ?", (return_id,)).fetchone()
    if not ret:
        return {"error": "return not found"}
    if ret["status"] != "draft":
        return {"error": f"cannot receive a return in status '{ret['status']}'"}

    wid = warehouse_id or ret["warehouse_id"]
    if not wid:
        row = db.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()
        wid = row["id"] if row else None
    if not wid:
        return {"error": "no warehouse available to receive into"}

    lines = db.execute("SELECT * FROM sales_return_lines WHERE return_id = ?",
                       (return_id,)).fetchall()
    restock = bool(ret["restock"])
    restocked, relayered = [], 0.0

    for l in lines:
        pid, qty = l["producto_id"], float(l["quantity"])
        if not restock:
            continue

        existing = db.execute(
            "SELECT id FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (pid, wid)).fetchone()
        if existing:
            db.execute("UPDATE stock SET quantity = quantity + ? WHERE id = ?",
                       (qty, existing["id"]))
        else:
            db.execute(
                "INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
                (pid, wid, qty))

        db.execute(
            "INSERT INTO stock_movements (producto_id, to_warehouse_id, quantity, "
            "type, reason) VALUES (?, ?, ?, 'adjustment', ?)",
            (pid, wid, qty, f"sales return {ret['folio'] or return_id}"))

        # Returned goods re-enter valuation at the cost they left at, so COGS
        # is reversed instead of being silently overstated.
        try:
            from core.valuation import add_layer, get_db as vdb  # noqa: F401
            cost_row = db.execute(
                "SELECT unit_cost FROM stock_valuation_entries "
                "WHERE producto_id = ? AND movement_type = 'out' "
                "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
            unit_cost = float(cost_row["unit_cost"]) if cost_row else 0.0
            if unit_cost <= 0:
                prod = db.execute("SELECT cost FROM productos WHERE id = ?",
                                  (pid,)).fetchone()
                unit_cost = float(prod["cost"] or 0) if prod else 0.0
            add_layer(db, pid, wid, qty, unit_cost,
                      source_type="sales_return", source_id=return_id)
            relayered += qty * unit_cost
        except Exception:
            pass

        # Lot-tracked goods come back into a lot
        try:
            from core.lots import receive_into_lot
            receive_into_lot(db, pid, wid, qty, source_type="sales_return",
                             source_id=return_id)
        except Exception:
            pass

        restocked.append({"producto_id": pid, "quantity": qty})

    db.execute(
        "UPDATE sales_returns SET status = 'received', warehouse_id = ?, "
        "received_at = CURRENT_TIMESTAMP WHERE id = ?", (wid, return_id))
    db.commit()

    return {"received": True, "return_id": return_id, "folio": ret["folio"],
            "warehouse_id": wid, "restocked": restocked,
            "restock": restock,
            "value_returned_to_inventory": round(relayered, 2),
            "note": None if restock else "restock disabled: goods were scrapped"}


@register("core.sales_returns.credit")
def sales_returns_credit(return_id=None, **kwargs):
    """Issue the credit note for a received return."""
    if not return_id:
        return {"error": "return_id required"}
    db = get_db()
    ret = db.execute("SELECT * FROM sales_returns WHERE id = ?", (return_id,)).fetchone()
    if not ret:
        return {"error": "return not found"}
    if ret["status"] == "credited":
        return {"error": "this return already has a credit note"}
    if ret["status"] != "received":
        return {"error": f"receive the goods first (status is '{ret['status']}')"}

    amount = round(float(ret["total"] or 0), 2)
    if amount <= 0:
        return {"error": "the return has no value to credit"}

    folio = _next_folio(db, "credit_note", "NC")
    cur = db.execute(
        "INSERT INTO credit_notes (folio, cliente_id, return_id, invoice_id, amount, "
        "status, currency, reason, company_id) "
        "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)",
        (folio, ret["cliente_id"], return_id, ret["invoice_id"], amount,
         ret["currency"] or "USD", ret["reason"], ret["company_id"]))
    note_id = cur.lastrowid
    db.execute(
        "UPDATE sales_returns SET status = 'credited', "
        "credited_at = CURRENT_TIMESTAMP WHERE id = ?", (return_id,))
    db.commit()

    return {"credited": True, "return_id": return_id, "credit_note_id": note_id,
            "folio": folio, "amount": amount, "status": "open"}


@register("core.sales_returns.cancel")
def sales_returns_cancel(return_id=None, **kwargs):
    if not return_id:
        return {"error": "return_id required"}
    db = get_db()
    ret = db.execute("SELECT status FROM sales_returns WHERE id = ?",
                     (return_id,)).fetchone()
    if not ret:
        return {"error": "return not found"}
    if ret["status"] == "credited":
        return {"error": "a credited return cannot be cancelled"}
    db.execute("UPDATE sales_returns SET status = 'cancelled' WHERE id = ?",
               (return_id,))
    db.commit()
    return {"cancelled": True, "return_id": return_id}


# ------------------------------------------------------------- credit notes

@register("core.credit_notes.list")
def credit_notes_list(cliente_id=None, status=None, **kwargs):
    db = get_db()
    where, params = [], []
    if cliente_id:
        where.append("n.cliente_id = ?")
        params.append(cliente_id)
    if status:
        where.append("n.status = ?")
        params.append(status)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(
        f"SELECT n.*, c.nombre AS cliente_nombre FROM credit_notes n "
        f"LEFT JOIN clientes c ON c.id = n.cliente_id "
        f"{clause} ORDER BY n.created_at DESC, n.id DESC LIMIT 200", params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["remaining"] = round(float(d["amount"]) - float(d["applied_amount"] or 0), 2)
        out.append(d)
    return out


@register("core.credit_notes.apply")
def credit_notes_apply(credit_note_id=None, invoice_id=None, amount=None, **kwargs):
    """Apply a credit note to an invoice, reducing what the customer owes."""
    if not credit_note_id or not invoice_id:
        return {"error": "credit_note_id and invoice_id required"}

    db = get_db()
    note = db.execute("SELECT * FROM credit_notes WHERE id = ?",
                      (credit_note_id,)).fetchone()
    if not note:
        return {"error": "credit note not found"}
    if note["status"] in ("applied", "cancelled"):
        return {"error": f"credit note is {note['status']}"}

    invoice = db.execute("SELECT * FROM facturas WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return {"error": "invoice not found"}
    if invoice["cliente_id"] != note["cliente_id"]:
        return {"error": "the invoice belongs to a different customer"}

    remaining_note = round(float(note["amount"]) - float(note["applied_amount"] or 0), 2)
    invoice_due = round(float(invoice["total"]) - float(invoice["amount_paid"] or 0), 2)
    if invoice_due <= 0:
        return {"error": "the invoice is already settled"}

    want = round(float(amount), 2) if amount is not None else min(remaining_note,
                                                                 invoice_due)
    if want <= 0:
        return {"error": "amount must be > 0"}
    if want > remaining_note + 0.01:
        return {"error": f"credit note only has {remaining_note} left",
                "remaining": remaining_note}
    if want > invoice_due + 0.01:
        return {"error": f"the invoice only owes {invoice_due}",
                "invoice_due": invoice_due}

    db.execute(
        "INSERT INTO credit_note_applications (credit_note_id, invoice_id, amount) "
        "VALUES (?, ?, ?)", (credit_note_id, invoice_id, want))
    db.execute(
        "UPDATE facturas SET amount_paid = COALESCE(amount_paid, 0) + ? WHERE id = ?",
        (want, invoice_id))

    applied_total = round(float(note["applied_amount"] or 0) + want, 2)
    status = "applied" if applied_total >= float(note["amount"]) - 0.01 \
        else "partially_applied"
    db.execute("UPDATE credit_notes SET applied_amount = ?, status = ? WHERE id = ?",
               (applied_total, status, credit_note_id))

    new_due = round(invoice_due - want, 2)
    if new_due <= 0.01:
        try:
            db.execute("UPDATE facturas SET payment_status = 'paid' WHERE id = ?",
                       (invoice_id,))
        except sqlite3.OperationalError:
            pass
    db.commit()

    return {"applied": True, "credit_note_id": credit_note_id,
            "invoice_id": invoice_id, "amount_applied": want,
            "credit_note_status": status,
            "credit_note_remaining": round(float(note["amount"]) - applied_total, 2),
            "invoice_due_after": new_due}


@register("core.credit_notes.cancel")
def credit_notes_cancel(credit_note_id=None, **kwargs):
    if not credit_note_id:
        return {"error": "credit_note_id required"}
    db = get_db()
    note = db.execute("SELECT * FROM credit_notes WHERE id = ?",
                      (credit_note_id,)).fetchone()
    if not note:
        return {"error": "credit note not found"}
    if float(note["applied_amount"] or 0) > 0:
        return {"error": "a credit note that was already applied cannot be cancelled"}
    db.execute("UPDATE credit_notes SET status = 'cancelled' WHERE id = ?",
               (credit_note_id,))
    db.commit()
    return {"cancelled": True, "credit_note_id": credit_note_id}
