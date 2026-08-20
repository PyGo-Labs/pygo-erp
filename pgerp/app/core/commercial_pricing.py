"""PyGo ERP — Price lists (universal core)."""
import os
import sys
from datetime import datetime

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


@register("core.pricelists.list")
def pricelists_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM pricelists ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@register("core.pricelists.create")
def pricelists_create(name=None, currency="USD", is_default=0, company_id=None, **kwargs):
    if not name:
        return {"error": "name required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO pricelists (name, currency, is_default, company_id) VALUES (?, ?, ?, ?)",
        (name, currency, int(is_default), company_id),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "currency": currency}


@register("core.pricelists.items.list")
def pricelist_items_list(pricelist_id=None, **kwargs):
    db = get_db()
    if pricelist_id:
        rows = db.execute(
            "SELECT i.*, p.nombre AS producto_nombre FROM pricelist_items i "
            "LEFT JOIN productos p ON p.id = i.producto_id "
            "WHERE i.pricelist_id = ? ORDER BY i.min_qty",
            (pricelist_id,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM pricelist_items ORDER BY pricelist_id").fetchall()
    return [dict(r) for r in rows]


@register("core.pricelists.items.create")
def pricelist_items_create(
    pricelist_id=None, producto_id=None, price=None,
    min_qty=1, discount_pct=0, valid_from=None, valid_to=None, **kwargs
):
    if not pricelist_id or not producto_id:
        return {"error": "pricelist_id and producto_id required"}
    if price is None and not discount_pct:
        return {"error": "price or discount_pct required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO pricelist_items "
        "(pricelist_id, producto_id, price, min_qty, discount_pct, valid_from, valid_to) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pricelist_id, producto_id, price, float(min_qty), float(discount_pct or 0), valid_from, valid_to),
    )
    db.commit()
    return {"id": cur.lastrowid, "pricelist_id": pricelist_id, "producto_id": producto_id}


@register("core.pricelists.resolve")
def pricelists_resolve(producto_id=None, qty=1, pricelist_id=None, cliente_id=None, **kwargs):
    """Resolve the applicable price for a product given qty and pricelist/customer."""
    if not producto_id:
        return {"error": "producto_id required"}
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        qty = 1.0

    db = get_db()
    product = db.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
    if not product:
        return {"error": "product not found"}
    base_price = product["precio_unitario"] or 0

    # Resolve pricelist: explicit > customer's > default
    pl = None
    if pricelist_id:
        pl = db.execute("SELECT * FROM pricelists WHERE id = ?", (pricelist_id,)).fetchone()
    if not pl and cliente_id:
        row = db.execute(
            "SELECT pl.* FROM pricelists pl "
            "JOIN cliente_pricelist cp ON cp.pricelist_id = pl.id "
            "WHERE cp.cliente_id = ?",
            (cliente_id,),
        ).fetchone()
        pl = row
    if not pl:
        pl = db.execute("SELECT * FROM pricelists WHERE is_default = 1").fetchone()

    if not pl:
        return {
            "producto_id": producto_id, "qty": qty, "price": base_price,
            "source": "product_base", "pricelist": None,
        }

    today = datetime.utcnow().strftime("%Y-%m-%d")
    item = db.execute(
        "SELECT * FROM pricelist_items WHERE pricelist_id = ? AND producto_id = ? "
        "AND min_qty <= ? "
        "AND (valid_from IS NULL OR valid_from <= ?) "
        "AND (valid_to IS NULL OR valid_to >= ?) "
        "ORDER BY min_qty DESC LIMIT 1",
        (pl["id"], producto_id, qty, today, today),
    ).fetchone()

    if not item:
        return {
            "producto_id": producto_id, "qty": qty, "price": base_price,
            "source": "product_base", "pricelist": pl["name"],
        }

    if item["price"] is not None:
        final = float(item["price"])
        source = "pricelist_fixed"
    else:
        final = base_price * (1 - float(item["discount_pct"] or 0) / 100)
        source = "pricelist_discount"

    return {
        "producto_id": producto_id,
        "qty": qty,
        "base_price": base_price,
        "price": round(final, 4),
        "source": source,
        "pricelist": pl["name"],
        "currency": pl["currency"],
        "discount_pct": item["discount_pct"],
    }


@register("core.pricelists.assign_customer")
def pricelists_assign_customer(cliente_id=None, pricelist_id=None, **kwargs):
    if not cliente_id or not pricelist_id:
        return {"error": "cliente_id and pricelist_id required"}
    db = get_db()
    db.execute("DELETE FROM cliente_pricelist WHERE cliente_id = ?", (cliente_id,))
    db.execute(
        "INSERT INTO cliente_pricelist (cliente_id, pricelist_id) VALUES (?, ?)",
        (cliente_id, pricelist_id),
    )
    db.commit()
    return {"cliente_id": cliente_id, "pricelist_id": pricelist_id, "assigned": True}


@register("core.pricelists.seed")
def pricelists_seed(**kwargs):
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM pricelists").fetchone()[0] > 0:
        return {"seeded": False, "reason": "already seeded"}
    db.execute(
        "INSERT INTO pricelists (name, currency, is_default) VALUES (?, ?, 1)",
        ("Public Price List", "USD"),
    )
    db.execute(
        "INSERT INTO pricelists (name, currency, is_default) VALUES (?, ?, 0)",
        ("Wholesale", "USD"),
    )
    db.commit()
    return {"seeded": True, "pricelists": 2}
