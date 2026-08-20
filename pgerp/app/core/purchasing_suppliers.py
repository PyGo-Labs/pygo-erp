"""PyGo ERP — Suppliers and price agreements (universal core)."""
import os
import sys
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


@register("core.suppliers.list")
def suppliers_list(company_id=None, **kwargs):
    db = get_db()
    if company_id:
        rows = db.execute(
            "SELECT * FROM suppliers WHERE company_id = ? AND is_active = 1 ORDER BY name",
            (company_id,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM suppliers WHERE is_active = 1 ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@register("core.suppliers.create")
def suppliers_create(
    name=None, tax_id=None, email=None, phone=None, address=None,
    country=None, currency="USD", payment_term_id=None,
    lead_time_days=0, company_id=None, **kwargs
):
    if not name:
        return {"error": "name required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO suppliers (name, tax_id, email, phone, address, country, currency, "
        "payment_term_id, lead_time_days, company_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, tax_id, email, phone, address, country, currency,
         payment_term_id, int(lead_time_days or 0), company_id),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "currency": currency}


@register("core.suppliers.update")
def suppliers_update(id=None, **kwargs):
    if not id:
        return {"error": "id required"}
    allowed = ["name", "tax_id", "email", "phone", "address", "country",
               "currency", "payment_term_id", "lead_time_days", "is_active"]
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return {"error": "no valid fields"}
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE suppliers SET {sets} WHERE id = ?", list(fields.values()) + [id])
    db.commit()
    row = db.execute("SELECT * FROM suppliers WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else {"error": "not found"}


@register("core.suppliers.delete")
def suppliers_delete(id=None, **kwargs):
    if not id:
        return {"error": "id required"}
    db = get_db()
    db.execute("UPDATE suppliers SET is_active = 0 WHERE id = ?", (id,))
    db.commit()
    return {"deleted": True, "id": id}


@register("core.suppliers.agreements.list")
def agreements_list(supplier_id=None, producto_id=None, **kwargs):
    db = get_db()
    sql = (
        "SELECT a.*, s.name AS supplier_name, p.nombre AS producto_nombre "
        "FROM supplier_price_agreements a "
        "LEFT JOIN suppliers s ON s.id = a.supplier_id "
        "LEFT JOIN productos p ON p.id = a.producto_id WHERE 1=1"
    )
    params = []
    if supplier_id:
        sql += " AND a.supplier_id = ?"
        params.append(supplier_id)
    if producto_id:
        sql += " AND a.producto_id = ?"
        params.append(producto_id)
    sql += " ORDER BY a.price"
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@register("core.suppliers.agreements.create")
def agreements_create(
    supplier_id=None, producto_id=None, price=None, currency="USD",
    min_qty=1, lead_time_days=0, valid_from=None, valid_to=None, **kwargs
):
    if not supplier_id or not producto_id or price is None:
        return {"error": "supplier_id, producto_id and price required"}
    try:
        price = float(price)
    except (TypeError, ValueError):
        return {"error": "price must be numeric"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO supplier_price_agreements "
        "(supplier_id, producto_id, price, currency, min_qty, lead_time_days, valid_from, valid_to) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (supplier_id, producto_id, price, currency, float(min_qty),
         int(lead_time_days or 0), valid_from, valid_to),
    )
    db.commit()
    return {"id": cur.lastrowid, "supplier_id": supplier_id, "producto_id": producto_id, "price": price}


@register("core.suppliers.best_price")
def suppliers_best_price(producto_id=None, qty=1, **kwargs):
    """Find the best supplier price for a product at a given qty."""
    if not producto_id:
        return {"error": "producto_id required"}
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        qty = 1.0

    db = get_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT a.*, s.name AS supplier_name FROM supplier_price_agreements a "
        "JOIN suppliers s ON s.id = a.supplier_id "
        "WHERE a.producto_id = ? AND a.min_qty <= ? AND s.is_active = 1 "
        "AND (a.valid_from IS NULL OR a.valid_from <= ?) "
        "AND (a.valid_to IS NULL OR a.valid_to >= ?) "
        "ORDER BY a.price ASC",
        (producto_id, qty, today, today),
    ).fetchall()

    if not rows:
        return {"producto_id": producto_id, "qty": qty, "best": None, "options": []}

    options = [
        {
            "supplier_id": r["supplier_id"],
            "supplier_name": r["supplier_name"],
            "price": r["price"],
            "currency": r["currency"],
            "lead_time_days": r["lead_time_days"],
            "total": round(r["price"] * qty, 2),
        }
        for r in rows
    ]
    return {"producto_id": producto_id, "qty": qty, "best": options[0], "options": options}
