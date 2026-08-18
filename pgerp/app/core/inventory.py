"""PyGo ERP V2.0 — Inventory module.

Provides:
- Warehouse management (multiple locations)
- Stock tracking (per product per warehouse)
- Stock transfers between warehouses
- Stock adjustments (inventory counts)
- Product categories
- Stock alerts (below minimum)
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


# --- Warehouse CRUD ---

@register("core.inventory.warehouses.list")
def warehouses_list(**kwargs):
    """List all warehouses."""
    db = get_db()
    rows = db.execute("SELECT * FROM warehouses").fetchall()
    return [dict(r) for r in rows]


@register("core.inventory.warehouses.create")
def warehouses_create(name=None, code=None, location=None, token=None, **kwargs):
    """Create a warehouse (admin/manager)."""
    if not name:
        return {"error": "name required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    if not code:
        code = name.upper()[:3] + str(int(datetime.utcnow().timestamp()))[-4:]
    
    cursor = db.execute(
        "INSERT INTO warehouses (name, code, location, company_id) VALUES (?, ?, ?, ?)",
        (name, code, location, user.company_id if token else None)
    )
    db.commit()
    
    row = db.execute("SELECT * FROM warehouses WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@register("core.inventory.warehouses.update")
def warehouses_update(warehouse_id=None, token=None, **kwargs):
    """Update a warehouse."""
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
    
    row = db.execute("SELECT * FROM warehouses WHERE id = ?", (warehouse_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    
    allowed = ["name", "code", "location", "is_active"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [warehouse_id]
        db.execute(f"UPDATE warehouses SET {sets} WHERE id = ?", vals)
        db.commit()
    
    return dict(db.execute("SELECT * FROM warehouses WHERE id = ?", (warehouse_id,)).fetchone())


@register("core.inventory.warehouses.delete")
def warehouses_delete(warehouse_id=None, token=None):
    """Delete a warehouse (admin only)."""
    if not warehouse_id:
        return {"error": "warehouse_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role != "admin":
            return {"error": "admin only"}
    
    # Check no stock exists
    stock_count = db.execute("SELECT COUNT(*) FROM stock WHERE warehouse_id = ?", (warehouse_id,)).fetchone()[0]
    if stock_count > 0:
        return {"error": "warehouse has stock, transfer first"}
    
    db.execute("DELETE FROM warehouses WHERE id = ?", (warehouse_id,))
    db.commit()
    return {"deleted": True, "warehouse_id": warehouse_id}


# --- Stock operations ---

@register("core.inventory.stock.list")
def stock_list(product_id=None, warehouse_id=None, **kwargs):
    """List stock levels (optionally filtered)."""
    db = get_db()
    query = """
        SELECT s.*, p.nombre as producto_nombre, p.codigo as producto_codigo,
               w.name as warehouse_name, w.code as warehouse_code
        FROM stock s
        JOIN productos p ON s.producto_id = p.id
        JOIN warehouses w ON s.warehouse_id = w.id
    """
    filters = []
    params = []
    
    if product_id:
        filters.append("s.producto_id = ?")
        params.append(product_id)
    if warehouse_id:
        filters.append("s.warehouse_id = ?")
        params.append(warehouse_id)
    
    if filters:
        query += " WHERE " + " AND ".join(filters)
    
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.inventory.stock.transfer")
def stock_transfer(product_id=None, from_warehouse=None, to_warehouse=None, quantity=None, token=None, **kwargs):
    """Transfer stock between warehouses."""
    if not all([product_id, from_warehouse, to_warehouse, quantity]):
        return {"error": "product_id, from_warehouse, to_warehouse, quantity required"}
    
    try:
        qty = float(quantity)
    except ValueError:
        return {"error": "invalid quantity"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    # Get source stock
    source = db.execute(
        "SELECT * FROM stock WHERE producto_id = ? AND warehouse_id = ?",
        (product_id, from_warehouse)
    ).fetchone()
    
    if not source or source["quantity"] < qty:
        return {"error": "insufficient stock"}
    
    # Update source
    db.execute(
        "UPDATE stock SET quantity = quantity - ? WHERE producto_id = ? AND warehouse_id = ?",
        (qty, product_id, from_warehouse)
    )
    
    # Update destination (insert if not exists)
    dest = db.execute(
        "SELECT * FROM stock WHERE producto_id = ? AND warehouse_id = ?",
        (product_id, to_warehouse)
    ).fetchone()
    
    if dest:
        db.execute(
            "UPDATE stock SET quantity = quantity + ? WHERE producto_id = ? AND warehouse_id = ?",
            (qty, product_id, to_warehouse)
        )
    else:
        db.execute(
            "INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
            (product_id, to_warehouse, qty)
        )
    
    # Log movement
    db.execute(
        "INSERT INTO stock_movements (producto_id, from_warehouse_id, to_warehouse_id, quantity, user_id, type) VALUES (?, ?, ?, ?, ?, 'transfer')",
        (product_id, from_warehouse, to_warehouse, qty, user.id if token else None)
    )
    db.commit()
    
    return {"transferred": True, "quantity": qty}


@register("core.inventory.stock.adjust")
def stock_adjust(product_id=None, warehouse_id=None, new_quantity=None, reason=None, token=None, **kwargs):
    """Adjust stock level (inventory count)."""
    if not all([product_id, warehouse_id, new_quantity is not None]):
        return {"error": "product_id, warehouse_id, new_quantity required"}
    
    try:
        qty = float(new_quantity)
    except ValueError:
        return {"error": "invalid quantity"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    # Get current
    current = db.execute(
        "SELECT * FROM stock WHERE producto_id = ? AND warehouse_id = ?",
        (product_id, warehouse_id)
    ).fetchone()
    
    diff = qty - (current["quantity"] if current else 0)
    
    if current:
        db.execute(
            "UPDATE stock SET quantity = ? WHERE producto_id = ? AND warehouse_id = ?",
            (qty, product_id, warehouse_id)
        )
    else:
        db.execute(
            "INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
            (product_id, warehouse_id, qty)
        )
    
    # Log movement
    db.execute(
        "INSERT INTO stock_movements (producto_id, from_warehouse_id, to_warehouse_id, quantity, user_id, type, reason) VALUES (?, NULL, ?, ?, ?, 'adjustment', ?)",
        (product_id, warehouse_id, diff, user.id if token else None, reason)
    )
    db.commit()
    
    return {"adjusted": True, "previous": current["quantity"] if current else 0, "new": qty}


@register("core.inventory.stock.movements")
def stock_movements(product_id=None, **kwargs):
    """List stock movements (history)."""
    db = get_db()
    query = """
        SELECT sm.*, p.nombre as producto_nombre,
               fw.name as from_warehouse_name, tw.name as to_warehouse_name
        FROM stock_movements sm
        JOIN productos p ON sm.producto_id = p.id
        LEFT JOIN warehouses fw ON sm.from_warehouse_id = fw.id
        LEFT JOIN warehouses tw ON sm.to_warehouse_id = tw.id
    """
    params = []
    
    if product_id:
        query += " WHERE sm.producto_id = ?"
        params.append(product_id)
    
    query += " ORDER BY sm.created_at DESC LIMIT 100"
    
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.inventory.stock.alerts")
def stock_alerts(**kwargs):
    """Products below minimum stock."""
    db = get_db()
    rows = db.execute("""
        SELECT p.*, s.quantity, p.stock_minimo
        FROM productos p
        LEFT JOIN stock s ON s.producto_id = p.id
        WHERE p.stock_minimo IS NOT NULL AND COALESCE(s.quantity, 0) < p.stock_minimo
    """).fetchall()
    return [dict(r) for r in rows]


@register("core.inventory.categories.list")
def categories_list(**kwargs):
    """List product categories."""
    db = get_db()
    rows = db.execute("SELECT * FROM categorias").fetchall()
    return [dict(r) for r in rows]


@register("core.inventory.categories.create")
def categories_create(name=None, parent_id=None, token=None, **kwargs):
    """Create a category (admin/manager)."""
    if not name:
        return {"error": "name required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    cursor = db.execute("INSERT INTO categorias (name, parent_id) VALUES (?, ?)", (name, parent_id))
    db.commit()
    
    return {"id": cursor.lastrowid, "name": name, "parent_id": parent_id}
