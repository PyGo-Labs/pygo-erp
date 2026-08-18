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
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    
    # Calculate totals
    subtotal = 0
    for item in items:
        qty = float(item.get("quantity", 1))
        price = float(item.get("precio_unitario", item.get("price", 0)))
        discount = float(item.get("discount", 0))
        item_total = qty * price * (1 - discount / 100)
        subtotal += item_total
    
    tax_rate = float(kwargs.get("tax_rate", 16))
    tax = subtotal * tax_rate / 100
    total = subtotal + tax
    
    cursor = db.execute(
        """INSERT INTO sales_orders (cliente_id, status, subtotal, tax, total, notes, user_id, created_at)
           VALUES (?, 'draft', ?, ?, ?, ?, ?, ?)""",
        (cliente_id, subtotal, tax, total, notes, user_id, datetime.utcnow().isoformat())
    )
    order_id = cursor.lastrowid
    
    # Insert line items
    for item in items:
        db.execute(
            """INSERT INTO sales_order_items (order_id, producto_id, quantity, precio_unitario, discount)
               VALUES (?, ?, ?, ?, ?)""",
            (order_id, item.get("producto_id"), item.get("quantity", 1),
             item.get("precio_unitario", item.get("price", 0)), item.get("discount", 0))
        )
    
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
    return {"confirmed": True, "order_id": order_id}


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
    
    db.execute("UPDATE sales_orders SET status = 'delivered' WHERE id = ?", (order_id,))
    db.commit()
    
    return {"delivered": True, "order_id": order_id}


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
