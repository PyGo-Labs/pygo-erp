"""l10n_mx handlers — Mexican-specific logic registered from the module."""
import os
import re
import sys
import uuid as uuid_lib
from datetime import datetime

# Reach the app/ directory so core imports resolve
_here = os.path.dirname(os.path.abspath(__file__))
_app = os.path.dirname(os.path.dirname(_here))
if _app not in sys.path:
    sys.path.insert(0, _app)

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


RFC_PATTERN = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


@register("l10n_mx.validate_rfc")
def validate_rfc(rfc=None, **kwargs):
    """Validate a Mexican RFC. Registered as an invoice.before_create hook."""
    if not rfc:
        return {"rfc_valid": None, "note": "no rfc provided"}
    clean = str(rfc).upper().replace("-", "").replace(" ", "")
    valid = bool(RFC_PATTERN.match(clean))
    return {
        "rfc": clean,
        "rfc_valid": valid,
        "rfc_type": ("moral" if len(clean) == 12 else "fisica") if valid else None,
        "error": None if valid else f"invalid RFC format: {rfc}",
    }


@register("l10n_mx.catalog")
def mx_catalog(catalog=None, **kwargs):
    """Query SAT catalogs shipped by this module."""
    db = get_db()
    if catalog:
        rows = db.execute(
            "SELECT * FROM mx_sat_catalog WHERE catalog = ? ORDER BY code", (catalog,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM mx_sat_catalog ORDER BY catalog, code").fetchall()
    return [dict(r) for r in rows]


@register("l10n_mx.taxes")
def mx_taxes(**kwargs):
    """List the Mexican taxes this module installed into the generic engine."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM taxes WHERE country = 'MX' AND is_active = 1 ORDER BY sequence, id"
    ).fetchall()
    groups = db.execute(
        "SELECT * FROM tax_groups WHERE country = 'MX' ORDER BY name"
    ).fetchall()
    return {
        "taxes": [dict(r) for r in rows],
        "groups": [dict(g) for g in groups],
        "note": "rates live in the generic tax engine; this module only supplies them",
    }


@register("l10n_mx.compute_tax")
def mx_compute_tax(amount=None, tax_group_code=None, **kwargs):
    """Compute Mexican taxes via the generic engine using a group code."""
    if amount is None:
        return {"error": "amount required"}
    db = get_db()
    group_code = tax_group_code or "MX_IVA16"
    group = db.execute(
        "SELECT * FROM tax_groups WHERE code = ? AND country = 'MX'", (group_code,)
    ).fetchone()
    if not group:
        return {"error": f"tax group '{group_code}' not found; is l10n_mx installed?"}

    from core.tax_engine import tax_compute
    result = tax_compute(amount=amount, tax_group_id=group["id"])
    result["tax_group"] = group["name"]
    result["country"] = "MX"
    return result


@register("l10n_mx.prepare_cfdi")
def prepare_cfdi(
    invoice_id=None, rfc_emisor=None, rfc_receptor=None,
    uso_cfdi="G03", forma_pago="03", metodo_pago="PUE",
    regimen_fiscal="601", subtotal=0, total=0, **kwargs
):
    """Prepare CFDI metadata for an invoice (no PAC stamping yet)."""
    if not invoice_id:
        return {"cfdi": None, "note": "no invoice_id; nothing prepared"}

    db = get_db()
    existing = db.execute("SELECT * FROM mx_cfdi WHERE invoice_id = ?", (invoice_id,)).fetchone()
    if existing:
        return {"cfdi_id": existing["id"], "status": existing["status"], "already_prepared": True}

    inv = db.execute("SELECT * FROM facturas WHERE id = ?", (invoice_id,)).fetchone()
    inv_total = float(inv["total"]) if inv else float(total or 0)
    inv_subtotal = float(subtotal or 0) or round(inv_total / 1.16, 2)

    cur = db.execute(
        "INSERT INTO mx_cfdi (invoice_id, serie, folio, rfc_emisor, rfc_receptor, uso_cfdi, "
        "forma_pago, metodo_pago, regimen_fiscal, subtotal, total, status) "
        "VALUES (?, 'A', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')",
        (invoice_id, str(invoice_id).zfill(6), rfc_emisor, rfc_receptor, uso_cfdi,
         forma_pago, metodo_pago, regimen_fiscal, inv_subtotal, inv_total),
    )
    db.commit()
    return {
        "cfdi_id": cur.lastrowid,
        "invoice_id": invoice_id,
        "status": "draft",
        "subtotal": inv_subtotal,
        "total": inv_total,
        "note": "ready for PAC stamping (requires a PAC integration)",
    }


@register("l10n_mx.stamp_cfdi")
def stamp_cfdi(cfdi_id=None, **kwargs):
    """Simulate PAC stamping. A real PAC integration replaces this handler."""
    if not cfdi_id:
        return {"error": "cfdi_id required"}
    db = get_db()
    c = db.execute("SELECT * FROM mx_cfdi WHERE id = ?", (cfdi_id,)).fetchone()
    if not c:
        return {"error": "cfdi not found"}
    if c["status"] == "stamped":
        return {"error": "cfdi already stamped", "uuid": c["uuid"]}

    fake_uuid = str(uuid_lib.uuid4()).upper()
    db.execute(
        "UPDATE mx_cfdi SET uuid = ?, status = 'stamped', stamped_at = ? WHERE id = ?",
        (fake_uuid, datetime.utcnow().isoformat(), cfdi_id),
    )
    db.commit()
    return {
        "cfdi_id": cfdi_id,
        "uuid": fake_uuid,
        "status": "stamped",
        "warning": "SIMULATED stamp — not a fiscally valid CFDI. "
                   "Connect a certified PAC before production use.",
    }


@register("l10n_mx.cfdi.list")
def cfdi_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM mx_cfdi ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]
