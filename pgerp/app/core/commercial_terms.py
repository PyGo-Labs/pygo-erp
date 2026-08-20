"""PyGo ERP — Payment terms and document sequences (universal core)."""
import os
import sys
from datetime import datetime, timedelta

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


# --- Payment terms ---

@register("core.payment_terms.list")
def payment_terms_list(**kwargs):
    db = get_db()
    terms = db.execute("SELECT * FROM payment_terms ORDER BY name").fetchall()
    out = []
    for t in terms:
        lines = db.execute(
            "SELECT * FROM payment_term_lines WHERE term_id = ? ORDER BY days",
            (t["id"],),
        ).fetchall()
        d = dict(t)
        d["lines"] = [dict(l) for l in lines]
        out.append(d)
    return out


@register("core.payment_terms.create")
def payment_terms_create(name=None, lines=None, early_discount_pct=0, early_discount_days=0, **kwargs):
    """Create a payment term. lines = [{"days": 30, "percent": 100}]"""
    if not name:
        return {"error": "name required"}
    if not lines:
        lines = [{"days": 0, "percent": 100}]
    if isinstance(lines, str):
        import json
        try:
            lines = json.loads(lines)
        except Exception:
            return {"error": "lines must be valid JSON"}

    total = sum(float(l.get("percent", 0)) for l in lines)
    if abs(total - 100) > 0.01:
        return {"error": f"lines percent must sum 100, got {total}"}

    db = get_db()
    cur = db.execute(
        "INSERT INTO payment_terms (name, early_discount_pct, early_discount_days) VALUES (?, ?, ?)",
        (name, float(early_discount_pct or 0), int(early_discount_days or 0)),
    )
    term_id = cur.lastrowid
    for l in lines:
        db.execute(
            "INSERT INTO payment_term_lines (term_id, days, percent) VALUES (?, ?, ?)",
            (term_id, int(l.get("days", 0)), float(l.get("percent", 0))),
        )
    db.commit()
    return {"id": term_id, "name": name, "lines": len(lines)}


@register("core.payment_terms.schedule")
def payment_terms_schedule(term_id=None, amount=None, start_date=None, **kwargs):
    """Compute the due-date schedule for an amount under a payment term."""
    if not term_id or amount is None:
        return {"error": "term_id and amount required"}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be numeric"}

    db = get_db()
    term = db.execute("SELECT * FROM payment_terms WHERE id = ?", (term_id,)).fetchone()
    if not term:
        return {"error": "payment term not found"}
    lines = db.execute(
        "SELECT * FROM payment_term_lines WHERE term_id = ? ORDER BY days", (term_id,)
    ).fetchall()

    base_date = datetime.utcnow()
    if start_date:
        try:
            base_date = datetime.strptime(str(start_date)[:10], "%Y-%m-%d")
        except ValueError:
            pass

    schedule = []
    for l in lines:
        due = base_date + timedelta(days=int(l["days"]))
        schedule.append({
            "days": l["days"],
            "percent": l["percent"],
            "amount": round(amount * float(l["percent"]) / 100, 2),
            "due_date": due.strftime("%Y-%m-%d"),
        })

    result = {
        "term": term["name"],
        "amount": amount,
        "schedule": schedule,
        "final_due_date": schedule[-1]["due_date"] if schedule else None,
    }
    if term["early_discount_pct"]:
        disc_date = base_date + timedelta(days=int(term["early_discount_days"]))
        result["early_payment"] = {
            "discount_pct": term["early_discount_pct"],
            "pay_before": disc_date.strftime("%Y-%m-%d"),
            "amount": round(amount * (1 - float(term["early_discount_pct"]) / 100), 2),
        }
    return result


@register("core.payment_terms.seed")
def payment_terms_seed(**kwargs):
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM payment_terms").fetchone()[0] > 0:
        return {"seeded": False, "reason": "already seeded"}

    presets = [
        ("Immediate Payment", [{"days": 0, "percent": 100}], 0, 0),
        ("15 Days", [{"days": 15, "percent": 100}], 0, 0),
        ("30 Days", [{"days": 30, "percent": 100}], 0, 0),
        ("60 Days", [{"days": 60, "percent": 100}], 0, 0),
        ("90 Days", [{"days": 90, "percent": 100}], 0, 0),
        ("30/60/90 Split", [{"days": 30, "percent": 34}, {"days": 60, "percent": 33}, {"days": 90, "percent": 33}], 0, 0),
        ("2/10 Net 30", [{"days": 30, "percent": 100}], 2, 10),
        ("50% Advance, 50% on Delivery", [{"days": 0, "percent": 50}, {"days": 30, "percent": 50}], 0, 0),
    ]
    for name, lines, disc, disc_days in presets:
        cur = db.execute(
            "INSERT INTO payment_terms (name, early_discount_pct, early_discount_days) VALUES (?, ?, ?)",
            (name, disc, disc_days),
        )
        tid = cur.lastrowid
        for l in lines:
            db.execute(
                "INSERT INTO payment_term_lines (term_id, days, percent) VALUES (?, ?, ?)",
                (tid, l["days"], l["percent"]),
            )
    db.commit()
    return {"seeded": True, "terms": len(presets)}


# --- Document sequences (series / folios) ---

@register("core.sequences.list")
def sequences_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM sequences ORDER BY doc_type, company_id").fetchall()
    return [dict(r) for r in rows]


@register("core.sequences.create")
def sequences_create(
    doc_type=None, prefix="", suffix="", padding=6,
    next_number=1, company_id=None, reset_period="never", **kwargs
):
    if not doc_type:
        return {"error": "doc_type required"}
    if reset_period not in ("never", "yearly", "monthly"):
        return {"error": "reset_period must be never|yearly|monthly"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO sequences (doc_type, prefix, suffix, padding, next_number, company_id, reset_period) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_type, prefix, suffix, int(padding), int(next_number), company_id, reset_period),
    )
    db.commit()
    return {"id": cur.lastrowid, "doc_type": doc_type, "prefix": prefix}


@register("core.sequences.next")
def sequences_next(doc_type=None, company_id=None, **kwargs):
    """Get and consume the next document number for a doc_type."""
    if not doc_type:
        return {"error": "doc_type required"}
    db = get_db()
    if company_id:
        seq = db.execute(
            "SELECT * FROM sequences WHERE doc_type = ? AND company_id = ?",
            (doc_type, company_id),
        ).fetchone()
    else:
        seq = db.execute(
            "SELECT * FROM sequences WHERE doc_type = ? ORDER BY company_id IS NULL DESC LIMIT 1",
            (doc_type,),
        ).fetchone()
    if not seq:
        return {"error": f"no sequence configured for {doc_type}"}

    now = datetime.utcnow()
    number = int(seq["next_number"])
    period_key = ""
    if seq["reset_period"] == "yearly":
        period_key = now.strftime("%Y")
    elif seq["reset_period"] == "monthly":
        period_key = now.strftime("%Y%m")

    if period_key and seq["current_period"] != period_key:
        number = 1

    prefix = (seq["prefix"] or "").replace("{YYYY}", now.strftime("%Y")).replace("{MM}", now.strftime("%m"))
    folio = f"{prefix}{str(number).zfill(int(seq['padding']))}{seq['suffix'] or ''}"

    db.execute(
        "UPDATE sequences SET next_number = ?, current_period = ? WHERE id = ?",
        (number + 1, period_key, seq["id"]),
    )
    db.commit()
    return {"doc_type": doc_type, "folio": folio, "number": number}


@register("core.sequences.seed")
def sequences_seed(**kwargs):
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM sequences").fetchone()[0] > 0:
        return {"seeded": False, "reason": "already seeded"}
    presets = [
        ("sales_order", "SO-{YYYY}-", "", 5, "yearly"),
        ("invoice", "INV-{YYYY}-", "", 5, "yearly"),
        ("quote", "QUO-{YYYY}-", "", 5, "yearly"),
        ("purchase_order", "PO-{YYYY}-", "", 5, "yearly"),
        ("rfq", "RFQ-{YYYY}-", "", 5, "yearly"),
        ("receipt", "RCP-{YYYY}-", "", 5, "yearly"),
        ("credit_note", "CN-{YYYY}-", "", 5, "yearly"),
        ("journal_entry", "JE-{YYYY}{MM}-", "", 5, "monthly"),
        ("production_order", "MO-{YYYY}-", "", 5, "yearly"),
        ("expense", "EXP-{YYYY}-", "", 5, "yearly"),
    ]
    for doc_type, prefix, suffix, padding, reset in presets:
        db.execute(
            "INSERT INTO sequences (doc_type, prefix, suffix, padding, next_number, reset_period) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (doc_type, prefix, suffix, padding, reset),
        )
    db.commit()
    return {"seeded": True, "sequences": len(presets)}
