"""PyGo ERP — Work centers, routings and production orders."""
import os
import sys
import json
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


def _parse(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return None
    return x


def _next_folio(doc_type):
    try:
        from core.commercial_terms import sequences_next
        return sequences_next(doc_type=doc_type).get("folio")
    except Exception:
        return None


def _move_stock(db, producto_id, warehouse_id, qty, reason, mtype="adjustment"):
    row = db.execute(
        "SELECT * FROM stock WHERE producto_id = ? AND warehouse_id = ?",
        (producto_id, warehouse_id),
    ).fetchone()
    if row:
        db.execute("UPDATE stock SET quantity = quantity + ? WHERE id = ?", (qty, row["id"]))
    else:
        db.execute(
            "INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
            (producto_id, warehouse_id, qty),
        )
    if qty >= 0:
        db.execute(
            "INSERT INTO stock_movements (producto_id, to_warehouse_id, quantity, type, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (producto_id, warehouse_id, abs(qty), mtype, reason),
        )
    else:
        db.execute(
            "INSERT INTO stock_movements (producto_id, from_warehouse_id, quantity, type, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (producto_id, warehouse_id, abs(qty), mtype, reason),
        )


# --- Work centers ---

@register("core.mrp.work_centers.list")
def work_centers_list(**kwargs):
    db = get_db()
    rows = db.execute(
        "SELECT w.*, c.name AS cost_center_name FROM work_centers w "
        "LEFT JOIN cost_centers c ON c.id = w.cost_center_id "
        "WHERE w.is_active = 1 ORDER BY w.name"
    ).fetchall()
    return [dict(r) for r in rows]


@register("core.mrp.work_centers.create")
def work_centers_create(
    name=None, code=None, capacity_per_hour=1, cost_per_hour=0,
    efficiency_pct=100, cost_center_id=None, company_id=None, **kwargs
):
    if not name:
        return {"error": "name required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO work_centers (code, name, capacity_per_hour, cost_per_hour, efficiency_pct, "
        "cost_center_id, company_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, name, float(capacity_per_hour or 1), float(cost_per_hour or 0),
         float(efficiency_pct or 100), cost_center_id, company_id),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "cost_per_hour": cost_per_hour}


# --- Routings ---

@register("core.mrp.routings.list")
def routings_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM routings WHERE is_active = 1 ORDER BY name").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        ops = db.execute(
            "SELECT o.*, w.name AS work_center_name, w.cost_per_hour FROM routing_operations o "
            "LEFT JOIN work_centers w ON w.id = o.work_center_id "
            "WHERE o.routing_id = ? ORDER BY o.sequence",
            (r["id"],),
        ).fetchall()
        d["operations"] = [dict(o) for o in ops]
        out.append(d)
    return out


@register("core.mrp.routings.create")
def routings_create(name=None, code=None, operations=None, **kwargs):
    """Create a routing. operations = [{"sequence":10,"name":"Cut","work_center_id":1,"minutes_per_unit":5}]"""
    if not name:
        return {"error": "name required"}
    operations = _parse(operations) or []

    db = get_db()
    try:
        cur = db.execute("INSERT INTO routings (code, name) VALUES (?, ?)", (code, name))
        routing_id = cur.lastrowid
        for o in operations:
            db.execute(
                "INSERT INTO routing_operations (routing_id, sequence, name, work_center_id, "
                "setup_minutes, minutes_per_unit) VALUES (?, ?, ?, ?, ?, ?)",
                (routing_id, int(o.get("sequence", 10)), o.get("name"), o.get("work_center_id"),
                 float(o.get("setup_minutes", 0) or 0), float(o.get("minutes_per_unit", 0) or 0)),
            )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"routing creation failed: {e}"}
    finally:
        db.close()
    return {"id": routing_id, "name": name, "operations": len(operations)}


# --- Production orders ---

@register("core.mrp.production.list")
def production_list(status=None, **kwargs):
    db = get_db()
    sql = (
        "SELECT o.*, p.nombre AS producto_nombre, p.codigo AS producto_codigo "
        "FROM production_orders o LEFT JOIN productos p ON p.id = o.producto_id WHERE 1=1"
    )
    params = []
    if status:
        sql += " AND o.status = ?"
        params.append(status)
    sql += " ORDER BY o.id DESC"
    rows = db.execute(sql, params).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        mats = db.execute(
            "SELECT m.*, p.nombre AS component_nombre FROM production_order_materials m "
            "LEFT JOIN productos p ON p.id = m.component_id WHERE m.order_id = ?",
            (r["id"],),
        ).fetchall()
        ops = db.execute(
            "SELECT po.*, w.name AS work_center_name FROM production_order_operations po "
            "LEFT JOIN work_centers w ON w.id = po.work_center_id "
            "WHERE po.order_id = ? ORDER BY po.sequence",
            (r["id"],),
        ).fetchall()
        d["materials"] = [dict(m) for m in mats]
        d["operations"] = [dict(o) for o in ops]
        out.append(d)
    return out


@register("core.mrp.production.create")
def production_create(
    producto_id=None, quantity=1, warehouse_id=None,
    planned_start=None, planned_end=None, cost_center_id=None,
    company_id=None, **kwargs
):
    """Create a production order, exploding the BOM into material requirements."""
    if not producto_id:
        return {"error": "producto_id required"}
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return {"error": "quantity must be numeric"}
    if quantity <= 0:
        return {"error": "quantity must be > 0"}

    from core.mrp_bom import boms_cost
    costing = boms_cost(producto_id=producto_id, quantity=quantity)
    if costing.get("error"):
        return costing

    db = get_db()
    bom = db.execute(
        "SELECT * FROM boms WHERE producto_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
        (producto_id,),
    ).fetchone()

    wh = warehouse_id
    if not wh:
        first = db.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()
        wh = first["id"] if first else None
    if not wh:
        return {"error": "no warehouse available"}

    folio = _next_folio("production_order")
    try:
        cur = db.execute(
            "INSERT INTO production_orders (folio, producto_id, bom_id, quantity, warehouse_id, "
            "status, planned_start, planned_end, material_cost, labor_cost, total_cost, "
            "cost_center_id, company_id) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)",
            (folio, producto_id, bom["id"] if bom else None, quantity, wh,
             planned_start, planned_end, costing["material_cost"], costing["labor_cost"],
             costing["total_cost"], cost_center_id, company_id),
        )
        order_id = cur.lastrowid

        for m in costing["raw_materials"]:
            db.execute(
                "INSERT INTO production_order_materials (order_id, component_id, qty_required, unit_cost) "
                "VALUES (?, ?, ?, ?)",
                (order_id, m["component_id"], m["qty_required"], m["unit_cost"]),
            )
        for o in costing["operations"]:
            db.execute(
                "INSERT INTO production_order_operations (order_id, sequence, name, work_center_id, "
                "planned_minutes) VALUES (?, ?, ?, ?, ?)",
                (order_id, o["sequence"], o["name"], None, o["minutes"]),
            )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"production order failed: {e}"}
    finally:
        db.close()

    return {
        "id": order_id,
        "folio": folio,
        "producto_id": producto_id,
        "quantity": quantity,
        "status": "draft",
        "material_cost": costing["material_cost"],
        "labor_cost": costing["labor_cost"],
        "total_cost": costing["total_cost"],
        "materials": len(costing["raw_materials"]),
        "operations": len(costing["operations"]),
    }


@register("core.mrp.production.check_availability")
def production_check_availability(order_id=None, **kwargs):
    """Check whether all required materials are in stock."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    order = db.execute("SELECT * FROM production_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "production order not found"}

    mats = db.execute(
        "SELECT m.*, p.nombre AS component_nombre FROM production_order_materials m "
        "LEFT JOIN productos p ON p.id = m.component_id WHERE m.order_id = ?",
        (order_id,),
    ).fetchall()

    detail = []
    all_ok = True
    for m in mats:
        available = db.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (m["component_id"], order["warehouse_id"]),
        ).fetchone()[0]
        need = float(m["qty_required"] or 0) - float(m["qty_consumed"] or 0)
        ok = float(available or 0) >= need - 1e-9
        if not ok:
            all_ok = False
        detail.append({
            "component_id": m["component_id"],
            "component": m["component_nombre"],
            "required": need,
            "available": float(available or 0),
            "shortage": round(max(need - float(available or 0), 0), 4),
            "sufficient": ok,
        })

    return {
        "order_id": order_id,
        "folio": order["folio"],
        "can_produce": all_ok,
        "materials": detail,
    }


@register("core.mrp.production.start")
def production_start(order_id=None, **kwargs):
    """Start production: consumes materials from stock."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    order = db.execute("SELECT * FROM production_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "production order not found"}
    if order["status"] != "draft":
        return {"error": f"order is {order['status']}, expected draft"}

    avail = production_check_availability(order_id=order_id)
    if not avail.get("can_produce"):
        return {
            "error": "insufficient materials",
            "shortages": [m for m in avail.get("materials", []) if not m["sufficient"]],
        }

    mats = db.execute(
        "SELECT * FROM production_order_materials WHERE order_id = ?", (order_id,)
    ).fetchall()

    try:
        consumed = 0.0
        for m in mats:
            need = float(m["qty_required"] or 0)
            _move_stock(db, m["component_id"], order["warehouse_id"], -need,
                        f"production {order['folio'] or order_id} consumption", "adjustment")
            db.execute(
                "UPDATE production_order_materials SET qty_consumed = ? WHERE id = ?",
                (need, m["id"]),
            )
            consumed += need * float(m["unit_cost"] or 0)

        db.execute(
            "UPDATE production_orders SET status = 'in_progress', actual_start = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), order_id),
        )
        db.execute(
            "UPDATE production_order_operations SET status = 'in_progress' WHERE order_id = ?",
            (order_id,),
        )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"production start failed: {e}"}
    finally:
        db.close()

    return {
        "order_id": order_id,
        "folio": order["folio"],
        "status": "in_progress",
        "materials_consumed_value": round(consumed, 2),
    }


@register("core.mrp.production.complete")
def production_complete(order_id=None, quantity_produced=None, **kwargs):
    """Complete production: adds finished goods to stock and posts analytic cost."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    order = db.execute("SELECT * FROM production_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "production order not found"}
    if order["status"] != "in_progress":
        return {"error": f"order is {order['status']}, expected in_progress"}

    planned = float(order["quantity"] or 0)
    produced = planned if quantity_produced is None else float(quantity_produced)
    if produced <= 0:
        return {"error": "quantity_produced must be > 0"}
    if produced > planned + 1e-9:
        return {"error": f"quantity_produced {produced} exceeds planned {planned}"}

    try:
        _move_stock(db, order["producto_id"], order["warehouse_id"], produced,
                    f"production {order['folio'] or order_id} output", "adjustment")

        total_cost = float(order["total_cost"] or 0)
        unit_cost = total_cost / planned if planned else 0
        # scale cost when under-produced
        actual_cost = unit_cost * produced

        db.execute(
            "UPDATE production_orders SET status = 'done', quantity_produced = ?, actual_end = ?, "
            "total_cost = ? WHERE id = ?",
            (produced, datetime.utcnow().isoformat(), round(actual_cost, 2), order_id),
        )
        db.execute(
            "UPDATE production_order_operations SET status = 'done' WHERE order_id = ?",
            (order_id,),
        )
        if order["cost_center_id"]:
            db.execute(
                "INSERT INTO analytic_lines (cost_center_id, amount, entry_date, description) "
                "VALUES (?, ?, ?, ?)",
                (order["cost_center_id"], round(actual_cost, 2),
                 datetime.utcnow().strftime("%Y-%m-%d"),
                 f"Production {order['folio'] or order_id}"),
            )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"production completion failed: {e}"}
    finally:
        db.close()

    return {
        "order_id": order_id,
        "folio": order["folio"],
        "status": "done",
        "quantity_planned": planned,
        "quantity_produced": produced,
        "yield_pct": round(produced / planned * 100, 1) if planned else 0,
        "total_cost": round(actual_cost, 2),
        "unit_cost": round(actual_cost / produced, 4) if produced else 0,
    }


@register("core.mrp.production.cancel")
def production_cancel(order_id=None, **kwargs):
    """Cancel a production order, returning consumed materials to stock."""
    if not order_id:
        return {"error": "order_id required"}
    db = get_db()
    order = db.execute("SELECT * FROM production_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "production order not found"}
    if order["status"] in ("done", "cancelled"):
        return {"error": f"order is {order['status']}"}

    try:
        returned = 0
        if order["status"] == "in_progress":
            mats = db.execute(
                "SELECT * FROM production_order_materials WHERE order_id = ? AND qty_consumed > 0",
                (order_id,),
            ).fetchall()
            for m in mats:
                qty = float(m["qty_consumed"] or 0)
                _move_stock(db, m["component_id"], order["warehouse_id"], qty,
                            f"production {order['folio'] or order_id} cancelled - return", "adjustment")
                db.execute("UPDATE production_order_materials SET qty_consumed = 0 WHERE id = ?", (m["id"],))
                returned += 1
        db.execute("UPDATE production_orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"cancellation failed: {e}"}
    finally:
        db.close()

    return {"order_id": order_id, "status": "cancelled", "materials_returned": returned}


@register("core.mrp.dashboard")
def mrp_dashboard(**kwargs):
    db = get_db()
    counts = {}
    for st in ("draft", "in_progress", "done", "cancelled"):
        counts[st] = db.execute(
            "SELECT COUNT(*) FROM production_orders WHERE status = ?", (st,)
        ).fetchone()[0]
    produced = db.execute(
        "SELECT COALESCE(SUM(quantity_produced),0), COALESCE(SUM(total_cost),0) "
        "FROM production_orders WHERE status = 'done'"
    ).fetchone()
    wc = db.execute("SELECT COUNT(*) FROM work_centers WHERE is_active = 1").fetchone()[0]
    boms = db.execute("SELECT COUNT(*) FROM boms WHERE is_active = 1").fetchone()[0]
    return {
        "orders_by_status": counts,
        "total_produced_qty": float(produced[0] or 0),
        "total_production_cost": round(float(produced[1] or 0), 2),
        "active_work_centers": wc,
        "active_boms": boms,
    }
