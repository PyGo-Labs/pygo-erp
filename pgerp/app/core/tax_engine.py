"""PyGo ERP — Generic tax engine (country-agnostic).

Supports the tax shapes every jurisdiction needs:
- percent            : amount is a percentage of the base
- fixed              : amount is a flat value per unit
- percent_of_tax     : amount applies over previously computed taxes (cascade)
- price_include      : the unit price already contains the tax (back it out)
- is_withholding     : tax is retained, subtracted from the total
- include_base_amount: this tax's result increases the base for later taxes
- sequence           : evaluation order for cascades

Country specifics (IVA/VAT/GST/ISR names and rates) belong to l10n_* modules.
"""
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


# --- Tax CRUD ---

@register("core.tax.list")
def tax_list(scope=None, country=None, **kwargs):
    db = get_db()
    sql = (
        "SELECT t.*, g.name AS tax_group_name FROM taxes t "
        "LEFT JOIN tax_groups g ON g.id = t.tax_group_id WHERE t.is_active = 1"
    )
    params = []
    if scope:
        sql += " AND (t.scope = ? OR t.scope = 'both')"
        params.append(scope)
    if country:
        sql += " AND (t.country = ? OR t.country IS NULL)"
        params.append(country)
    sql += " ORDER BY t.sequence, t.id"
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@register("core.tax.create")
def tax_create(
    name=None, code=None, amount=None, computation="percent",
    country=None, tax_group_id=None, price_include=0, is_withholding=0,
    sequence=10, include_base_amount=0, scope="sale", account_id=None,
    module_name=None, company_id=None, **kwargs
):
    if not name or amount is None:
        return {"error": "name and amount required"}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be numeric"}
    if computation not in ("percent", "fixed", "percent_of_tax"):
        return {"error": "computation must be percent|fixed|percent_of_tax"}
    if scope not in ("sale", "purchase", "both"):
        return {"error": "scope must be sale|purchase|both"}

    db = get_db()
    cur = db.execute(
        "INSERT INTO taxes (name, code, country, tax_group_id, computation, amount, price_include, "
        "is_withholding, sequence, include_base_amount, scope, account_id, module_name, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, code, country, tax_group_id, computation, amount, int(price_include),
         int(is_withholding), int(sequence), int(include_base_amount), scope,
         account_id, module_name, company_id),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "computation": computation,
            "amount": amount, "scope": scope}


@register("core.tax.groups.list")
def tax_groups_list(country=None, **kwargs):
    db = get_db()
    if country:
        groups = db.execute(
            "SELECT * FROM tax_groups WHERE country = ? OR country IS NULL ORDER BY name",
            (country,),
        ).fetchall()
    else:
        groups = db.execute("SELECT * FROM tax_groups ORDER BY name").fetchall()
    out = []
    for g in groups:
        taxes = db.execute(
            "SELECT t.* FROM taxes t JOIN tax_group_taxes gt ON gt.tax_id = t.id "
            "WHERE gt.tax_group_id = ? AND t.is_active = 1 ORDER BY t.sequence",
            (g["id"],),
        ).fetchall()
        d = dict(g)
        d["taxes"] = [dict(t) for t in taxes]
        out.append(d)
    return out


@register("core.tax.groups.create")
def tax_groups_create(name=None, code=None, country=None, description=None,
                      tax_ids=None, is_default=0, company_id=None, **kwargs):
    """Create a tax group. tax_ids = [1,2] to bundle taxes that apply together."""
    if not name:
        return {"error": "name required"}
    tax_ids = _parse(tax_ids) or []

    db = get_db()
    cur = db.execute(
        "INSERT INTO tax_groups (name, code, country, description, is_default, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, code, country, description, int(is_default), company_id),
    )
    group_id = cur.lastrowid
    for tid in tax_ids:
        db.execute(
            "INSERT INTO tax_group_taxes (tax_group_id, tax_id) VALUES (?, ?)",
            (group_id, tid),
        )
    db.commit()
    return {"id": group_id, "name": name, "taxes": len(tax_ids)}


# --- The engine ---

def compute_taxes(base_amount, taxes, quantity=1.0):
    """Core computation. taxes is an ordered list of dicts.

    Returns the untaxed base, per-tax detail, tax totals and the final total.
    """
    base_amount = float(base_amount)
    quantity = float(quantity or 1)

    ordered = sorted(taxes, key=lambda t: (int(t.get("sequence", 10)), int(t.get("id", 0))))

    # Step 1: back out any price-included, non-withholding percent taxes
    include_pct = sum(
        float(t.get("amount", 0))
        for t in ordered
        if int(t.get("price_include", 0)) and t.get("computation") == "percent"
        and not int(t.get("is_withholding", 0))
    )
    include_fixed = sum(
        float(t.get("amount", 0)) * quantity
        for t in ordered
        if int(t.get("price_include", 0)) and t.get("computation") == "fixed"
        and not int(t.get("is_withholding", 0))
    )

    untaxed = base_amount - include_fixed
    if include_pct:
        untaxed = untaxed / (1 + include_pct / 100)

    running_base = untaxed
    detail = []
    total_taxes = 0.0
    total_withheld = 0.0
    cumulative_tax = 0.0

    for t in ordered:
        comp = t.get("computation", "percent")
        amt = float(t.get("amount", 0))
        withholding = bool(int(t.get("is_withholding", 0)))

        if comp == "percent":
            value = running_base * amt / 100
        elif comp == "fixed":
            value = amt * quantity
        elif comp == "percent_of_tax":
            value = cumulative_tax * amt / 100
        else:
            value = 0.0

        value = round(value, 4)
        if withholding:
            total_withheld += value
        else:
            total_taxes += value
            cumulative_tax += value
            if int(t.get("include_base_amount", 0)):
                running_base += value

        detail.append({
            "tax_id": t.get("id"),
            "name": t.get("name"),
            "code": t.get("code"),
            "computation": comp,
            "rate": amt,
            "base": round(running_base, 4),
            "amount": value,
            "is_withholding": withholding,
            "price_include": bool(int(t.get("price_include", 0))),
        })

    return {
        "untaxed_amount": round(untaxed, 2),
        "taxes": detail,
        "total_taxes": round(total_taxes, 2),
        "total_withheld": round(total_withheld, 2),
        "total": round(untaxed + total_taxes - total_withheld, 2),
    }


@register("core.tax.compute")
def tax_compute(amount=None, tax_ids=None, tax_group_id=None, quantity=1,
                scope="sale", country=None, **kwargs):
    """Compute taxes for an amount using explicit ids, a group, or country defaults."""
    if amount is None:
        return {"error": "amount required"}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be numeric"}

    db = get_db()
    tax_ids = _parse(tax_ids)

    rows = []
    if tax_ids:
        placeholders = ",".join("?" * len(tax_ids))
        rows = db.execute(
            f"SELECT * FROM taxes WHERE id IN ({placeholders}) AND is_active = 1", tax_ids
        ).fetchall()
    elif tax_group_id:
        rows = db.execute(
            "SELECT t.* FROM taxes t JOIN tax_group_taxes gt ON gt.tax_id = t.id "
            "WHERE gt.tax_group_id = ? AND t.is_active = 1",
            (tax_group_id,),
        ).fetchall()
    else:
        sql = "SELECT * FROM taxes WHERE is_active = 1 AND (scope = ? OR scope = 'both')"
        params = [scope]
        if country:
            sql += " AND (country = ? OR country IS NULL)"
            params.append(country)
        else:
            sql += " AND country IS NULL"
        rows = db.execute(sql, params).fetchall()

    if not rows:
        return {
            "untaxed_amount": round(amount, 2), "taxes": [], "total_taxes": 0,
            "total_withheld": 0, "total": round(amount, 2),
            "note": "no taxes matched; amount returned untaxed",
        }

    result = compute_taxes(amount, [dict(r) for r in rows], quantity)
    result["input_amount"] = round(amount, 2)
    result["scope"] = scope
    return result


@register("core.tax.compute_document")
def tax_compute_document(lines=None, scope="sale", country=None, **kwargs):
    """Compute taxes for a whole document.

    lines = [{"amount":1000,"quantity":2,"tax_ids":[1,2]}]
    """
    lines = _parse(lines)
    if not lines:
        return {"error": "lines required"}

    untaxed = 0.0
    total_taxes = 0.0
    total_withheld = 0.0
    tax_summary = {}
    line_results = []

    for idx, l in enumerate(lines):
        amt = float(l.get("amount", 0))
        qty = float(l.get("quantity", 1) or 1)
        res = tax_compute(
            amount=amt, tax_ids=l.get("tax_ids"), tax_group_id=l.get("tax_group_id"),
            quantity=qty, scope=scope, country=country,
        )
        if res.get("error"):
            return {"error": f"line {idx}: {res['error']}"}

        untaxed += res["untaxed_amount"]
        total_taxes += res["total_taxes"]
        total_withheld += res["total_withheld"]
        for t in res.get("taxes", []):
            key = t.get("name") or f"tax_{t.get('tax_id')}"
            if key not in tax_summary:
                tax_summary[key] = {"name": key, "code": t.get("code"),
                                    "rate": t.get("rate"), "amount": 0.0,
                                    "is_withholding": t.get("is_withholding")}
            tax_summary[key]["amount"] = round(tax_summary[key]["amount"] + t["amount"], 4)

        line_results.append({
            "line": idx,
            "untaxed": res["untaxed_amount"],
            "taxes": res["total_taxes"],
            "withheld": res["total_withheld"],
            "total": res["total"],
        })

    return {
        "lines": line_results,
        "untaxed_amount": round(untaxed, 2),
        "tax_summary": list(tax_summary.values()),
        "total_taxes": round(total_taxes, 2),
        "total_withheld": round(total_withheld, 2),
        "total": round(untaxed + total_taxes - total_withheld, 2),
    }


@register("core.tax.seed_generic")
def tax_seed_generic(**kwargs):
    """Seed neutral, country-agnostic sample taxes.

    Deliberately generic: real rates come from l10n_* modules.
    """
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM taxes").fetchone()[0] > 0:
        return {"seeded": False, "reason": "already seeded"}

    presets = [
        ("Standard Rate", "STD", "percent", 16, 0, 0, 10, "both"),
        ("Reduced Rate", "RED", "percent", 8, 0, 0, 10, "both"),
        ("Zero Rate", "ZERO", "percent", 0, 0, 0, 10, "both"),
        ("Standard Rate (incl.)", "STD_INC", "percent", 16, 1, 0, 10, "sale"),
    ]
    ids = []
    for name, code, comp, amt, incl, wh, seq, scope in presets:
        cur = db.execute(
            "INSERT INTO taxes (name, code, computation, amount, price_include, is_withholding, "
            "sequence, scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, code, comp, amt, incl, wh, seq, scope),
        )
        ids.append(cur.lastrowid)

    cur = db.execute(
        "INSERT INTO tax_groups (name, code, description, is_default) "
        "VALUES ('Standard Taxes', 'STD_GROUP', 'Generic standard rate', 1)"
    )
    db.execute("INSERT INTO tax_group_taxes (tax_group_id, tax_id) VALUES (?, ?)",
               (cur.lastrowid, ids[0]))
    db.commit()
    return {"seeded": True, "taxes": len(presets), "groups": 1}
