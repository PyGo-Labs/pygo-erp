"""PyGo ERP — Bill of Materials with multi-level explosion."""
import os
import sys
import json

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


def _parse(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return None
    return x


@register("core.mrp.boms.list")
def boms_list(producto_id=None, **kwargs):
    db = get_db()
    sql = (
        "SELECT b.*, p.nombre AS producto_nombre, p.codigo AS producto_codigo, "
        "r.name AS routing_name FROM boms b "
        "LEFT JOIN productos p ON p.id = b.producto_id "
        "LEFT JOIN routings r ON r.id = b.routing_id WHERE b.is_active = 1"
    )
    params = []
    if producto_id:
        sql += " AND b.producto_id = ?"
        params.append(producto_id)
    sql += " ORDER BY b.id DESC"
    rows = db.execute(sql, params).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        lines = db.execute(
            "SELECT l.*, p.nombre AS component_nombre, p.codigo AS component_codigo, "
            "COALESCE(NULLIF(p.cost,0), p.precio_unitario, 0) AS component_cost FROM bom_lines l "
            "LEFT JOIN productos p ON p.id = l.component_id WHERE l.bom_id = ?",
            (r["id"],),
        ).fetchall()
        d["lines"] = [dict(l) for l in lines]
        out.append(d)
    return out


@register("core.mrp.boms.create")
def boms_create(
    producto_id=None, lines=None, quantity=1, code=None,
    routing_id=None, version="1.0", bom_type="manufacture",
    uom_id=None, company_id=None, **kwargs
):
    """Create a BOM. lines = [{"component_id":2,"quantity":3,"scrap_pct":5}]"""
    if not producto_id:
        return {"error": "producto_id required"}
    lines = _parse(lines)
    if not lines:
        return {"error": "lines required"}

    db = get_db()
    if not db.execute("SELECT 1 FROM productos WHERE id = ?", (producto_id,)).fetchone():
        return {"error": "producto not found"}

    # prevent a component from being the finished product itself
    for l in lines:
        if str(l.get("component_id")) == str(producto_id):
            return {"error": "a product cannot be a component of itself"}

    try:
        cur = db.execute(
            "INSERT INTO boms (code, producto_id, quantity, uom_id, bom_type, routing_id, version, company_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (code, producto_id, float(quantity or 1), uom_id, bom_type, routing_id, version, company_id),
        )
        bom_id = cur.lastrowid
        for l in lines:
            db.execute(
                "INSERT INTO bom_lines (bom_id, component_id, quantity, uom_id, scrap_pct, child_bom_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (bom_id, l.get("component_id"), float(l.get("quantity", 1)),
                 l.get("uom_id"), float(l.get("scrap_pct", 0) or 0), l.get("child_bom_id")),
            )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"bom creation failed: {e}"}
    finally:
        db.close()

    return {"id": bom_id, "producto_id": producto_id, "quantity": quantity, "lines": len(lines)}


def _explode(db, producto_id, qty, level, visited, flat):
    """Recursively explode a BOM. visited guards against circular references."""
    bom = db.execute(
        "SELECT * FROM boms WHERE producto_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
        (producto_id,),
    ).fetchone()
    if not bom:
        return []

    if producto_id in visited:
        return [{"level": level, "error": f"circular BOM reference on producto_id {producto_id}"}]
    visited = visited | {producto_id}

    bom_qty = float(bom["quantity"] or 1) or 1.0
    factor = qty / bom_qty

    tree = []
    lines = db.execute(
        "SELECT l.*, p.nombre AS component_nombre, p.codigo AS component_codigo, "
        "COALESCE(NULLIF(p.cost,0), p.precio_unitario, 0) AS component_cost FROM bom_lines l "
        "LEFT JOIN productos p ON p.id = l.component_id WHERE l.bom_id = ?",
        (bom["id"],),
    ).fetchall()

    for l in lines:
        scrap = float(l["scrap_pct"] or 0)
        needed = float(l["quantity"] or 0) * factor * (1 + scrap / 100)
        cid = l["component_id"]
        node = {
            "level": level,
            "component_id": cid,
            "component_codigo": l["component_codigo"],
            "component_nombre": l["component_nombre"],
            "qty_required": round(needed, 6),
            "scrap_pct": scrap,
            "unit_cost": float(l["component_cost"] or 0),
        }

        children = _explode(db, cid, needed, level + 1, visited, flat)
        if children:
            node["children"] = children
            node["is_subassembly"] = True
        else:
            node["is_subassembly"] = False
            # only leaf components are raw material requirements
            if cid in flat:
                flat[cid]["qty_required"] = round(flat[cid]["qty_required"] + needed, 6)
            else:
                flat[cid] = {
                    "component_id": cid,
                    "component_codigo": l["component_codigo"],
                    "component_nombre": l["component_nombre"],
                    "qty_required": round(needed, 6),
                    "unit_cost": float(l["component_cost"] or 0),
                }
        tree.append(node)
    return tree


@register("core.mrp.boms.explode")
def boms_explode(producto_id=None, quantity=1, **kwargs):
    """Multi-level BOM explosion with a flattened raw-material requirement list."""
    if not producto_id:
        return {"error": "producto_id required"}
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        quantity = 1.0

    db = get_db()
    product = db.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
    if not product:
        return {"error": "producto not found"}

    flat = {}
    tree = _explode(db, producto_id, quantity, 1, frozenset(), flat)
    if not tree:
        return {"error": "no active BOM for this product", "producto_id": producto_id}

    raw = list(flat.values())
    for r in raw:
        r["total_cost"] = round(r["qty_required"] * r["unit_cost"], 2)

    return {
        "producto_id": producto_id,
        "producto": product["nombre"],
        "quantity": quantity,
        "tree": tree,
        "raw_materials": raw,
        "total_material_cost": round(sum(r["total_cost"] for r in raw), 2),
    }


@register("core.mrp.boms.cost")
def boms_cost(producto_id=None, quantity=1, **kwargs):
    """Compute the full manufacturing cost: materials + labor from routing."""
    exploded = boms_explode(producto_id=producto_id, quantity=quantity)
    if exploded.get("error"):
        return exploded

    db = get_db()
    bom = db.execute(
        "SELECT * FROM boms WHERE producto_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
        (producto_id,),
    ).fetchone()

    labor_cost = 0.0
    operations = []
    if bom and bom["routing_id"]:
        ops = db.execute(
            "SELECT o.*, w.name AS work_center_name, w.cost_per_hour, w.efficiency_pct "
            "FROM routing_operations o LEFT JOIN work_centers w ON w.id = o.work_center_id "
            "WHERE o.routing_id = ? ORDER BY o.sequence",
            (bom["routing_id"],),
        ).fetchall()
        qty = float(quantity)
        for o in ops:
            eff = float(o["efficiency_pct"] or 100) / 100 or 1.0
            minutes = (float(o["setup_minutes"] or 0) + float(o["minutes_per_unit"] or 0) * qty) / eff
            cost = minutes / 60 * float(o["cost_per_hour"] or 0)
            labor_cost += cost
            operations.append({
                "sequence": o["sequence"],
                "name": o["name"],
                "work_center": o["work_center_name"],
                "minutes": round(minutes, 2),
                "cost": round(cost, 2),
            })

    material = exploded["total_material_cost"]
    total = material + labor_cost
    return {
        "producto_id": producto_id,
        "producto": exploded["producto"],
        "quantity": quantity,
        "material_cost": material,
        "labor_cost": round(labor_cost, 2),
        "total_cost": round(total, 2),
        "unit_cost": round(total / float(quantity), 4) if float(quantity) else 0,
        "operations": operations,
        "raw_materials": exploded["raw_materials"],
    }
