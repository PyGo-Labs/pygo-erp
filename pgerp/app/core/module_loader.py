"""PyGo ERP — Module loader: discovery, dependency resolution, manifest parsing.

A module lives in app/modules/<name>/ and declares a module.yaml manifest:

    name: l10n_mx
    display_name: Mexico Localization
    version: 1.0.0
    category: localization
    depends: [core]
    summary: CFDI, DIOT and Mexican tax rules

Modules are pure additions: they register handlers, migrations and hooks
without the core knowing they exist.
"""
import os
import sys
import json
import importlib

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

MODULES_DIR = os.path.join(base, "app", "modules")


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


def _parse_yaml_simple(text):
    """Minimal YAML subset parser (stdlib only, no PyYAML dependency).

    Supports: key: value, inline lists [a, b], and quoted strings.
    Sufficient for module manifests; keeps the framework dependency-free.
    """
    data = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        if line != line.lstrip():
            continue  # ignore nested blocks
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            data[key] = ""
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            items = [v.strip().strip("'\"") for v in inner.split(",")] if inner else []
            data[key] = [i for i in items if i]
        elif value.lower() in ("true", "yes"):
            data[key] = True
        elif value.lower() in ("false", "no"):
            data[key] = False
        else:
            data[key] = value.strip("'\"")
    return data


def read_manifest(module_path):
    """Read module.yaml from a module directory."""
    manifest_path = os.path.join(module_path, "module.yaml")
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = _parse_yaml_simple(f.read())
    except Exception:
        return None
    if not data.get("name"):
        return None
    depends = data.get("depends") or []
    if isinstance(depends, str):
        depends = [d.strip() for d in depends.split(",") if d.strip()]
    data["depends"] = depends
    return data


def discover():
    """Scan app/modules/ and return every valid manifest found on disk."""
    found = []
    if not os.path.isdir(MODULES_DIR):
        return found
    for entry in sorted(os.listdir(MODULES_DIR)):
        path = os.path.join(MODULES_DIR, entry)
        if not os.path.isdir(path) or entry.startswith((".", "_")):
            continue
        manifest = read_manifest(path)
        if manifest:
            manifest["path"] = path
            found.append(manifest)
    return found


def sync_registry():
    """Reconcile on-disk modules with the DB registry (idempotent)."""
    db = get_db()
    found = discover()
    added, updated = 0, 0
    for m in found:
        row = db.execute("SELECT * FROM modules WHERE name = ?", (m["name"],)).fetchone()
        depends_json = json.dumps(m.get("depends", []))
        if row:
            db.execute(
                "UPDATE modules SET display_name = ?, version = ?, category = ?, summary = ?, "
                "author = ?, depends = ?, path = ?, auto_install = ?, updated_at = datetime('now') "
                "WHERE name = ?",
                (m.get("display_name") or m["name"], m.get("version", "1.0.0"),
                 m.get("category"), m.get("summary"), m.get("author"), depends_json,
                 m["path"], 1 if m.get("auto_install") else 0, m["name"]),
            )
            updated += 1
        else:
            db.execute(
                "INSERT INTO modules (name, display_name, version, category, summary, author, "
                "depends, state, path, auto_install) VALUES (?, ?, ?, ?, ?, ?, ?, 'uninstalled', ?, ?)",
                (m["name"], m.get("display_name") or m["name"], m.get("version", "1.0.0"),
                 m.get("category"), m.get("summary"), m.get("author"), depends_json,
                 m["path"], 1 if m.get("auto_install") else 0),
            )
            added += 1
    db.commit()
    return {"discovered": len(found), "added": added, "updated": updated}


def resolve_dependencies(module_name, db=None, _seen=None):
    """Return the install order for a module, dependencies first.

    Raises ValueError on a missing dependency or a circular chain.
    """
    own_db = db is None
    db = db or get_db()
    _seen = _seen or []

    if module_name in _seen:
        raise ValueError(f"circular dependency: {' -> '.join(_seen + [module_name])}")

    row = db.execute("SELECT * FROM modules WHERE name = ?", (module_name,)).fetchone()
    if not row:
        # 'core' is implicit and always present
        if module_name == "core":
            return []
        raise ValueError(f"module '{module_name}' not found in registry")

    order = []
    try:
        depends = json.loads(row["depends"] or "[]")
    except Exception:
        depends = []

    for dep in depends:
        if dep == "core":
            continue
        order.extend(resolve_dependencies(dep, db, _seen + [module_name]))

    if module_name not in order:
        order.append(module_name)
    return order


def dependents_of(module_name, db=None):
    """Modules that depend on the given one (blocks uninstall)."""
    db = db or get_db()
    out = []
    for row in db.execute("SELECT name, depends, state FROM modules").fetchall():
        try:
            deps = json.loads(row["depends"] or "[]")
        except Exception:
            deps = []
        if module_name in deps and row["state"] == "installed":
            out.append(row["name"])
    return out


def load_module_code(module_name, module_path):
    """Import a module's Python package so its handlers/migrations register."""
    modules_parent = os.path.dirname(module_path)
    if modules_parent not in sys.path:
        sys.path.insert(0, modules_parent)
    try:
        mod = importlib.import_module(module_name)
        importlib.reload(mod)
        return True, None
    except Exception as e:
        return False, str(e)


def run_module_migrations(module_name, module_path, db=None):
    """Apply a module's own migrations, tracked separately from core ones."""
    db = db or get_db()
    migrations_file = os.path.join(module_path, "migrations.py")
    if not os.path.exists(migrations_file):
        return {"applied": 0, "migrations": []}

    modules_parent = os.path.dirname(module_path)
    if modules_parent not in sys.path:
        sys.path.insert(0, modules_parent)

    try:
        mig_mod = importlib.import_module(f"{module_name}.migrations")
        importlib.reload(mig_mod)
    except Exception as e:
        return {"error": f"failed to import migrations: {e}", "applied": 0}

    applied = []
    for name in sorted(d for d in dir(mig_mod) if d.startswith("migration_")):
        already = db.execute(
            "SELECT 1 FROM module_migrations WHERE module_name = ? AND migration_name = ?",
            (module_name, name),
        ).fetchone()
        if already:
            continue
        fn = getattr(mig_mod, name)
        try:
            fn(db)
            db.execute(
                "INSERT INTO module_migrations (module_name, migration_name) VALUES (?, ?)",
                (module_name, name),
            )
            db.commit()
            applied.append(name)
        except Exception as e:
            db.rollback()
            return {"error": f"migration {name} failed: {e}", "applied": len(applied),
                    "migrations": applied}
    return {"applied": len(applied), "migrations": applied}
