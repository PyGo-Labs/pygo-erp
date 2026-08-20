"""PyGo ERP — Valuation handlers exposed over the API."""
import os
import sys

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register  # noqa: E402
from core.valuation import (get_db, add_layer, consume_layers,  # noqa: E402
                            stock_value, _recompute_average)


@register("core.valuation.layers")
def valuation_layers(producto_id=None, warehouse_id=None, only_open=1, **kwargs):
    """Cost layers, newest first. only_open hides fully consumed ones."""
    db = get_db()
    where, params = [], []
    if producto_id:
        where.append("l.producto_id = ?")
        params.append(producto_id)
    if warehouse_id:
        where.append("l.warehouse_id = ?")
        params.append(warehouse_id)
    if int(only_open or 0):
        where.append("l.remaining > 0")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(
        f"SELECT l.*, p.codigo AS producto_codigo, p.nombre AS producto_nombre, "
        f"w.name AS warehouse_name FROM stock_layers l "
        f"JOIN productos p ON p.id = l.producto_id "
        f"LEFT JOIN warehouses w ON w.id = l.warehouse_id "
        f"{clause} ORDER BY l.layer_date DESC, l.id DESC LIMIT 200", params).fetchall()
    out = [dict(r) for r in rows]
    db.close()
    return out


@register("core.valuation.add_layer")
def valuation_add_layer(producto_id=None, warehouse_id=None, quantity=None,
                        unit_cost=None, source_type="manual", source_id=None,
                        currency="USD", company_id=None, **kwargs):
    """Register an inbound cost layer manually (opening balances, corrections)."""
    if not producto_id or not warehouse_id or quantity is None:
        return {"error": "producto_id, warehouse_id and quantity required"}
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        return {"error": "quantity must be numeric"}
    if qty <= 0:
        return {"error": "quantity must be > 0"}

    db = get_db()
    try:
        layer_id = add_layer(db, producto_id, warehouse_id, qty, unit_cost or 0,
                             source_type=source_type, source_id=source_id,
                             currency=currency, company_id=company_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        db.close()
        return {"error": str(exc)}
    avg = db.execute("SELECT average_cost FROM productos WHERE id = ?",
                     (producto_id,)).fetchone()["average_cost"]
    db.close()
    return {"layer_id": layer_id, "producto_id": producto_id, "quantity": qty,
            "unit_cost": float(unit_cost or 0), "average_cost": float(avg or 0)}


@register("core.valuation.consume")
def valuation_consume(producto_id=None, warehouse_id=None, quantity=None,
                      source_type="manual", source_id=None, company_id=None, **kwargs):
    """Consume layers and return the real cost taken out (used by sales/MRP)."""
    if not producto_id or quantity is None:
        return {"error": "producto_id and quantity required"}
    db = get_db()
    try:
        result = consume_layers(db, producto_id, warehouse_id, quantity,
                                source_type=source_type, source_id=source_id,
                                company_id=company_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        db.close()
        return {"error": str(exc)}
    db.close()
    return result


@register("core.valuation.stock_value")
def valuation_stock_value(producto_id=None, warehouse_id=None, **kwargs):
    """Inventory value from remaining layers, plus a per-product breakdown."""
    db = get_db()
    qty, value = stock_value(db, producto_id, warehouse_id)

    rows = db.execute(
        "SELECT l.producto_id, p.codigo, p.nombre, p.costing_method, "
        "SUM(l.remaining) AS qty, SUM(l.remaining * l.unit_cost) AS value "
        "FROM stock_layers l JOIN productos p ON p.id = l.producto_id "
        "WHERE l.remaining > 0 "
        + ("AND l.producto_id = ? " if producto_id else "")
        + ("AND l.warehouse_id = ? " if warehouse_id else "")
        + "GROUP BY l.producto_id ORDER BY value DESC",
        tuple(x for x in (producto_id, warehouse_id) if x)).fetchall()

    by_product = [{
        "producto_id": r["producto_id"],
        "codigo": r["codigo"],
        "nombre": r["nombre"],
        "costing_method": r["costing_method"] or "fifo",
        "quantity": round(float(r["qty"] or 0), 6),
        "value": round(float(r["value"] or 0), 2),
        "unit_cost": round(float(r["value"] or 0) / float(r["qty"]), 6)
                     if float(r["qty"] or 0) else 0.0,
    } for r in rows]
    db.close()
    return {"total_quantity": round(qty, 6), "total_value": round(value, 2),
            "by_product": by_product}


@register("core.valuation.cogs")
def valuation_cogs(date_from=None, date_to=None, producto_id=None, **kwargs):
    """Cost of goods sold from real outbound valuation entries."""
    db = get_db()
    where = ["movement_type = 'out'"]
    params = []
    if date_from:
        where.append("entry_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("entry_date <= ?")
        params.append(date_to + " 23:59:59")
    if producto_id:
        where.append("producto_id = ?")
        params.append(producto_id)
    clause = " AND ".join(where)

    total = db.execute(
        f"SELECT SUM(quantity) AS qty, SUM(total_value) AS value "
        f"FROM stock_valuation_entries WHERE {clause}", params).fetchone()

    rows = db.execute(
        f"SELECT v.producto_id, p.codigo, p.nombre, SUM(v.quantity) AS qty, "
        f"SUM(v.total_value) AS value FROM stock_valuation_entries v "
        f"JOIN productos p ON p.id = v.producto_id WHERE {clause} "
        f"GROUP BY v.producto_id ORDER BY value DESC", params).fetchall()

    fallback = db.execute(
        f"SELECT SUM(quantity) AS qty FROM stock_valuation_entries "
        f"WHERE {clause} AND method = 'fallback'", params).fetchone()

    db.close()
    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_quantity": round(float(total["qty"] or 0), 6),
        "total_cogs": round(float(total["value"] or 0), 2),
        "by_product": [{
            "producto_id": r["producto_id"], "codigo": r["codigo"],
            "nombre": r["nombre"],
            "quantity": round(float(r["qty"] or 0), 6),
            "cogs": round(float(r["value"] or 0), 2),
        } for r in rows],
        "uncosted_quantity": round(float(fallback["qty"] or 0), 6),
        "note": "uncosted_quantity was priced from productos.cost because no "
                "layer covered it",
    }


@register("core.valuation.set_method")
def valuation_set_method(producto_id=None, method=None, **kwargs):
    """Change the costing method of a product."""
    allowed = ("fifo", "average", "standard")
    if not producto_id or not method:
        return {"error": "producto_id and method required"}
    if method not in allowed:
        return {"error": "unsupported method", "allowed": list(allowed)}

    db = get_db()
    if not db.execute("SELECT 1 FROM productos WHERE id = ?", (producto_id,)).fetchone():
        db.close()
        return {"error": "product not found"}
    db.execute("UPDATE productos SET costing_method = ? WHERE id = ?",
               (method, producto_id))
    avg = _recompute_average(db, producto_id)
    db.commit()
    db.close()
    return {"producto_id": producto_id, "costing_method": method, "average_cost": avg}
