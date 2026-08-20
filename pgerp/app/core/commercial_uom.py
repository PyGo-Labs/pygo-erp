"""PyGo ERP — Units of Measure (universal core)."""
import os
import sys

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


def get_db():
    import sqlite3
    conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"))
    conn.row_factory = sqlite3.Row
    return conn


@register("core.uom.categories.list")
def uom_categories_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM uom_categories ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@register("core.uom.categories.create")
def uom_categories_create(name=None, **kwargs):
    if not name:
        return {"error": "name required"}
    db = get_db()
    cur = db.execute("INSERT INTO uom_categories (name) VALUES (?)", (name,))
    db.commit()
    return {"id": cur.lastrowid, "name": name}


@register("core.uom.list")
def uom_list(category_id=None, **kwargs):
    db = get_db()
    if category_id:
        rows = db.execute(
            "SELECT u.*, c.name AS category_name FROM uom u "
            "LEFT JOIN uom_categories c ON c.id = u.category_id "
            "WHERE u.category_id = ? ORDER BY u.name",
            (category_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT u.*, c.name AS category_name FROM uom u "
            "LEFT JOIN uom_categories c ON c.id = u.category_id ORDER BY u.name"
        ).fetchall()
    return [dict(r) for r in rows]


@register("core.uom.create")
def uom_create(name=None, code=None, category_id=None, ratio=1.0, uom_type="reference", **kwargs):
    if not name or not code:
        return {"error": "name and code required"}
    try:
        ratio = float(ratio)
    except (TypeError, ValueError):
        return {"error": "ratio must be numeric"}
    if ratio <= 0:
        return {"error": "ratio must be > 0"}
    if uom_type not in ("reference", "bigger", "smaller"):
        return {"error": "uom_type must be reference|bigger|smaller"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO uom (name, code, category_id, ratio, uom_type) VALUES (?, ?, ?, ?, ?)",
        (name, code, category_id, ratio, uom_type),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "code": code, "ratio": ratio, "uom_type": uom_type}


@register("core.uom.convert")
def uom_convert(qty=None, from_uom=None, to_uom=None, **kwargs):
    """Convert a quantity between two UoM of the same category."""
    if qty is None or not from_uom or not to_uom:
        return {"error": "qty, from_uom and to_uom required"}
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        return {"error": "qty must be numeric"}

    db = get_db()
    src = db.execute("SELECT * FROM uom WHERE id = ? OR code = ?", (from_uom, from_uom)).fetchone()
    dst = db.execute("SELECT * FROM uom WHERE id = ? OR code = ?", (to_uom, to_uom)).fetchone()
    if not src or not dst:
        return {"error": "uom not found"}
    if src["category_id"] != dst["category_id"]:
        return {"error": "cannot convert between different categories"}

    # ratio is relative to the category reference unit
    base_qty = qty * src["ratio"]
    result = base_qty / dst["ratio"]
    return {
        "qty": qty,
        "from": src["code"],
        "to": dst["code"],
        "result": round(result, 6),
    }


@register("core.uom.seed")
def uom_seed(**kwargs):
    """Seed international UoM categories and units."""
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM uom_categories").fetchone()[0] > 0:
        return {"seeded": False, "reason": "already seeded"}

    cats = {}
    for name in ("Unit", "Weight", "Volume", "Length", "Time"):
        cur = db.execute("INSERT INTO uom_categories (name) VALUES (?)", (name,))
        cats[name] = cur.lastrowid

    units = [
        ("Unit", "Unit", "unit", 1.0, "reference"),
        ("Unit", "Dozen", "dozen", 12.0, "bigger"),
        ("Unit", "Box 100", "box100", 100.0, "bigger"),
        ("Weight", "Kilogram", "kg", 1.0, "reference"),
        ("Weight", "Gram", "g", 0.001, "smaller"),
        ("Weight", "Tonne", "t", 1000.0, "bigger"),
        ("Weight", "Pound", "lb", 0.453592, "smaller"),
        ("Volume", "Liter", "L", 1.0, "reference"),
        ("Volume", "Milliliter", "mL", 0.001, "smaller"),
        ("Volume", "Cubic meter", "m3", 1000.0, "bigger"),
        ("Volume", "Gallon US", "gal", 3.78541, "bigger"),
        ("Length", "Meter", "m", 1.0, "reference"),
        ("Length", "Centimeter", "cm", 0.01, "smaller"),
        ("Length", "Kilometer", "km", 1000.0, "bigger"),
        ("Length", "Inch", "in", 0.0254, "smaller"),
        ("Time", "Hour", "h", 1.0, "reference"),
        ("Time", "Minute", "min", 0.016667, "smaller"),
        ("Time", "Day 8h", "day8", 8.0, "bigger"),
    ]
    for cat, name, code, ratio, utype in units:
        db.execute(
            "INSERT INTO uom (name, code, category_id, ratio, uom_type) VALUES (?, ?, ?, ?, ?)",
            (name, code, cats[cat], ratio, utype),
        )
    db.commit()
    return {"seeded": True, "categories": len(cats), "units": len(units)}
