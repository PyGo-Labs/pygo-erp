"""PyGo ERP — Setup wizard: guided onboarding so the ERP is usable on install.

Steps: company -> localization -> chart_of_accounts -> taxes -> sequences -> done.
Every step is idempotent and reports what remains.
"""
import os
import sys
import json
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
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
    except Exception:
        pass
    return conn


STEPS = [
    ("company", "Company identity: legal name, tax id, address"),
    ("localization", "Country, currency, language and timezone"),
    ("chart_of_accounts", "Chart of accounts installed"),
    ("taxes", "Tax rules configured (via localization module or generic)"),
    ("sequences", "Document numbering series"),
    ("warehouse", "At least one warehouse for inventory"),
]

# Country -> sensible defaults. Kept minimal on purpose: deep localization
# belongs to l10n_* modules, this only bootstraps something usable.
COUNTRY_DEFAULTS = {
    "MX": {"currency": "MXN", "language": "es", "timezone": "America/Mexico_City", "module": "l10n_mx"},
    "CO": {"currency": "COP", "language": "es", "timezone": "America/Bogota", "module": "l10n_co"},
    "ES": {"currency": "EUR", "language": "es", "timezone": "Europe/Madrid", "module": "l10n_es"},
    "AR": {"currency": "ARS", "language": "es", "timezone": "America/Argentina/Buenos_Aires", "module": "l10n_ar"},
    "CL": {"currency": "CLP", "language": "es", "timezone": "America/Santiago", "module": "l10n_cl"},
    "US": {"currency": "USD", "language": "en", "timezone": "America/New_York", "module": None},
    "GB": {"currency": "GBP", "language": "en", "timezone": "Europe/London", "module": None},
    "BR": {"currency": "BRL", "language": "pt", "timezone": "America/Sao_Paulo", "module": "l10n_br"},
}


def _mark_step(db, step, status="done", data=None):
    payload = json.dumps(data or {})
    existing = db.execute("SELECT id FROM setup_state WHERE step = ?", (step,)).fetchone()
    now = datetime.utcnow().isoformat() if status == "done" else None
    if existing:
        db.execute(
            "UPDATE setup_state SET status = ?, data = ?, completed_at = ? WHERE step = ?",
            (status, payload, now, step),
        )
    else:
        db.execute(
            "INSERT INTO setup_state (step, status, data, completed_at) VALUES (?, ?, ?, ?)",
            (step, status, payload, now),
        )
    db.commit()


def _set_setting(db, company_id, key, value):
    db.execute(
        "INSERT INTO company_settings (company_id, setting_key, setting_value) VALUES (?, ?, ?) "
        "ON CONFLICT(company_id, setting_key) DO UPDATE SET setting_value = excluded.setting_value, "
        "updated_at = datetime('now')",
        (company_id, key, str(value)),
    )


def _detect_step_status(db, step):
    """Infer completion from real data, not just the wizard's own bookkeeping."""
    try:
        if step == "company":
            row = db.execute("SELECT COUNT(*) FROM companies").fetchone()
            return bool(row and row[0])
        if step == "localization":
            row = db.execute(
                "SELECT COUNT(*) FROM company_settings WHERE setting_key = 'country'"
            ).fetchone()
            return bool(row and row[0])
        if step == "chart_of_accounts":
            row = db.execute("SELECT COUNT(*) FROM accounts").fetchone()
            return bool(row and row[0])
        if step == "taxes":
            row = db.execute("SELECT COUNT(*) FROM taxes WHERE is_active = 1").fetchone()
            return bool(row and row[0])
        if step == "sequences":
            row = db.execute("SELECT COUNT(*) FROM sequences").fetchone()
            return bool(row and row[0])
        if step == "warehouse":
            row = db.execute("SELECT COUNT(*) FROM warehouses").fetchone()
            return bool(row and row[0])
    except Exception:
        return False
    return False


@register("core.setup.status")
def setup_status(**kwargs):
    """Where the installation stands and what is still missing."""
    db = get_db()
    steps = []
    done_count = 0
    for step, description in STEPS:
        row = db.execute("SELECT * FROM setup_state WHERE step = ?", (step,)).fetchone()
        detected = _detect_step_status(db, step)
        status = "done" if (detected or (row and row["status"] == "done")) else "pending"
        if status == "done":
            done_count += 1
        data = {}
        if row:
            try:
                data = json.loads(row["data"] or "{}")
            except Exception:
                data = {}
        steps.append({
            "step": step,
            "description": description,
            "status": status,
            "data": data,
            "completed_at": row["completed_at"] if row else None,
        })

    total = len(STEPS)
    return {
        "steps": steps,
        "completed": done_count,
        "total": total,
        "progress_pct": round(done_count / total * 100, 1),
        "is_ready": done_count == total,
        "next_step": next((s["step"] for s in steps if s["status"] == "pending"), None),
    }


@register("core.setup.countries")
def setup_countries(**kwargs):
    """Supported country presets and whether their l10n module is available."""
    db = get_db()
    out = []
    for code, d in sorted(COUNTRY_DEFAULTS.items()):
        module_state = None
        if d["module"]:
            row = db.execute("SELECT state FROM modules WHERE name = ?", (d["module"],)).fetchone()
            module_state = row["state"] if row else "not_available"
        out.append({
            "country": code,
            "currency": d["currency"],
            "language": d["language"],
            "timezone": d["timezone"],
            "localization_module": d["module"],
            "module_state": module_state,
        })
    return {"countries": out, "note": "countries without a module still work with generic taxes"}


@register("core.setup.company")
def setup_company(
    name=None, legal_name=None, tax_id=None, address=None,
    email=None, phone=None, company_id=None, **kwargs
):
    """Step 1: company identity."""
    if not name:
        return {"error": "name required"}
    db = get_db()

    if company_id:
        row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return {"error": "company not found"}
        db.execute("UPDATE companies SET name = ? WHERE id = ?", (name, company_id))
        cid = company_id
    else:
        row = db.execute("SELECT * FROM companies ORDER BY id LIMIT 1").fetchone()
        if row:
            cid = row["id"]
            db.execute("UPDATE companies SET name = ? WHERE id = ?", (name, cid))
        else:
            slug = name.lower().replace(" ", "-")[:40]
            cur = db.execute("INSERT INTO companies (name, slug) VALUES (?, ?)", (name, slug))
            cid = cur.lastrowid

    for key, value in [
        ("legal_name", legal_name or name), ("tax_id", tax_id or ""),
        ("address", address or ""), ("email", email or ""), ("phone", phone or ""),
    ]:
        _set_setting(db, cid, key, value)
    db.commit()

    _mark_step(db, "company", "done", {"company_id": cid, "name": name})
    return {"company_id": cid, "name": name, "step": "company", "status": "done"}


@register("core.setup.localization")
def setup_localization(country=None, currency=None, language=None, timezone=None,
                       install_module=1, company_id=None, **kwargs):
    """Step 2: country/currency/language, optionally installing the l10n module."""
    if not country:
        return {"error": "country required", "available": sorted(COUNTRY_DEFAULTS.keys())}
    country = str(country).upper()
    defaults = COUNTRY_DEFAULTS.get(country)
    if not defaults:
        defaults = {"currency": currency or "USD", "language": language or "en",
                    "timezone": timezone or "UTC", "module": None}

    db = get_db()
    if not company_id:
        row = db.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
        company_id = row["id"] if row else None
    if not company_id:
        return {"error": "no company configured; run core.setup.company first"}

    resolved = {
        "country": country,
        "currency": currency or defaults["currency"],
        "language": language or defaults["language"],
        "timezone": timezone or defaults["timezone"],
    }
    for k, v in resolved.items():
        _set_setting(db, company_id, k, v)
    db.commit()

    module_result = None
    mod_name = defaults.get("module")
    if mod_name and int(install_module or 0):
        row = db.execute("SELECT * FROM modules WHERE name = ?", (mod_name,)).fetchone()
        if not row:
            module_result = {"module": mod_name, "installed": False,
                             "reason": "module not present on disk"}
        elif row["state"] == "installed":
            module_result = {"module": mod_name, "installed": True, "already": True}
        else:
            from core.module_manager import modules_install
            res = modules_install(name=mod_name)
            module_result = {"module": mod_name,
                             "installed": not bool(res.get("error")),
                             "detail": res}

    _mark_step(db, "localization", "done", {**resolved, "module": module_result})
    return {
        "step": "localization", "status": "done",
        "company_id": company_id, **resolved,
        "localization_module": module_result,
    }


@register("core.setup.finalize")
def setup_finalize(company_id=None, create_warehouse=1, **kwargs):
    """Final step: verify the remaining prerequisites and mark the ERP ready."""
    db = get_db()
    if not company_id:
        row = db.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
        company_id = row["id"] if row else None

    actions = []

    # Chart of accounts
    if not _detect_step_status(db, "chart_of_accounts"):
        try:
            from core.accounting import accounts_seed
            accounts_seed()
            actions.append("chart_of_accounts seeded")
        except Exception as e:
            actions.append(f"chart_of_accounts failed: {e}")
    _mark_step(db, "chart_of_accounts", "done" if _detect_step_status(db, "chart_of_accounts") else "pending")

    # Taxes
    if not _detect_step_status(db, "taxes"):
        try:
            from core.tax_engine import tax_seed_generic
            tax_seed_generic()
            actions.append("generic taxes seeded")
        except Exception as e:
            actions.append(f"taxes failed: {e}")
    _mark_step(db, "taxes", "done" if _detect_step_status(db, "taxes") else "pending")

    # Sequences
    if not _detect_step_status(db, "sequences"):
        try:
            from core.commercial_terms import sequences_seed
            sequences_seed()
            actions.append("sequences seeded")
        except Exception as e:
            actions.append(f"sequences failed: {e}")
    _mark_step(db, "sequences", "done" if _detect_step_status(db, "sequences") else "pending")

    # Warehouse
    if not _detect_step_status(db, "warehouse") and int(create_warehouse or 0):
        try:
            db.execute(
                "INSERT INTO warehouses (name, code) VALUES ('Main Warehouse', 'MAIN')"
            )
            db.commit()
            actions.append("default warehouse created")
        except Exception as e:
            actions.append(f"warehouse failed: {e}")
    _mark_step(db, "warehouse", "done" if _detect_step_status(db, "warehouse") else "pending")

    status = setup_status()
    return {
        "actions": actions,
        "is_ready": status["is_ready"],
        "progress_pct": status["progress_pct"],
        "next_step": status["next_step"],
        "company_id": company_id,
    }


@register("core.setup.settings")
def setup_settings(company_id=None, **kwargs):
    """Read every configured setting for a company."""
    db = get_db()
    if not company_id:
        row = db.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
        company_id = row["id"] if row else None
    if not company_id:
        return {"error": "no company configured"}
    rows = db.execute(
        "SELECT setting_key, setting_value, updated_at FROM company_settings "
        "WHERE company_id = ? ORDER BY setting_key",
        (company_id,),
    ).fetchall()
    return {
        "company_id": company_id,
        "settings": {r["setting_key"]: r["setting_value"] for r in rows},
        "count": len(rows),
    }


@register("core.setup.set_setting")
def setup_set_setting(key=None, value=None, company_id=None, **kwargs):
    if not key:
        return {"error": "key required"}
    db = get_db()
    if not company_id:
        row = db.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
        company_id = row["id"] if row else None
    if not company_id:
        return {"error": "no company configured"}
    _set_setting(db, company_id, key, value if value is not None else "")
    db.commit()
    return {"company_id": company_id, "key": key, "value": value, "saved": True}


@register("core.setup.reset")
def setup_reset(confirm=None, **kwargs):
    """Clear wizard bookkeeping (does NOT delete business data)."""
    if str(confirm) != "yes":
        return {"error": "pass confirm=yes to reset the wizard state",
                "note": "business data is never deleted by this call"}
    db = get_db()
    db.execute("DELETE FROM setup_state")
    db.commit()
    return {"reset": True, "note": "wizard state cleared; business data untouched"}
