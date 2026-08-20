"""PyGo ERP — Multicurrency: document rates and realised FX differences.

A document issued at one rate and settled at another produces a real gain or
loss. Without recording it, a company that invoices in two currencies cannot
close its books.
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


def base_currency(db):
    row = db.execute("SELECT code FROM currencies WHERE is_base = 1 LIMIT 1").fetchone()
    return row["code"] if row else "USD"


def rate_for(db, currency, date=None):
    """Rate to convert `currency` into the base currency.

    exchange_rates stores currency_id (FK to currencies), not the code, so the
    lookup joins. Falls back to the most recent rate, then to 1.0.
    """
    if not currency:
        return 1.0
    if currency == base_currency(db):
        return 1.0

    if date:
        row = db.execute(
            "SELECT r.rate FROM exchange_rates r JOIN currencies c ON c.id = r.currency_id "
            "WHERE c.code = ? AND r.date <= ? ORDER BY r.date DESC LIMIT 1",
            (currency, str(date)[:10])).fetchone()
        if row:
            return float(row["rate"])
    row = db.execute(
        "SELECT r.rate FROM exchange_rates r JOIN currencies c ON c.id = r.currency_id "
        "WHERE c.code = ? ORDER BY r.date DESC LIMIT 1", (currency,)).fetchone()
    return float(row["rate"]) if row else 1.0


# ------------------------------------------------------------------- handlers

@register("core.fx.rate")
def fx_rate(currency=None, date=None, **kwargs):
    """Resolve the rate a document should use."""
    if not currency:
        return {"error": "currency required"}
    db = get_db()
    base = base_currency(db)
    rate = rate_for(db, currency, date)
    db.close()
    return {"currency": currency, "base_currency": base, "rate": rate,
            "date": str(date)[:10] if date else None}


@register("core.fx.convert")
def fx_convert(amount=None, from_currency=None, to_currency=None, date=None, **kwargs):
    """Convert between any two configured currencies via the base currency."""
    if amount is None or not from_currency or not to_currency:
        return {"error": "amount, from_currency and to_currency required"}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be numeric"}

    db = get_db()
    base = base_currency(db)
    from_rate = rate_for(db, from_currency, date)
    to_rate = rate_for(db, to_currency, date)
    db.close()
    if to_rate == 0:
        return {"error": f"no usable rate for {to_currency}"}

    in_base = amount * from_rate
    result = in_base / to_rate
    return {"amount": amount, "from_currency": from_currency,
            "to_currency": to_currency, "base_currency": base,
            "from_rate": from_rate, "to_rate": to_rate,
            "amount_base": round(in_base, 6), "result": round(result, 6)}


@register("core.fx.set_document_rate")
def fx_set_document_rate(document_type=None, document_id=None, currency=None,
                         exchange_rate=None, date=None, **kwargs):
    """Stamp a document with its currency and the rate in force."""
    tables = {"invoice": "facturas", "sales_order": "sales_orders",
              "purchase_order": "purchase_orders", "payment": "payments",
              "journal_entry": "journal_entries"}
    if document_type not in tables or not document_id:
        return {"error": "valid document_type and document_id required",
                "allowed": list(tables)}

    table = tables[document_type]
    db = get_db()
    cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (document_id,)).fetchone()
    if not row:
        db.close()
        return {"error": f"{document_type} {document_id} not found"}

    cur = currency or (row["currency"] if "currency" in cols else None) or base_currency(db)
    rate = float(exchange_rate) if exchange_rate is not None else rate_for(db, cur, date)

    sets, params = [], []
    if "currency" in cols:
        sets.append("currency = ?")
        params.append(cur)
    if "exchange_rate" in cols:
        sets.append("exchange_rate = ?")
        params.append(rate)
    if not sets:
        db.close()
        return {"error": f"{table} has no currency columns"}

    params.append(document_id)
    db.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", params)
    db.commit()
    db.close()
    return {"document_type": document_type, "document_id": document_id,
            "currency": cur, "exchange_rate": rate}


@register("core.fx.record_difference")
def fx_record_difference(document_type=None, document_id=None, payment_id=None,
                         amount_currency=None, payment_rate=None, date=None,
                         company_id=None, **kwargs):
    """Record the realised gain/loss when a payment settles at a new rate."""
    tables = {"invoice": "facturas", "purchase_order": "purchase_orders",
              "sales_order": "sales_orders"}
    if document_type not in tables or not document_id or amount_currency is None:
        return {"error": "document_type, document_id and amount_currency required",
                "allowed": list(tables)}

    db = get_db()
    table = tables[document_type]
    cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (document_id,)).fetchone()
    if not row:
        db.close()
        return {"error": f"{document_type} {document_id} not found"}

    currency = (row["currency"] if "currency" in cols else None) or base_currency(db)
    doc_rate = float(row["exchange_rate"] or 0) if "exchange_rate" in cols else 0.0
    if not doc_rate:
        doc_rate = rate_for(db, currency, row["fecha"] if "fecha" in cols else None)
    pay_rate = float(payment_rate) if payment_rate is not None else rate_for(db, currency, date)

    try:
        amount_currency = float(amount_currency)
    except (TypeError, ValueError):
        db.close()
        return {"error": "amount_currency must be numeric"}

    difference = round(amount_currency * (pay_rate - doc_rate), 6)
    if abs(difference) < 0.000001:
        db.close()
        return {"recorded": False, "reason": "no rate difference",
                "currency": currency, "document_rate": doc_rate,
                "payment_rate": pay_rate, "difference_base": 0.0}

    gain_or_loss = "gain" if difference > 0 else "loss"
    cur = db.execute(
        "INSERT INTO fx_differences (document_type, document_id, payment_id, currency, "
        "document_rate, payment_rate, amount_currency, difference_base, gain_or_loss, "
        "company_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (document_type, document_id, payment_id, currency, doc_rate, pay_rate,
         amount_currency, difference, gain_or_loss, company_id))
    db.commit()
    diff_id = cur.lastrowid
    db.close()
    return {"recorded": True, "id": diff_id, "currency": currency,
            "document_rate": doc_rate, "payment_rate": pay_rate,
            "amount_currency": amount_currency,
            "difference_base": difference, "gain_or_loss": gain_or_loss}


@register("core.fx.differences")
def fx_differences(document_type=None, date_from=None, date_to=None, **kwargs):
    """Realised FX differences with gain/loss totals."""
    db = get_db()
    where, params = [], []
    if document_type:
        where.append("document_type = ?")
        params.append(document_type)
    if date_from:
        where.append("entry_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("entry_date <= ?")
        params.append(date_to + " 23:59:59")
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    rows = db.execute(
        f"SELECT * FROM fx_differences {clause} ORDER BY entry_date DESC LIMIT 200",
        params).fetchall()
    totals = db.execute(
        f"SELECT gain_or_loss, SUM(difference_base) AS total FROM fx_differences "
        f"{clause} GROUP BY gain_or_loss", params).fetchall()
    db.close()

    summary = {r["gain_or_loss"]: round(float(r["total"] or 0), 2) for r in totals}
    net = round(summary.get("gain", 0.0) + summary.get("loss", 0.0), 2)
    return {"differences": [dict(r) for r in rows],
            "total_gain": summary.get("gain", 0.0),
            "total_loss": summary.get("loss", 0.0),
            "net_effect": net}


@register("core.fx.exposure")
def fx_exposure(**kwargs):
    """Open balances grouped by currency — what is exposed to rate moves."""
    db = get_db()
    base = base_currency(db)
    cols = {r[1] for r in db.execute("PRAGMA table_info(facturas)")}
    currency_col = "currency" if "currency" in cols else None
    if not currency_col:
        db.close()
        return {"base_currency": base, "by_currency": [], "total_base": 0.0}

    rows = db.execute(
        "SELECT COALESCE(currency, ?) AS cur, "
        "SUM(total - COALESCE(amount_paid, 0)) AS open_balance, COUNT(*) AS docs "
        "FROM facturas WHERE (total - COALESCE(amount_paid, 0)) > 0.01 "
        "GROUP BY COALESCE(currency, ?)", (base, base)).fetchall()

    out, total_base = [], 0.0
    for r in rows:
        rate = rate_for(db, r["cur"])
        in_base = round(float(r["open_balance"] or 0) * rate, 2)
        total_base += in_base
        out.append({"currency": r["cur"], "documents": r["docs"],
                    "open_balance": round(float(r["open_balance"] or 0), 2),
                    "rate": rate, "open_balance_base": in_base,
                    "is_base": r["cur"] == base})
    db.close()
    return {"base_currency": base, "by_currency": out,
            "total_base": round(total_base, 2)}
