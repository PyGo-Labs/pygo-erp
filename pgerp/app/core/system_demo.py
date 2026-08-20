"""PyGo ERP — Optional demo data and system readiness report."""
import os
import sys
from datetime import datetime, timedelta

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


@register("core.system.readiness")
def system_readiness(**kwargs):
    """Is this installation actually usable? Reports per-area readiness."""
    db = get_db()

    def count(table, where=""):
        try:
            sql = f"SELECT COUNT(*) FROM {table}"
            if where:
                sql += f" WHERE {where}"
            return db.execute(sql).fetchone()[0]
        except Exception:
            return -1

    areas = {
        "identity": {
            "companies": count("companies"),
            "users": count("users"),
            "ready": count("companies") > 0 and count("users") > 0,
        },
        "accounting": {
            "accounts": count("accounts"),
            "taxes": count("taxes", "is_active = 1"),
            "cost_centers": count("cost_centers"),
            "ready": count("accounts") > 0 and count("taxes", "is_active = 1") > 0,
        },
        "commercial": {
            "pricelists": count("pricelists"),
            "payment_terms": count("payment_terms"),
            "sequences": count("sequences"),
            "uom": count("uom"),
            "ready": count("sequences") > 0 and count("uom") > 0,
        },
        "inventory": {
            "warehouses": count("warehouses"),
            "products": count("productos"),
            "ready": count("warehouses") > 0,
        },
        "hr": {
            "employees": count("employees", "status = 'active'"),
            "leave_types": count("leave_types"),
            "ready": count("leave_types") > 0,
        },
        "manufacturing": {
            "boms": count("boms", "is_active = 1"),
            "work_centers": count("work_centers", "is_active = 1"),
            "ready": True,  # optional area
        },
        "extensibility": {
            "modules_available": count("modules"),
            "modules_installed": count("modules", "state = 'installed'"),
            "hooks_active": count("module_hooks", "is_active = 1"),
            "ready": True,
        },
        "governance": {
            "audit_entries": count("audit_log"),
            "attachments": count("attachments"),
            "ready": True,
        },
    }

    blocking = [name for name, a in areas.items() if not a.get("ready")]
    return {
        "areas": areas,
        "operational": len(blocking) == 0,
        "blocking_areas": blocking,
        "checked_at": datetime.utcnow().isoformat(),
    }


@register("core.demo.load")
def demo_load(confirm=None, **kwargs):
    """Load a small, coherent demo dataset so the ERP can be explored immediately."""
    if str(confirm) != "yes":
        return {
            "error": "pass confirm=yes to load demo data",
            "warning": "demo data is for evaluation only; do not load in production",
        }

    db = get_db()
    created = {}

    try:
        # Customers
        if db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 0:
            for name, email in [
                ("Northwind Trading", "ops@northwind.example"),
                ("Baltic Retail Group", "purchasing@baltic.example"),
                ("Andes Logistics", "contact@andes.example"),
            ]:
                db.execute("INSERT INTO clientes (nombre, email) VALUES (?, ?)", (name, email))
            created["clientes"] = 3

        # Products
        if db.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
            for code, name, price, cost in [
                ("DEMO-LAP", "Laptop 14in", 1200, 850),
                ("DEMO-MON", "Monitor 27in", 320, 210),
                ("DEMO-KEY", "Mechanical Keyboard", 95, 55),
                ("DEMO-DOCK", "USB-C Dock", 180, 120),
            ]:
                db.execute(
                    "INSERT INTO productos (codigo, nombre, precio_unitario, cost, stock_minimo) "
                    "VALUES (?, ?, ?, ?, 5)",
                    (code, name, price, cost),
                )
            created["productos"] = 4

        # Warehouse
        if db.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0] == 0:
            db.execute("INSERT INTO warehouses (name, code) VALUES ('Demo Warehouse', 'DEMO')")
            created["warehouses"] = 1

        wh = db.execute("SELECT id FROM warehouses ORDER BY id LIMIT 1").fetchone()
        wh_id = wh["id"] if wh else None

        # Opening stock
        if wh_id and db.execute("SELECT COUNT(*) FROM stock").fetchone()[0] == 0:
            for p in db.execute("SELECT id FROM productos").fetchall():
                db.execute(
                    "INSERT INTO stock (producto_id, warehouse_id, quantity) VALUES (?, ?, ?)",
                    (p["id"], wh_id, 25),
                )
            created["stock_lines"] = db.execute("SELECT COUNT(*) FROM stock").fetchone()[0]

        # Suppliers
        if db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0:
            for name, country, lead in [
                ("Shenzhen Components Ltd", "CN", 21),
                ("EuroParts GmbH", "DE", 9),
            ]:
                db.execute(
                    "INSERT INTO suppliers (name, country, lead_time_days) VALUES (?, ?, ?)",
                    (name, country, lead),
                )
            created["suppliers"] = 2

        # Leads (schema uses `status`, not `stage`)
        if db.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 0:
            for name, company, email in [
                ("Marta Ruiz", "Helio Systems", "marta@helio.example"),
                ("Tom Becker", "Becker Industrial", "tom@becker.example"),
            ]:
                db.execute(
                    "INSERT INTO leads (name, company, email, status, source) "
                    "VALUES (?, ?, ?, 'new', 'demo')",
                    (name, company, email),
                )
            created["leads"] = 2

        db.commit()
    except Exception as e:
        # Keep whatever succeeded: partial demo data is still useful and the
        # caller is told exactly which part failed.
        try:
            db.commit()
        except Exception:
            db.rollback()
        return {"loaded": True, "partial": True, "created": created,
                "warning": f"some demo records were skipped: {e}"}
    finally:
        db.close()

    from core.audit_attachments import audit_record
    audit_record("system", 0, "import", new_values={"demo_data": created})

    return {
        "loaded": True,
        "created": created,
        "warning": "demo data loaded — evaluation only",
    }


@register("core.demo.clear")
def demo_clear(confirm=None, **kwargs):
    """Remove demo records (identified by the DEMO- product prefix and demo names)."""
    if str(confirm) != "yes":
        return {"error": "pass confirm=yes to clear demo data"}
    db = get_db()
    removed = {}
    try:
        cur = db.execute("DELETE FROM productos WHERE codigo LIKE 'DEMO-%'")
        removed["productos"] = cur.rowcount
        cur = db.execute("DELETE FROM warehouses WHERE code = 'DEMO'")
        removed["warehouses"] = cur.rowcount
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"clear failed: {e}"}
    finally:
        db.close()
    return {"cleared": True, "removed": removed,
            "note": "only clearly-marked demo records are removed"}
