"""PyGo ERP — Inventory valuation with real cost layers.

Every inbound movement creates a layer at its actual cost. Every outbound
movement consumes layers and records the cost it actually took out, so COGS
stops being an invented number.

Methods:
  fifo     — consume the oldest layers first (default)
  average  — weighted average across remaining layers
  standard — always use productos.cost
"""
import os
import sys
import sqlite3

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register  # noqa: E402

DB_PATH = os.environ.get("PYGO_DB", "/tmp/pgerp.db")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _method_for(db, producto_id):
    row = db.execute(
        "SELECT costing_method, cost, average_cost FROM productos WHERE id = ?",
        (producto_id,)).fetchone()
    if not row:
        return "fifo", 0.0, 0.0
    return (row["costing_method"] or "fifo"), float(row["cost"] or 0), \
        float(row["average_cost"] or 0)


def _recompute_average(db, producto_id):
    """Weighted average over layers that still have stock."""
    row = db.execute(
        "SELECT SUM(remaining) AS qty, SUM(remaining * unit_cost) AS value "
        "FROM stock_layers WHERE producto_id = ? AND remaining > 0",
        (producto_id,)).fetchone()
    qty = float(row["qty"] or 0)
    value = float(row["value"] or 0)
    avg = round(value / qty, 6) if qty > 0 else 0.0
    db.execute("UPDATE productos SET average_cost = ? WHERE id = ?", (avg, producto_id))
    return avg


# ---------------------------------------------------------------- public API

def add_layer(db, producto_id, warehouse_id, quantity, unit_cost,
              source_type=None, source_id=None, currency="USD",
              layer_date=None, company_id=None):
    """Register an inbound cost layer. Returns the layer id."""
    quantity = float(quantity)
    if quantity <= 0:
        raise ValueError("layer quantity must be > 0")
    unit_cost = float(unit_cost or 0)

    cur = db.execute(
        "INSERT INTO stock_layers (producto_id, warehouse_id, quantity, remaining, "
        "unit_cost, currency, source_type, source_id, layer_date, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)",
        (producto_id, warehouse_id, quantity, quantity, unit_cost, currency,
         source_type, source_id, layer_date, company_id),
    )
    layer_id = cur.lastrowid

    db.execute(
        "INSERT INTO stock_valuation_entries (producto_id, warehouse_id, movement_type, "
        "quantity, unit_cost, total_value, method, layer_id, source_type, source_id, "
        "entry_date, company_id) "
        "VALUES (?, ?, 'in', ?, ?, ?, 'layer', ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)",
        (producto_id, warehouse_id, quantity, unit_cost, round(quantity * unit_cost, 6),
         layer_id, source_type, source_id, layer_date, company_id),
    )
    _recompute_average(db, producto_id)
    return layer_id


def consume_layers(db, producto_id, warehouse_id, quantity,
                   source_type=None, source_id=None, company_id=None):
    """Consume `quantity` from cost layers and return the real cost taken out.

    Returns {"quantity", "total_cost", "unit_cost", "method", "consumed": [...]}
    Never raises on insufficient layers: it consumes what exists and falls back
    to the product cost for the remainder, reporting the shortfall.
    """
    quantity = float(quantity)
    if quantity <= 0:
        return {"quantity": 0.0, "total_cost": 0.0, "unit_cost": 0.0,
                "method": "none", "consumed": [], "uncosted_quantity": 0.0}

    method, std_cost, avg_cost = _method_for(db, producto_id)

    if method == "standard":
        total = round(quantity * std_cost, 6)
        db.execute(
            "INSERT INTO stock_valuation_entries (producto_id, warehouse_id, "
            "movement_type, quantity, unit_cost, total_value, method, source_type, "
            "source_id, company_id) VALUES (?, ?, 'out', ?, ?, ?, 'standard', ?, ?, ?)",
            (producto_id, warehouse_id, quantity, std_cost, total,
             source_type, source_id, company_id),
        )
        return {"quantity": quantity, "total_cost": total, "unit_cost": std_cost,
                "method": "standard", "consumed": [], "uncosted_quantity": 0.0}

    # fifo and average both draw down the same layers; average just prices them
    # at the weighted average instead of each layer's own cost.
    order = "layer_date ASC, id ASC"
    layers = db.execute(
        f"SELECT * FROM stock_layers WHERE producto_id = ? AND remaining > 0 "
        f"{'AND warehouse_id = ?' if warehouse_id is not None else ''} "
        f"ORDER BY {order}",
        (producto_id, warehouse_id) if warehouse_id is not None else (producto_id,),
    ).fetchall()

    price_at = avg_cost if method == "average" else None
    remaining_to_take = quantity
    total_cost = 0.0
    consumed = []

    for layer in layers:
        if remaining_to_take <= 0:
            break
        take = min(float(layer["remaining"]), remaining_to_take)
        unit = price_at if price_at is not None else float(layer["unit_cost"])
        cost = round(take * unit, 6)

        db.execute("UPDATE stock_layers SET remaining = remaining - ? WHERE id = ?",
                   (take, layer["id"]))
        db.execute(
            "INSERT INTO stock_valuation_entries (producto_id, warehouse_id, "
            "movement_type, quantity, unit_cost, total_value, method, layer_id, "
            "source_type, source_id, company_id) "
            "VALUES (?, ?, 'out', ?, ?, ?, ?, ?, ?, ?, ?)",
            (producto_id, layer["warehouse_id"], take, unit, cost, method,
             layer["id"], source_type, source_id, company_id),
        )
        consumed.append({"layer_id": layer["id"], "quantity": take, "unit_cost": unit,
                         "cost": cost})
        total_cost += cost
        remaining_to_take -= take

    uncosted = round(remaining_to_take, 6)
    if uncosted > 0:
        # No layer covered this quantity (e.g. stock loaded before valuation
        # existed). Price it at the product cost and say so.
        fallback_unit = std_cost or avg_cost
        cost = round(uncosted * fallback_unit, 6)
        db.execute(
            "INSERT INTO stock_valuation_entries (producto_id, warehouse_id, "
            "movement_type, quantity, unit_cost, total_value, method, source_type, "
            "source_id, company_id) VALUES (?, ?, 'out', ?, ?, ?, 'fallback', ?, ?, ?)",
            (producto_id, warehouse_id, uncosted, fallback_unit, cost,
             source_type, source_id, company_id),
        )
        total_cost += cost

    _recompute_average(db, producto_id)
    total_cost = round(total_cost, 6)
    return {
        "quantity": quantity,
        "total_cost": total_cost,
        "unit_cost": round(total_cost / quantity, 6) if quantity else 0.0,
        "method": method,
        "consumed": consumed,
        "uncosted_quantity": uncosted,
    }


def stock_value(db, producto_id=None, warehouse_id=None):
    """Current inventory value from remaining layers."""
    where, params = ["remaining > 0"], []
    if producto_id:
        where.append("producto_id = ?")
        params.append(producto_id)
    if warehouse_id:
        where.append("warehouse_id = ?")
        params.append(warehouse_id)
    row = db.execute(
        f"SELECT SUM(remaining) AS qty, SUM(remaining * unit_cost) AS value "
        f"FROM stock_layers WHERE {' AND '.join(where)}", params).fetchone()
    return float(row["qty"] or 0), round(float(row["value"] or 0), 6)
