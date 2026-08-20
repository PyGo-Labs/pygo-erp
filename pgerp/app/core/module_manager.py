"""PyGo ERP — Module management handlers and the extension hook system.

Hooks let a module extend core behaviour without the core importing it:
the core calls run_hook("sales.order.before_confirm", payload) and any
installed module registered on that point gets a chance to react.
"""
import os
import sys
import json
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register, HANDLERS
from core import module_loader


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


# --- Hook system ---

def run_hook(hook_point, payload=None):
    """Execute every active hook registered on a point, in priority order.

    Each hook handler is a registered handler name. A hook may mutate and
    return the payload; the accumulated payload is passed along the chain.
    """
    db = get_db()
    try:
        hooks = db.execute(
            "SELECT h.* FROM module_hooks h JOIN modules m ON m.name = h.module_name "
            "WHERE h.hook_point = ? AND h.is_active = 1 AND m.state = 'installed' "
            "ORDER BY h.priority ASC",
            (hook_point,),
        ).fetchall()
    except Exception:
        return {"hook_point": hook_point, "executed": 0, "payload": payload}

    payload = payload if payload is not None else {}
    executed = []
    for h in hooks:
        fn = HANDLERS.get(h["handler"])
        if fn is None:
            continue
        try:
            result = fn(**payload) if isinstance(payload, dict) else fn(payload)
            if isinstance(result, dict):
                payload = {**payload, **result}
            executed.append({"module": h["module_name"], "handler": h["handler"], "ok": True})
        except Exception as e:
            executed.append({"module": h["module_name"], "handler": h["handler"],
                             "ok": False, "error": str(e)})
    return {"hook_point": hook_point, "executed": len(executed), "hooks": executed, "payload": payload}


@register("core.hooks.list")
def hooks_list(hook_point=None, **kwargs):
    db = get_db()
    if hook_point:
        rows = db.execute(
            "SELECT * FROM module_hooks WHERE hook_point = ? ORDER BY priority", (hook_point,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM module_hooks ORDER BY hook_point, priority").fetchall()
    return [dict(r) for r in rows]


@register("core.hooks.register")
def hooks_register(module_name=None, hook_point=None, handler=None, priority=100, **kwargs):
    if not module_name or not hook_point or not handler:
        return {"error": "module_name, hook_point and handler required"}
    db = get_db()
    if not db.execute("SELECT 1 FROM modules WHERE name = ?", (module_name,)).fetchone():
        return {"error": f"module '{module_name}' not registered"}
    db.execute(
        "INSERT INTO module_hooks (module_name, hook_point, handler, priority) VALUES (?, ?, ?, ?)",
        (module_name, hook_point, handler, int(priority)),
    )
    db.commit()
    return {"module_name": module_name, "hook_point": hook_point, "handler": handler,
            "priority": int(priority), "registered": True}


@register("core.hooks.run")
def hooks_run(hook_point=None, payload=None, **kwargs):
    """Manually fire a hook point (useful for testing extensibility)."""
    if not hook_point:
        return {"error": "hook_point required"}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return run_hook(hook_point, payload or {})


# --- Module management ---

@register("core.modules.list")
def modules_list(state=None, category=None, **kwargs):
    db = get_db()
    sql = "SELECT * FROM modules WHERE 1=1"
    params = []
    if state:
        sql += " AND state = ?"
        params.append(state)
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY category, name"
    rows = db.execute(sql, params).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        try:
            d["depends"] = json.loads(r["depends"] or "[]")
        except Exception:
            d["depends"] = []
        d["hooks"] = db.execute(
            "SELECT COUNT(*) FROM module_hooks WHERE module_name = ? AND is_active = 1",
            (r["name"],),
        ).fetchone()[0]
        d["migrations_applied"] = db.execute(
            "SELECT COUNT(*) FROM module_migrations WHERE module_name = ?", (r["name"],)
        ).fetchone()[0]
        out.append(d)
    return out


@register("core.modules.scan")
def modules_scan(**kwargs):
    """Discover modules on disk and sync them into the registry."""
    result = module_loader.sync_registry()
    result["modules"] = [m["name"] for m in module_loader.discover()]
    return result


@register("core.modules.info")
def modules_info(name=None, **kwargs):
    if not name:
        return {"error": "name required"}
    db = get_db()
    row = db.execute("SELECT * FROM modules WHERE name = ?", (name,)).fetchone()
    if not row:
        return {"error": f"module '{name}' not found"}
    d = dict(row)
    try:
        d["depends"] = json.loads(row["depends"] or "[]")
    except Exception:
        d["depends"] = []
    d["dependents"] = module_loader.dependents_of(name, db)
    d["hooks"] = [dict(h) for h in db.execute(
        "SELECT * FROM module_hooks WHERE module_name = ? ORDER BY hook_point", (name,)
    ).fetchall()]
    d["migrations"] = [dict(m) for m in db.execute(
        "SELECT * FROM module_migrations WHERE module_name = ? ORDER BY applied_at", (name,)
    ).fetchall()]
    return d


@register("core.modules.install")
def modules_install(name=None, **kwargs):
    """Install a module: resolve deps, run its migrations, load its code."""
    if not name:
        return {"error": "name required"}
    db = get_db()
    row = db.execute("SELECT * FROM modules WHERE name = ?", (name,)).fetchone()
    if not row:
        return {"error": f"module '{name}' not found; run core.modules.scan first"}
    if row["state"] == "installed":
        return {"error": f"module '{name}' already installed", "state": "installed"}

    try:
        order = module_loader.resolve_dependencies(name, db)
    except ValueError as e:
        return {"error": str(e)}

    installed = []
    for mod_name in order:
        m = db.execute("SELECT * FROM modules WHERE name = ?", (mod_name,)).fetchone()
        if not m:
            return {"error": f"dependency '{mod_name}' not in registry"}
        if m["state"] == "installed":
            continue

        mig = module_loader.run_module_migrations(mod_name, m["path"], db)
        if mig.get("error"):
            return {"error": f"{mod_name}: {mig['error']}", "installed_so_far": installed}

        ok, err = module_loader.load_module_code(mod_name, m["path"])
        if not ok:
            return {"error": f"{mod_name}: failed to load code: {err}",
                    "installed_so_far": installed}

        db.execute(
            "UPDATE modules SET state = 'installed', installed_at = ? WHERE name = ?",
            (datetime.utcnow().isoformat(), mod_name),
        )
        db.commit()
        installed.append({
            "name": mod_name,
            "migrations_applied": mig.get("applied", 0),
        })

    return {
        "installed": installed,
        "install_order": order,
        "state": "installed",
        "handlers_total": len(HANDLERS),
    }


@register("core.modules.uninstall")
def modules_uninstall(name=None, force=0, **kwargs):
    """Uninstall a module. Refuses when other installed modules depend on it."""
    if not name:
        return {"error": "name required"}
    db = get_db()
    row = db.execute("SELECT * FROM modules WHERE name = ?", (name,)).fetchone()
    if not row:
        return {"error": f"module '{name}' not found"}
    if row["is_core"]:
        return {"error": "core modules cannot be uninstalled"}
    if row["state"] == "uninstalled":
        return {"error": f"module '{name}' is not installed"}

    dependents = module_loader.dependents_of(name, db)
    if dependents and not int(force or 0):
        return {
            "error": "other installed modules depend on this one",
            "dependents": dependents,
            "hint": "uninstall them first or pass force=1",
        }

    db.execute("UPDATE module_hooks SET is_active = 0 WHERE module_name = ?", (name,))
    db.execute("UPDATE modules SET state = 'uninstalled' WHERE name = ?", (name,))
    db.commit()
    return {
        "name": name,
        "state": "uninstalled",
        "hooks_deactivated": True,
        "note": "module data tables are preserved; reinstall keeps history",
    }


@register("core.modules.enable")
def modules_enable(name=None, **kwargs):
    """Re-activate an installed-but-disabled module."""
    if not name:
        return {"error": "name required"}
    db = get_db()
    row = db.execute("SELECT * FROM modules WHERE name = ?", (name,)).fetchone()
    if not row:
        return {"error": f"module '{name}' not found"}
    if row["state"] == "installed":
        return {"error": f"module '{name}' already enabled"}
    if row["state"] != "disabled":
        return {"error": f"module '{name}' is {row['state']}; install it first"}

    ok, err = module_loader.load_module_code(name, row["path"])
    if not ok:
        return {"error": f"failed to load code: {err}"}

    db.execute("UPDATE modules SET state = 'installed' WHERE name = ?", (name,))
    db.execute("UPDATE module_hooks SET is_active = 1 WHERE module_name = ?", (name,))
    db.commit()
    return {"name": name, "state": "installed", "enabled": True}


@register("core.modules.disable")
def modules_disable(name=None, **kwargs):
    """Disable a module without losing its data or migration history."""
    if not name:
        return {"error": "name required"}
    db = get_db()
    row = db.execute("SELECT * FROM modules WHERE name = ?", (name,)).fetchone()
    if not row:
        return {"error": f"module '{name}' not found"}
    if row["is_core"]:
        return {"error": "core modules cannot be disabled"}
    if row["state"] != "installed":
        return {"error": f"module '{name}' is {row['state']}, expected installed"}

    dependents = module_loader.dependents_of(name, db)
    if dependents:
        return {"error": "other installed modules depend on this one", "dependents": dependents}

    db.execute("UPDATE modules SET state = 'disabled' WHERE name = ?", (name,))
    db.execute("UPDATE module_hooks SET is_active = 0 WHERE module_name = ?", (name,))
    db.commit()
    return {"name": name, "state": "disabled", "hooks_deactivated": True}


@register("core.modules.dependency_graph")
def modules_dependency_graph(**kwargs):
    """Full dependency graph plus a valid global install order."""
    db = get_db()
    rows = db.execute("SELECT name, depends, state FROM modules ORDER BY name").fetchall()
    graph = {}
    for r in rows:
        try:
            deps = json.loads(r["depends"] or "[]")
        except Exception:
            deps = []
        graph[r["name"]] = {
            "depends": deps,
            "state": r["state"],
            "dependents": module_loader.dependents_of(r["name"], db),
        }

    order = []
    problems = []
    for name in graph:
        try:
            for m in module_loader.resolve_dependencies(name, db):
                if m not in order:
                    order.append(m)
        except ValueError as e:
            problems.append(str(e))

    return {"graph": graph, "suggested_install_order": order, "problems": problems}
