"""PyGo ERP V2.0 — Accounting Real (IVA, Retenciones, DIOT, Multimoneda)."""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

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


# --- Tax Rates ---

@register("core.accounting.tax_rates.list")
def tax_rates_list(**kwargs):
    """List all tax rates."""
    db = get_db()
    rows = db.execute("SELECT * FROM tax_rates ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@register("core.accounting.tax_rates.create")
def tax_rates_create(name=None, rate=None, type="iva", is_retention=False, **kwargs):
    """Create a tax rate."""
    if not name or rate is None:
        return {"error": "name and rate required"}
    
    db = get_db()
    try:
        rate_val = float(rate)
    except ValueError:
        return {"error": "invalid rate"}
    
    cursor = db.execute(
        "INSERT INTO tax_rates (name, rate, type, is_retention) VALUES (?, ?, ?, ?)",
        (name, rate_val, type, 1 if is_retention else 0)
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "name": name, "rate": rate_val, "type": type}


@register("core.accounting.tax_rates.update")
def tax_rates_update(tax_id=None, **kwargs):
    """Update a tax rate."""
    if not tax_id:
        return {"error": "tax_id required"}
    
    db = get_db()
    row = db.execute("SELECT * FROM tax_rates WHERE id = ?", (tax_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    
    allowed = ["name", "rate", "type", "is_retention"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [tax_id]
        db.execute(f"UPDATE tax_rates SET {sets} WHERE id = ?", vals)
        db.commit()
    
    return dict(db.execute("SELECT * FROM tax_rates WHERE id = ?", (tax_id,)).fetchone())


@register("core.accounting.tax_rates.delete")
def tax_rates_delete(tax_id=None, **kwargs):
    """Delete a tax rate."""
    if not tax_id:
        return {"error": "tax_id required"}
    
    db = get_db()
    db.execute("DELETE FROM tax_rates WHERE id = ?", (tax_id,))
    db.commit()
    return {"deleted": True}


# --- Currencies ---

@register("core.accounting.currencies.list")
def currencies_list(**kwargs):
    """List all currencies."""
    db = get_db()
    rows = db.execute("SELECT * FROM currencies ORDER BY code").fetchall()
    return [dict(r) for r in rows]


@register("core.accounting.currencies.create")
def currencies_create(code=None, name=None, symbol=None, is_base=False, **kwargs):
    """Create a currency."""
    if not code or not name:
        return {"error": "code and name required"}
    
    db = get_db()
    
    # If this is base currency, unset others
    if is_base:
        db.execute("UPDATE currencies SET is_base = 0")
    
    cursor = db.execute(
        "INSERT INTO currencies (code, name, symbol, is_base) VALUES (?, ?, ?, ?)",
        (code.upper(), name, symbol, 1 if is_base else 0)
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "code": code.upper(), "name": name, "symbol": symbol}


@register("core.accounting.currencies.get_base")
def currencies_get_base(**kwargs):
    """Get base currency."""
    db = get_db()
    row = db.execute("SELECT * FROM currencies WHERE is_base = 1").fetchone()
    return dict(row) if row else {"code": "MXN", "name": "Peso Mexicano"}


# --- Exchange Rates ---

@register("core.accounting.exchange_rates.list")
def exchange_rates_list(currency_id=None, **kwargs):
    """List exchange rates."""
    db = get_db()
    query = """
        SELECT er.*, c.code as currency_code, c.name as currency_name
        FROM exchange_rates er
        JOIN currencies c ON er.currency_id = c.id
    """
    params = []
    if currency_id:
        query += " WHERE er.currency_id = ?"
        params.append(currency_id)
    query += " ORDER BY er.date DESC LIMIT 100"
    
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.accounting.exchange_rates.create")
def exchange_rates_create(currency_id=None, rate=None, date=None, **kwargs):
    """Create or update exchange rate."""
    if not currency_id or rate is None:
        return {"error": "currency_id and rate required"}
    
    db = get_db()
    
    try:
        rate_val = float(rate)
    except ValueError:
        return {"error": "invalid rate"}
    
    rate_date = date or datetime.utcnow().isoformat()[:10]
    
    # Upsert
    existing = db.execute(
        "SELECT id FROM exchange_rates WHERE currency_id = ? AND date = ?",
        (currency_id, rate_date)
    ).fetchone()
    
    if existing:
        db.execute("UPDATE exchange_rates SET rate = ? WHERE id = ?", (rate_val, existing["id"]))
    else:
        db.execute(
            "INSERT INTO exchange_rates (currency_id, rate, date) VALUES (?, ?, ?)",
            (currency_id, rate_val, rate_date)
        )
    db.commit()
    
    return {"currency_id": currency_id, "rate": rate_val, "date": rate_date}


@register("core.accounting.exchange_rates.convert")
def exchange_rates_convert(amount=None, from_currency=None, to_currency=None, date=None, **kwargs):
    """Convert amount between currencies."""
    if amount is None:
        return {"error": "amount required"}
    
    try:
        amount_val = float(amount)
    except ValueError:
        return {"error": "invalid amount"}
    
    db = get_db()
    rate_date = date or datetime.utcnow().isoformat()[:10]
    
    # Get from currency rate (default 1 if base)
    from_rate = 1.0
    if from_currency:
        from_curr = db.execute("SELECT id FROM currencies WHERE code = ?", (from_currency.upper(),)).fetchone()
        if from_curr:
            rate_row = db.execute(
                "SELECT rate FROM exchange_rates WHERE currency_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                (from_curr["id"], rate_date)
            ).fetchone()
            if rate_row:
                from_rate = rate_row["rate"]
    
    # Get to currency rate
    to_rate = 1.0
    if to_currency:
        to_curr = db.execute("SELECT id FROM currencies WHERE code = ?", (to_currency.upper(),)).fetchone()
        if to_curr:
            rate_row = db.execute(
                "SELECT rate FROM exchange_rates WHERE currency_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                (to_curr["id"], rate_date)
            ).fetchone()
            if rate_row:
                to_rate = rate_row["rate"]
    
    # Convert: amount / from_rate * to_rate
    converted = amount_val / from_rate * to_rate if from_rate != 0 else amount_val
    
    return {
        "original_amount": amount_val,
        "converted_amount": round(converted, 2),
        "from_currency": from_currency or "MXN",
        "to_currency": to_currency or "MXN",
        "rate": to_rate / from_rate if from_rate != 0 else 1,
    }


# --- DIOT (Declaración Informativa de Operaciones con Terceros) ---

@register("core.accounting.diot.generate")
def diot_generate(month=None, year=None, company_id=None, **kwargs):
    """Generate DIOT report for a period."""
    if not month or not year:
        return {"error": "month and year required"}
    
    db = get_db()
    
    # Get sales orders in period with tax info
    rows = db.execute("""
        SELECT 
            so.id as operation_id,
            c.nombre as provider_name,
            c.email as provider_email,
            so.total,
            so.tax,
            so.created_at,
            'sales' as operation_type
        FROM sales_orders so
        JOIN clientes c ON so.cliente_id = c.id
        WHERE so.status = 'invoiced'
        AND strftime('%m', so.created_at) = ?
        AND strftime('%Y', so.created_at) = ?
    """, (month.zfill(2), str(year))).fetchall()
    
    # Get purchase orders
    purchase_rows = db.execute("""
        SELECT 
            po.id as operation_id,
            po.supplier_name as provider_name,
            '' as provider_email,
            po.total,
            po.tax,
            po.created_at,
            'purchases' as operation_type
        FROM purchase_orders po
        WHERE po.status = 'received'
        AND strftime('%m', po.created_at) = ?
        AND strftime('%Y', po.created_at) = ?
    """, (month.zfill(2), str(year))).fetchall()
    
    all_operations = [dict(r) for r in rows] + [dict(r) for r in purchase_rows]
    
    # Group by provider
    provider_totals = {}
    for op in all_operations:
        name = op["provider_name"]
        if name not in provider_totals:
            provider_totals[name] = {
                "provider_name": name,
                "total_amount": 0,
                "tax_amount": 0,
                "operations": 0,
            }
        provider_totals[name]["total_amount"] += op["total"]
        provider_totals[name]["tax_amount"] += op["tax"]
        provider_totals[name]["operations"] += 1
    
    return {
        "month": month,
        "year": year,
        "total_operations": len(all_operations),
        "providers": list(provider_totals.values()),
        "generated_at": datetime.utcnow().isoformat(),
    }


@register("core.accounting.diot.providers")
def diot_providers(**kwargs):
    """List top providers for DIOT."""
    db = get_db()
    rows = db.execute("""
        SELECT 
            c.nombre,
            SUM(so.total) as total_amount,
            SUM(so.tax) as tax_amount,
            COUNT(*) as operations
        FROM sales_orders so
        JOIN clientes c ON so.cliente_id = c.id
        WHERE so.status = 'invoiced'
        GROUP BY c.id
        ORDER BY total_amount DESC
    """).fetchall()
    
    return [dict(r) for r in rows]


# --- Retenciones ---

@register("core.accounting.retentions.list")
def retentions_list(**kwargs):
    """List all retention concepts."""
    db = get_db()
    rows = db.execute("SELECT * FROM retention_concepts ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@register("core.accounting.retentions.calculate")
def retentions_calculate(amount=None, concept_id=None, **kwargs):
    """Calculate retention amount."""
    if amount is None or not concept_id:
        return {"error": "amount and concept_id required"}
    
    try:
        amount_val = float(amount)
    except ValueError:
        return {"error": "invalid amount"}
    
    db = get_db()
    concept = db.execute("SELECT * FROM retention_concepts WHERE id = ?", (concept_id,)).fetchone()
    if not concept:
        return {"error": "concept not found"}
    
    retention_amount = amount_val * concept["rate"] / 100
    
    return {
        "original_amount": amount_val,
        "concept": concept["name"],
        "rate": concept["rate"],
        "retention_amount": round(retention_amount, 2),
        "net_amount": round(amount_val - retention_amount, 2),
    }


# --- Fiscal Periods ---

@register("core.accounting.fiscal_periods.list")
def fiscal_periods_list(**kwargs):
    """List fiscal periods."""
    db = get_db()
    rows = db.execute("SELECT * FROM fiscal_periods ORDER BY year, month").fetchall()
    return [dict(r) for r in rows]


@register("core.accounting.fiscal_periods.create")
def fiscal_periods_create(month=None, year=None, **kwargs):
    """Create a fiscal period."""
    if not month or not year:
        return {"error": "month and year required"}
    
    db = get_db()
    
    # Check if exists
    existing = db.execute(
        "SELECT id FROM fiscal_periods WHERE month = ? AND year = ?",
        (month, year)
    ).fetchone()
    
    if existing:
        return {"error": "period already exists"}
    
    cursor = db.execute(
        "INSERT INTO fiscal_periods (month, year, status) VALUES (?, ?, 'open')",
        (month, year)
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "month": month, "year": year, "status": "open"}


# --- Tax Calculation Engine ---

@register("core.accounting.tax.calculate")
def tax_calculate(amount=None, tax_rate_id=None, quantity=1, discount=0, **kwargs):
    """Calculate tax for a line item."""
    if amount is None:
        return {"error": "amount required"}
    
    try:
        qty = float(quantity)
        price = float(amount)
        disc = float(discount)
    except ValueError:
        return {"error": "invalid numeric values"}
    
    subtotal = qty * price * (1 - disc / 100)
    
    tax_amount = 0
    tax_details = []
    
    if tax_rate_id:
        db = get_db()
        tax = db.execute("SELECT * FROM tax_rates WHERE id = ?", (tax_rate_id,)).fetchone()
        if tax:
            tax_amount = subtotal * tax["rate"] / 100
            tax_details.append({
                "id": tax["id"],
                "name": tax["name"],
                "rate": tax["rate"],
                "amount": round(tax_amount, 2),
                "type": tax["type"],
            })
    
    total = subtotal + tax_amount
    
    return {
        "quantity": qty,
        "unit_price": price,
        "discount": disc,
        "subtotal": round(subtotal, 2),
        "tax_amount": round(tax_amount, 2),
        "tax_details": tax_details,
        "total": round(total, 2),
    }


@register("core.accounting.tax.summary")
def tax_summary(month=None, year=None, **kwargs):
    """Tax summary for a period."""
    db = get_db()
    
    if month and year:
        date_filter = "AND strftime('%m', so.created_at) = ? AND strftime('%Y', so.created_at) = ?"
        params = [month.zfill(2), str(year)]
    else:
        date_filter = ""
        params = []
    
    # Sales tax (IVA cobrado)
    sales = db.execute(f"""
        SELECT COALESCE(SUM(tax), 0) as total_tax, COALESCE(SUM(subtotal), 0) as total_subtotal
        FROM sales_orders
        WHERE status = 'invoiced' {date_filter}
    """, params).fetchone()
    
    # Purchases tax (IVA pagado)
    purchases = db.execute(f"""
        SELECT COALESCE(SUM(tax), 0) as total_tax, COALESCE(SUM(subtotal), 0) as total_subtotal
        FROM purchase_orders
        WHERE status = 'received' {date_filter}
    """, params).fetchone()
    
    iva_cobrado = sales["total_tax"] if sales else 0
    iva_pagado = purchases["total_tax"] if purchases else 0
    
    return {
        "period": f"{year}-{month}" if month and year else "all",
        "iva_cobrado": iva_cobrado,
        "iva_pagado": iva_pagado,
        "iva_a_pagar": round(iva_cobrado - iva_pagado, 2),
        "sales_subtotal": sales["total_subtotal"] if sales else 0,
        "purchases_subtotal": purchases["total_subtotal"] if purchases else 0,
    }
