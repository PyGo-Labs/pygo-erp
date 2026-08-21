"""PyGo ERP V2.0 — Sales & Purchases module.

Provides:
- Sales Orders (pedidos de venta) with line items
- Purchase Orders (pedidos de compra) with line items
- Order status workflow (draft → confirmed → delivered → invoiced)
- Auto-invoice generation from sales order
- Customer quotes
- Supplier management (via Clientes with type)
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.auth import Session, User
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


# --- Sales Orders ---

@register("core.sales.orders.list")
def sales_orders_list(status=None, cliente_id=None, **kwargs):
    """List sales orders (optionally filtered)."""
    db = get_db()
    query = """
        SELECT so.*, c.nombre as cliente_nombre, c.email as cliente_email
        FROM sales_orders so
        LEFT JOIN clientes c ON so.cliente_id = c.id
    """
    filters = []
    params = []
    if status:
        filters.append("so.status = ?")
        params.append(status)
    if cliente_id:
        filters.append("so.cliente_id = ?")
        params.append(cliente_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY so.created_at DESC"
    rows = db.execute(query, params).fetchall()
    result = []
    for row in rows:
        order = dict(row)
        items = db.execute("SELECT * FROM sales_order_items WHERE order_id = ?", (order["id"],)).fetchall()
        order["items"] = [dict(i) for i in items]
        result.append(order)
    return result


@register("core.sales.orders.create")
def sales_orders_create(cliente_id=None, items=None, notes=None, token=None, **kwargs):
    """Create a new sales order with line items."""
    if not cliente_id:
        return {"error": "cliente_id required"}
    if not items or not isinstance(items, list):
        return {"error": "items must be a non-empty list"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
        user_id = user.id
    else:
        user_id = None
    
    # Calculate totals. Accept discount or discount_pct, and keep the gross
    # subtotal plus the discount amount so the document shows what was given away.
    subtotal = 0
    gross_subtotal = 0
    discount_total = 0
    for item in items:
        qty = float(item.get("quantity", 1))
        price = float(item.get("precio_unitario", item.get("price", 0)))
        discount = float(item.get("discount_pct", item.get("discount", 0)) or 0)
        if discount < 0 or discount > 100:
            return {"error": f"discount_pct must be between 0 and 100, got {discount}"}
        gross = qty * price
        item_total = gross * (1 - discount / 100)
        gross_subtotal += gross
        discount_total += gross - item_total
        subtotal += item_total
    
    tax_rate = float(kwargs.get("tax_rate", 16))
    tax = subtotal * tax_rate / 100
    total = subtotal + tax

    # Refuse the order when it would push the customer past their credit limit.
    try:
        from core.credit import check_credit, log_credit_event
        decision = check_credit(db, cliente_id, total)
        log_credit_event(db, cliente_id, "order_create", "sales_order", None,
                         total, decision)
        db.commit()
        if not decision.get("allowed"):
            return {"error": decision.get("reason", "credit check failed"),
                    "credit": {k: decision.get(k) for k in
                               ("credit_limit", "exposure", "projected",
                                "available", "over_by", "open_invoices",
                                "pending_orders")}}
    except ImportError:
        pass
    
    cursor = db.execute(
        """INSERT INTO sales_orders (cliente_id, status, subtotal, tax, total, notes, user_id, created_at)
           VALUES (?, 'draft', ?, ?, ?, ?, ?, ?)""",
        (cliente_id, subtotal, tax, total, notes, user_id, datetime.utcnow().isoformat())
    )
    order_id = cursor.lastrowid

    try:
        db.execute(
            "UPDATE sales_orders SET gross_subtotal = ?, discount_total = ? WHERE id = ?",
            (round(gross_subtotal, 2), round(discount_total, 2), order_id))
    except Exception:
        pass
    
    # Insert line items
    for item in items:
        qty = float(item.get("quantity", 1))
        price = float(item.get("precio_unitario", item.get("price", 0)))
        disc = float(item.get("discount_pct", item.get("discount", 0)) or 0)
        line_total = round(qty * price * (1 - disc / 100), 6)
        db.execute(
            """INSERT INTO sales_order_items (order_id, producto_id, quantity, precio_unitario, discount)
               VALUES (?, ?, ?, ?, ?)""",
            (order_id, item.get("producto_id"), qty, price, disc)
        )
        # discount_pct/line_total live in the D3 columns; keep `discount` in sync
        try:
            db.execute(
                "UPDATE sales_order_items SET discount_pct = ?, line_total = ? "
                "WHERE order_id = ? AND producto_id = ? AND line_total = 0",
                (disc, line_total, order_id, item.get("producto_id")))
        except Exception:
            pass
    
    db.commit()
    
    order = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    return dict(order)


@register("core.sales.orders.confirm")
def sales_orders_confirm(order_id=None, token=None, **kwargs):
    """Confirm a sales order (draft → confirmed)."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    row = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    if row["status"] != "draft":
        return {"error": f"cannot confirm order in status '{row['status']}'"}
    
    db.execute("UPDATE sales_orders SET status = 'confirmed' WHERE id = ?", (order_id,))
    db.commit()

    # Confirming promises the goods, so reserve them. What cannot be reserved
    # becomes a backorder instead of an over-promise nobody notices.
    #
    # The reservation helpers open their own connection, so this one must be
    # closed first or SQLite raises "database is locked".
    items = db.execute("SELECT * FROM sales_order_items WHERE order_id = ?",
                       (order_id,)).fetchall()
    plan = []
    for item in items:
        wh = db.execute(
            "SELECT warehouse_id FROM stock WHERE producto_id = ? "
            "ORDER BY quantity DESC LIMIT 1", (item["producto_id"],)).fetchone()
        plan.append((item["producto_id"], float(item["quantity"]),
                     wh["warehouse_id"] if wh else None))
    db.close()

    reserved, backordered = [], []
    try:
        from core.reservations import (get_db as res_db, available_quantity,
                                       reservations_reserve, backorders_create)
        for pid, want, wid in plan:
            if wid is None:
                backorders_create(document_type="sales_order", document_id=order_id,
                                  producto_id=pid, quantity_ordered=want,
                                  quantity_pending=want)
                backordered.append({"producto_id": pid, "quantity": want})
                continue

            probe = res_db()
            can = min(want, max(available_quantity(probe, pid, wid), 0))
            probe.close()

            if can > 0:
                r = reservations_reserve(producto_id=pid, warehouse_id=wid,
                                         quantity=can, document_type="sales_order",
                                         document_id=order_id)
                if "error" not in r:
                    reserved.append({"producto_id": pid, "quantity": can})
            missing = round(want - can, 6)
            if missing > 0:
                backorders_create(document_type="sales_order", document_id=order_id,
                                  producto_id=pid, warehouse_id=wid,
                                  quantity_ordered=want, quantity_pending=missing)
                backordered.append({"producto_id": pid, "quantity": missing})
    except Exception:
        pass  # reservations must never block a confirmation

    result = {"confirmed": True, "order_id": order_id}
    if reserved:
        result["reserved"] = reserved
    if backordered:
        result["backordered"] = backordered
    return result


@register("core.sales.orders.deliver")
def sales_orders_deliver(order_id=None, token=None, **kwargs):
    """Mark order as delivered and reduce stock."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    row = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    if row["status"] != "confirmed":
        return {"error": "must confirm first"}
    
    # Reduce stock for each item
    items = db.execute("SELECT * FROM sales_order_items WHERE order_id = ?", (order_id,)).fetchall()
    total_cogs = 0.0
    uncosted = 0.0
    lots_issued = []
    for item in items:
        # Find stock for this product (any warehouse)
        stock = db.execute(
            "SELECT * FROM stock WHERE producto_id = ? AND quantity >= ? LIMIT 1",
            (item["producto_id"], item["quantity"])
        ).fetchone()
        if not stock:
            return {"error": f"insufficient stock for product {item['producto_id']}"}
        
        db.execute(
            "UPDATE stock SET quantity = quantity - ? WHERE id = ?",
            (item["quantity"], stock["id"])
        )
        
        # Log movement
        db.execute(
            """INSERT INTO stock_movements (producto_id, from_warehouse_id, quantity, type, reason)
               VALUES (?, ?, ?, 'sale', ?)""",
            (item["producto_id"], stock["warehouse_id"], item["quantity"],
             f"Sales order #{order_id}")
        )

        # Draw down cost layers so COGS reflects what actually left the warehouse
        try:
            from core.valuation import consume_layers
            costing = consume_layers(
                db, item["producto_id"], stock["warehouse_id"], item["quantity"],
                source_type="sales_order", source_id=order_id)
            total_cogs += float(costing["total_cost"])
            uncosted += float(costing.get("uncosted_quantity") or 0)
        except Exception:
            pass  # valuation must never block a delivery

        # Issue the actual lots (FEFO) for tracked products
        try:
            from core.lots import consume_from_lots
            lot_result = consume_from_lots(
                db, item["producto_id"], stock["warehouse_id"], item["quantity"],
                source_type="sales_order", source_id=order_id)
            if lot_result["consumed"]:
                lots_issued.extend(lot_result["consumed"])
        except Exception:
            pass
    
    db.execute("UPDATE sales_orders SET status = 'delivered' WHERE id = ?", (order_id,))
    db.commit()
    db.close()  # release the write lock before the reservation helper opens its own

    # The goods physically left, so the reservation is consumed, not pending
    try:
        from core.reservations import reservations_fulfill
        reservations_fulfill(document_type="sales_order", document_id=order_id)
    except Exception:
        pass

    result = {"delivered": True, "order_id": order_id, "cogs": round(total_cogs, 2)}
    if lots_issued:
        result["lots_issued"] = lots_issued
    if uncosted:
        result["uncosted_quantity"] = round(uncosted, 6)
        result["note"] = "some quantity had no cost layer and used productos.cost"
    return result


@register("core.sales.orders.invoice")
def sales_orders_invoice(order_id=None, token=None, **kwargs):
    """Auto-generate invoice from delivered sales order."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    order = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "not found"}
    if order["status"] != "delivered":
        return {"error": "must deliver first"}
    
    # Create invoice
    cursor = db.execute(
        """INSERT INTO facturas (fecha, total, cliente_id, sales_order_id)
           VALUES (datetime('now'), ?, ?, ?)""",
        (order["total"], order["cliente_id"], order_id)
    )
    invoice_id = cursor.lastrowid
    
    # Mark order as invoiced
    db.execute("UPDATE sales_orders SET status = 'invoiced' WHERE id = ?", (order_id,))
    db.commit()
    
    invoice = db.execute("SELECT * FROM facturas WHERE id = ?", (invoice_id,)).fetchone()
    return {"invoiced": True, "invoice": dict(invoice)}


@register("core.sales.orders.cancel")
def sales_orders_cancel(order_id=None, reason=None, token=None):
    """Cancel a sales order."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    row = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    if row["status"] in ("invoiced",):
        return {"error": "cannot cancel invoiced order"}
    
    db.execute("UPDATE sales_orders SET status = 'cancelled', notes = COALESCE(notes, '') || ? WHERE id = ?",
               (f" [CANCELLED: {reason}]", order_id))
    db.commit()
    return {"cancelled": True, "order_id": order_id}


# --- Purchase Orders ---

@register("core.sales.purchase.list")
def purchase_orders_list(status=None, **kwargs):
    """List purchase orders."""
    db = get_db()
    query = "SELECT * FROM purchase_orders"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    result = []
    for row in rows:
        order = dict(row)
        items = db.execute("SELECT * FROM purchase_order_items WHERE order_id = ?", (order["id"],)).fetchall()
        order["items"] = [dict(i) for i in items]
        result.append(order)
    return result


@register("core.sales.purchase.create")
def purchase_orders_create(supplier_name=None, items=None, notes=None, token=None, **kwargs):
    """Create a purchase order."""
    if not items:
        return {"error": "items required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
        user_id = user.id
    else:
        user_id = None
    
    subtotal = sum(float(i.get("quantity", 1)) * float(i.get("precio_unitario", i.get("price", 0))) for i in items)
    tax_rate = float(kwargs.get("tax_rate", 16))
    tax = subtotal * tax_rate / 100
    total = subtotal + tax
    
    cursor = db.execute(
        """INSERT INTO purchase_orders (supplier_name, status, subtotal, tax, total, notes, user_id, created_at)
           VALUES (?, 'draft', ?, ?, ?, ?, ?, ?)""",
        (supplier_name, subtotal, tax, total, notes, user_id, datetime.utcnow().isoformat())
    )
    order_id = cursor.lastrowid
    
    for item in items:
        db.execute(
            """INSERT INTO purchase_order_items (order_id, producto_id, quantity, precio_unitario)
               VALUES (?, ?, ?, ?)""",
            (order_id, item.get("producto_id"), item.get("quantity", 1),
             item.get("precio_unitario", item.get("price", 0)))
        )
    
    db.commit()
    return {"id": order_id, "total": total, "status": "draft"}


@register("core.sales.purchase.receive")
def purchase_orders_receive(order_id=None, warehouse_id=None, token=None, **kwargs):
    """Receive purchase order → adds stock."""
    if not order_id:
        return {"error": "order_id required"}
    if not warehouse_id:
        return {"error": "warehouse_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    order = db.execute("SELECT * FROM purchase_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "not found"}
    if order["status"] != "draft":
        return {"error": "must be draft"}
    
    # Add stock
    items = db.execute("SELECT * FROM purchase_order_items WHERE order_id = ?", (order_id,)).fetchall()
    for item in items:
        existing = db.execute(
            "SELECT * FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (item["producto_id"], warehouse_id)
        ).fetchone()
        
        if existing:
            db.execute("UPDATE stock SET quantity = quantity + ? WHERE id = ?",
                       (item["quantity"], existing["id"]))
        else:
            db.execute("INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
                       (item["producto_id"], warehouse_id, item["quantity"]))
        
        db.execute(
            """INSERT INTO stock_movements (producto_id, to_warehouse_id, quantity, type, reason)
               VALUES (?, ?, ?, 'purchase', ?)""",
            (item["producto_id"], warehouse_id, item["quantity"],
             f"Purchase order #{order_id}")
        )
    
    db.execute("UPDATE purchase_orders SET status = 'received' WHERE id = ?", (order_id,))
    db.commit()
    return {"received": True, "order_id": order_id}


# --- Quotes ---

@register("core.sales.quotes.list")
def quotes_list(**kwargs):
    """List customer quotes."""
    db = get_db()
    rows = db.execute("SELECT * FROM quotes ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@register("core.sales.quotes.create")
def quotes_create(cliente_id=None, items=None, valid_days=30, token=None, **kwargs):
    """Create a customer quote."""
    if not cliente_id or not items:
        return {"error": "cliente_id and items required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
    
    subtotal = sum(float(i.get("quantity", 1)) * float(i.get("precio_unitario", i.get("price", 0))) for i in items)
    tax = subtotal * 0.16
    total = subtotal + tax
    
    from datetime import timedelta
    valid_until = (datetime.utcnow() + timedelta(days=valid_days)).isoformat()
    
    cursor = db.execute(
        """INSERT INTO quotes (cliente_id, subtotal, tax, total, valid_until, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'draft', ?)""",
        (cliente_id, subtotal, tax, total, valid_until, datetime.utcnow().isoformat())
    )
    
    for item in items:
        db.execute(
            "INSERT INTO quote_items (quote_id, producto_id, quantity, precio_unitario) VALUES (?, ?, ?, ?)",
            (cursor.lastrowid, item.get("producto_id"), item.get("quantity", 1),
             item.get("precio_unitario", item.get("price", 0)))
        )
    
    db.commit()
    return {"id": cursor.lastrowid, "total": total, "valid_until": valid_until}


# --- Sales Summary ---

@register("core.sales.summary")
def sales_summary(period="month", **kwargs):
    """Sales summary for dashboard."""
    db = get_db()
    if period == "month":
        where_clause = "WHERE so.created_at >= date('now', '-30 days')"
    elif period == "week":
        where_clause = "WHERE so.created_at >= date('now', '-7 days')"
    else:
        where_clause = ""
    
    total_sales = db.execute(
        f"SELECT COALESCE(SUM(total), 0) FROM sales_orders so {where_clause} AND so.status = 'invoiced'"
    ).fetchone()[0]
    
    total_orders = db.execute(
        f"SELECT COUNT(*) FROM sales_orders so {where_clause}"
    ).fetchone()[0]
    
    return {
        "total_sales": total_sales,
        "total_orders": total_orders,
        "period": period,
    }
