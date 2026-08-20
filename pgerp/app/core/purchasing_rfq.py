"""PyGo ERP — RFQ (Request For Quotation) with supplier comparison."""
import os
import sys
import json

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
        res = sequences_next(doc_type=doc_type)
        return res.get("folio")
    except Exception:
        return None


@register("core.rfq.list")
def rfq_list(status=None, **kwargs):
    db = get_db()
    if status:
        rfqs = db.execute("SELECT * FROM rfqs WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
    else:
        rfqs = db.execute("SELECT * FROM rfqs ORDER BY id DESC").fetchall()
    out = []
    for r in rfqs:
        d = dict(r)
        lines = db.execute(
            "SELECT l.*, p.nombre AS producto_nombre FROM rfq_lines l "
            "LEFT JOIN productos p ON p.id = l.producto_id WHERE l.rfq_id = ?",
            (r["id"],),
        ).fetchall()
        d["lines"] = [dict(l) for l in lines]
        d["quotes_count"] = db.execute(
            "SELECT COUNT(*) FROM rfq_quotes WHERE rfq_id = ?", (r["id"],)
        ).fetchone()[0]
        out.append(d)
    return out


@register("core.rfq.create")
def rfq_create(lines=None, deadline=None, notes=None, company_id=None, user_id=None, **kwargs):
    """Create an RFQ. lines = [{"producto_id": 1, "qty": 10}]"""
    lines = _parse_lines(lines)
    if not lines:
        return {"error": "lines required"}

    db = get_db()
    folio = _next_folio("rfq")
    cur = db.execute(
        "INSERT INTO rfqs (folio, status, deadline, notes, company_id, user_id) "
        "VALUES (?, 'draft', ?, ?, ?, ?)",
        (folio, deadline, notes, company_id, user_id),
    )
    rfq_id = cur.lastrowid
    for l in lines:
        # Accept qty or quantity; a missing/zero amount is an error rather than
        # a silent default of 1, which produced wrong purchase orders.
        raw_qty = l.get("qty", l.get("quantity"))
        try:
            qty = float(raw_qty)
        except (TypeError, ValueError):
            db.rollback()
            db.close()
            return {"error": f"line for producto_id {l.get('producto_id')} needs qty"}
        if qty <= 0:
            db.rollback()
            db.close()
            return {"error": f"qty must be > 0 for producto_id {l.get('producto_id')}"}
        db.execute(
            "INSERT INTO rfq_lines (rfq_id, producto_id, qty, uom_id) VALUES (?, ?, ?, ?)",
            (rfq_id, l.get("producto_id"), qty, l.get("uom_id")),
        )
    db.commit()
    return {"id": rfq_id, "folio": folio, "status": "draft", "lines": len(lines)}


@register("core.rfq.send")
def rfq_send(rfq_id=None, **kwargs):
    if not rfq_id:
        return {"error": "rfq_id required"}
    db = get_db()
    rfq = db.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,)).fetchone()
    if not rfq:
        return {"error": "rfq not found"}
    if rfq["status"] != "draft":
        return {"error": f"rfq is {rfq['status']}, expected draft"}
    db.execute("UPDATE rfqs SET status = 'sent' WHERE id = ?", (rfq_id,))
    db.commit()
    return {"id": rfq_id, "status": "sent"}


@register("core.rfq.quotes.add")
def rfq_quotes_add(rfq_id=None, supplier_id=None, lines=None, lead_time_days=0, currency="USD", notes=None, **kwargs):
    """Register a supplier quote for an RFQ. lines = [{"producto_id":1,"qty":10,"unit_price":95}]"""
    if not rfq_id or not supplier_id:
        return {"error": "rfq_id and supplier_id required"}
    lines = _parse_lines(lines)
    if not lines:
        return {"error": "lines required"}

    db = get_db()
    if not db.execute("SELECT 1 FROM rfqs WHERE id = ?", (rfq_id,)).fetchone():
        return {"error": "rfq not found"}

    total = sum(float(l.get("qty", l.get("quantity", 1)) or 1) * float(l.get("unit_price", 0)) for l in lines)
    cur = db.execute(
        "INSERT INTO rfq_quotes (rfq_id, supplier_id, total, currency, lead_time_days, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (rfq_id, supplier_id, total, currency, int(lead_time_days or 0), notes),
    )
    quote_id = cur.lastrowid
    for l in lines:
        db.execute(
            "INSERT INTO rfq_quote_lines (quote_id, producto_id, qty, unit_price) VALUES (?, ?, ?, ?)",
            (quote_id, l.get("producto_id"),
             float(l.get("qty", l.get("quantity", 1)) or 1),
             float(l.get("unit_price", 0))),
        )
    db.execute("UPDATE rfqs SET status = 'quoted' WHERE id = ? AND status IN ('draft','sent')", (rfq_id,))
    db.commit()
    return {"quote_id": quote_id, "rfq_id": rfq_id, "supplier_id": supplier_id, "total": round(total, 2)}


@register("core.rfq.compare")
def rfq_compare(rfq_id=None, **kwargs):
    """Compare all supplier quotes for an RFQ and recommend the best."""
    if not rfq_id:
        return {"error": "rfq_id required"}
    db = get_db()
    rfq = db.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,)).fetchone()
    if not rfq:
        return {"error": "rfq not found"}

    quotes = db.execute(
        "SELECT q.*, s.name AS supplier_name FROM rfq_quotes q "
        "LEFT JOIN suppliers s ON s.id = q.supplier_id "
        "WHERE q.rfq_id = ? ORDER BY q.total ASC",
        (rfq_id,),
    ).fetchall()

    if not quotes:
        return {"rfq_id": rfq_id, "folio": rfq["folio"], "quotes": [], "recommendation": None}

    comparison = []
    for q in quotes:
        lines = db.execute(
            "SELECT ql.*, p.nombre AS producto_nombre FROM rfq_quote_lines ql "
            "LEFT JOIN productos p ON p.id = ql.producto_id WHERE ql.quote_id = ?",
            (q["id"],),
        ).fetchall()
        comparison.append({
            "quote_id": q["id"],
            "supplier_id": q["supplier_id"],
            "supplier_name": q["supplier_name"],
            "total": q["total"],
            "currency": q["currency"],
            "lead_time_days": q["lead_time_days"],
            "lines": [dict(l) for l in lines],
        })

    cheapest = comparison[0]
    fastest = min(comparison, key=lambda c: c["lead_time_days"])
    return {
        "rfq_id": rfq_id,
        "folio": rfq["folio"],
        "quotes": comparison,
        "recommendation": {
            "cheapest": {"supplier": cheapest["supplier_name"], "total": cheapest["total"], "quote_id": cheapest["quote_id"]},
            "fastest": {"supplier": fastest["supplier_name"], "lead_time_days": fastest["lead_time_days"], "quote_id": fastest["quote_id"]},
        },
        "savings_vs_worst": round(comparison[-1]["total"] - cheapest["total"], 2) if len(comparison) > 1 else 0,
    }


@register("core.rfq.award")
def rfq_award(quote_id=None, warehouse_id=None, **kwargs):
    """Award an RFQ quote: creates a purchase order from the winning quote."""
    if not quote_id:
        return {"error": "quote_id required"}
    db = get_db()
    quote = db.execute("SELECT * FROM rfq_quotes WHERE id = ?", (quote_id,)).fetchone()
    if not quote:
        return {"error": "quote not found"}

    lines = db.execute("SELECT * FROM rfq_quote_lines WHERE quote_id = ?", (quote_id,)).fetchall()
    if not lines:
        return {"error": "quote has no lines"}

    folio = _next_folio("purchase_order")
    total = float(quote["total"])
    cur = db.execute(
        "INSERT INTO purchase_orders (folio, supplier_id, status, total, currency, warehouse_id, rfq_id) "
        "VALUES (?, ?, 'draft', ?, ?, ?, ?)",
        (folio, quote["supplier_id"], total, quote["currency"], warehouse_id, quote["rfq_id"]),
    )
    po_id = cur.lastrowid
    for l in lines:
        db.execute(
            "INSERT INTO purchase_order_items (order_id, producto_id, quantity, precio_unitario) "
            "VALUES (?, ?, ?, ?)",
            (po_id, l["producto_id"], l["qty"], l["unit_price"]),
        )

    db.execute("UPDATE rfq_quotes SET status = 'awarded' WHERE id = ?", (quote_id,))
    db.execute("UPDATE rfq_quotes SET status = 'rejected' WHERE rfq_id = ? AND id != ?", (quote["rfq_id"], quote_id))
    db.execute("UPDATE rfqs SET status = 'awarded' WHERE id = ?", (quote["rfq_id"],))
    db.commit()
    return {
        "purchase_order_id": po_id,
        "folio": folio,
        "supplier_id": quote["supplier_id"],
        "total": total,
        "rfq_id": quote["rfq_id"],
    }
