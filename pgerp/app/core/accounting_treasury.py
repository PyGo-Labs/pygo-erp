"""PyGo ERP — Payments, AR/AP aging and bank reconciliation."""
import os
import sys
import json
from datetime import datetime

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


def _parse(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return None
    return x


def _next_folio(doc_type):
    try:
        from core.commercial_terms import sequences_next
        return sequences_next(doc_type=doc_type).get("folio")
    except Exception:
        return None


def _days_between(d1, d2):
    try:
        a = datetime.strptime(str(d1)[:10], "%Y-%m-%d")
        b = datetime.strptime(str(d2)[:10], "%Y-%m-%d")
        return (b - a).days
    except Exception:
        return 0


# --- Payments ---

@register("core.payments.list")
def payments_list(partner_type=None, partner_id=None, **kwargs):
    db = get_db()
    sql = "SELECT * FROM payments WHERE 1=1"
    params = []
    if partner_type:
        sql += " AND partner_type = ?"
        params.append(partner_type)
    if partner_id:
        sql += " AND partner_id = ?"
        params.append(partner_id)
    sql += " ORDER BY id DESC"
    rows = db.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        allocs = db.execute(
            "SELECT * FROM payment_allocations WHERE payment_id = ?", (r["id"],)
        ).fetchall()
        d["allocations"] = [dict(a) for a in allocs]
        d["allocated"] = round(sum(float(a["amount"]) for a in allocs), 2)
        d["unallocated"] = round(float(r["amount"]) - d["allocated"], 2)
        out.append(d)
    return out


@register("core.payments.register")
def payments_register(
    amount=None, partner_type="customer", partner_id=None,
    payment_type="inbound", payment_date=None, method="transfer",
    bank_account_id=None, reference=None, allocations=None,
    currency="USD", company_id=None, **kwargs
):
    """Register a payment and optionally allocate it to documents.

    allocations = [{"document_type":"invoice","document_id":1,"amount":500}]
    """
    if amount is None:
        return {"error": "amount required"}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be numeric"}
    if amount <= 0:
        return {"error": "amount must be > 0"}
    if payment_type not in ("inbound", "outbound"):
        return {"error": "payment_type must be inbound|outbound"}

    allocations = _parse(allocations) or []
    alloc_total = sum(float(a.get("amount", 0)) for a in allocations)
    if alloc_total > amount + 1e-9:
        return {"error": f"allocations {alloc_total} exceed payment amount {amount}"}

    db = get_db()
    folio = _next_folio("credit_note" if payment_type == "outbound" else "invoice")
    pdate = payment_date or datetime.utcnow().strftime("%Y-%m-%d")

    try:
        cur = db.execute(
            "INSERT INTO payments (folio, payment_type, partner_type, partner_id, amount, currency, "
            "payment_date, method, bank_account_id, reference, company_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (folio, payment_type, partner_type, partner_id, amount, currency,
             pdate, method, bank_account_id, reference, company_id),
        )
        payment_id = cur.lastrowid

        for a in allocations:
            doc_type = a.get("document_type")
            doc_id = a.get("document_id")
            amt = float(a.get("amount", 0))
            if not doc_type or not doc_id or amt <= 0:
                continue
            db.execute(
                "INSERT INTO payment_allocations (payment_id, document_type, document_id, amount) "
                "VALUES (?, ?, ?, ?)",
                (payment_id, doc_type, doc_id, amt),
            )
            if doc_type == "invoice":
                inv = db.execute("SELECT * FROM facturas WHERE id = ?", (doc_id,)).fetchone()
                if inv:
                    paid = float(inv["amount_paid"] or 0) + amt
                    total = float(inv["total"] or 0)
                    status = "paid" if paid >= total - 0.01 else ("partial" if paid > 0 else "unpaid")
                    db.execute(
                        "UPDATE facturas SET amount_paid = ?, payment_status = ? WHERE id = ?",
                        (round(paid, 2), status, doc_id),
                    )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"payment failed: {e}"}
    finally:
        db.close()

    return {
        "payment_id": payment_id,
        "folio": folio,
        "amount": amount,
        "payment_type": payment_type,
        "allocated": round(alloc_total, 2),
        "unallocated": round(amount - alloc_total, 2),
        "payment_date": pdate,
    }


@register("core.ar.aging")
def ar_aging(as_of=None, **kwargs):
    """Accounts receivable aging buckets."""
    db = get_db()
    today = as_of or datetime.utcnow().strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT f.*, c.nombre AS cliente_nombre FROM facturas f "
        "LEFT JOIN clientes c ON c.id = f.cliente_id "
        "WHERE COALESCE(f.payment_status,'unpaid') != 'paid'"
    ).fetchall()

    buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "over_90": 0.0}
    detail = []
    for r in rows:
        total = float(r["total"] or 0)
        paid = float(r["amount_paid"] or 0)
        balance = round(total - paid, 2)
        if balance <= 0:
            continue
        due = r["due_date"] or r["fecha"]
        overdue = _days_between(due, today)
        if overdue <= 0:
            bucket = "current"
        elif overdue <= 30:
            bucket = "1_30"
        elif overdue <= 60:
            bucket = "31_60"
        elif overdue <= 90:
            bucket = "61_90"
        else:
            bucket = "over_90"
        buckets[bucket] += balance
        detail.append({
            "invoice_id": r["id"],
            "folio": r["folio"],
            "customer": r["cliente_nombre"],
            "total": total,
            "paid": paid,
            "balance": balance,
            "due_date": due,
            "days_overdue": max(overdue, 0),
            "bucket": bucket,
        })

    return {
        "as_of": today,
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "total_receivable": round(sum(buckets.values()), 2),
        "invoices": sorted(detail, key=lambda d: -d["days_overdue"]),
    }


@register("core.ap.aging")
def ap_aging(as_of=None, **kwargs):
    """Accounts payable aging based on purchase orders received but unpaid."""
    db = get_db()
    today = as_of or datetime.utcnow().strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT po.*, s.name AS supplier_name FROM purchase_orders po "
        "LEFT JOIN suppliers s ON s.id = po.supplier_id "
        "WHERE po.status IN ('received','partially_received')"
    ).fetchall()

    buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "over_90": 0.0}
    detail = []
    for r in rows:
        total = float(r["total"] or 0)
        paid_row = db.execute(
            "SELECT COALESCE(SUM(pa.amount),0) FROM payment_allocations pa "
            "JOIN payments p ON p.id = pa.payment_id "
            "WHERE pa.document_type = 'purchase_order' AND pa.document_id = ?",
            (r["id"],),
        ).fetchone()
        paid = float(paid_row[0] or 0)
        balance = round(total - paid, 2)
        if balance <= 0:
            continue
        ref_date = r["expected_date"] or r["created_at"]
        overdue = _days_between(ref_date, today)
        if overdue <= 0:
            bucket = "current"
        elif overdue <= 30:
            bucket = "1_30"
        elif overdue <= 60:
            bucket = "31_60"
        elif overdue <= 90:
            bucket = "61_90"
        else:
            bucket = "over_90"
        buckets[bucket] += balance
        detail.append({
            "purchase_order_id": r["id"],
            "folio": r["folio"],
            "supplier": r["supplier_name"],
            "total": total,
            "paid": round(paid, 2),
            "balance": balance,
            "days_overdue": max(overdue, 0),
            "bucket": bucket,
        })

    return {
        "as_of": today,
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "total_payable": round(sum(buckets.values()), 2),
        "orders": sorted(detail, key=lambda d: -d["days_overdue"]),
    }


# --- Bank reconciliation ---

@register("core.bank.accounts.list")
def bank_accounts_list(**kwargs):
    db = get_db()
    rows = db.execute("SELECT * FROM bank_accounts WHERE is_active = 1 ORDER BY name").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        moves = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM bank_statement_lines WHERE bank_account_id = ?",
            (r["id"],),
        ).fetchone()[0]
        d["current_balance"] = round(float(r["opening_balance"] or 0) + float(moves or 0), 2)
        out.append(d)
    return out


@register("core.bank.accounts.create")
def bank_accounts_create(
    name=None, bank_name=None, account_number=None, iban=None,
    currency="USD", account_id=None, opening_balance=0, company_id=None, **kwargs
):
    if not name:
        return {"error": "name required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO bank_accounts (name, bank_name, account_number, iban, currency, account_id, "
        "opening_balance, company_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, bank_name, account_number, iban, currency, account_id,
         float(opening_balance or 0), company_id),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "currency": currency}


@register("core.bank.statement.import_lines")
def bank_statement_import(bank_account_id=None, lines=None, reference=None, **kwargs):
    """Import bank statement lines. lines = [{"line_date":"2026-08-01","description":"...","amount":500}]"""
    if not bank_account_id:
        return {"error": "bank_account_id required"}
    lines = _parse(lines)
    if not lines:
        return {"error": "lines required"}

    db = get_db()
    if not db.execute("SELECT 1 FROM bank_accounts WHERE id = ?", (bank_account_id,)).fetchone():
        return {"error": "bank account not found"}

    try:
        cur = db.execute(
            "INSERT INTO bank_statements (bank_account_id, reference, status) VALUES (?, ?, 'open')",
            (bank_account_id, reference),
        )
        statement_id = cur.lastrowid
        imported = 0
        for l in lines:
            db.execute(
                "INSERT INTO bank_statement_lines (statement_id, bank_account_id, line_date, "
                "description, reference, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (statement_id, bank_account_id, l.get("line_date"), l.get("description"),
                 l.get("reference"), float(l.get("amount", 0))),
            )
            imported += 1
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"import failed: {e}"}
    finally:
        db.close()

    return {"statement_id": statement_id, "bank_account_id": bank_account_id, "imported": imported}


@register("core.bank.reconcile.auto")
def bank_reconcile_auto(bank_account_id=None, tolerance=0.01, **kwargs):
    """Auto-match unreconciled bank lines against payments by amount and date proximity."""
    if not bank_account_id:
        return {"error": "bank_account_id required"}
    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError):
        tolerance = 0.01

    db = get_db()
    unmatched = db.execute(
        "SELECT * FROM bank_statement_lines WHERE bank_account_id = ? AND matched = 0",
        (bank_account_id,),
    ).fetchall()
    payments = db.execute(
        "SELECT * FROM payments WHERE bank_account_id = ? OR bank_account_id IS NULL",
        (bank_account_id,),
    ).fetchall()

    used = set()
    matched = []
    for line in unmatched:
        line_amt = float(line["amount"] or 0)
        best = None
        best_gap = None
        for p in payments:
            if p["id"] in used:
                continue
            p_amt = float(p["amount"] or 0)
            signed = p_amt if p["payment_type"] == "inbound" else -p_amt
            if abs(signed - line_amt) > tolerance:
                continue
            gap = abs(_days_between(p["payment_date"], line["line_date"]))
            if best is None or gap < best_gap:
                best = p
                best_gap = gap
        if best:
            used.add(best["id"])
            db.execute(
                "UPDATE bank_statement_lines SET matched = 1, matched_payment_id = ?, matched_type = 'payment' "
                "WHERE id = ?",
                (best["id"], line["id"]),
            )
            matched.append({
                "line_id": line["id"],
                "line_date": line["line_date"],
                "amount": line_amt,
                "payment_id": best["id"],
                "payment_folio": best["folio"],
                "date_gap_days": best_gap,
            })
    db.commit()

    still = db.execute(
        "SELECT COUNT(*) FROM bank_statement_lines WHERE bank_account_id = ? AND matched = 0",
        (bank_account_id,),
    ).fetchone()[0]

    return {
        "bank_account_id": bank_account_id,
        "matched_count": len(matched),
        "matched": matched,
        "still_unmatched": still,
    }


@register("core.bank.reconcile.status")
def bank_reconcile_status(bank_account_id=None, **kwargs):
    """Reconciliation status for a bank account."""
    if not bank_account_id:
        return {"error": "bank_account_id required"}
    db = get_db()
    acc = db.execute("SELECT * FROM bank_accounts WHERE id = ?", (bank_account_id,)).fetchone()
    if not acc:
        return {"error": "bank account not found"}

    total = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM bank_statement_lines WHERE bank_account_id = ?",
        (bank_account_id,),
    ).fetchone()
    mat = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM bank_statement_lines "
        "WHERE bank_account_id = ? AND matched = 1",
        (bank_account_id,),
    ).fetchone()
    unmatched_rows = db.execute(
        "SELECT * FROM bank_statement_lines WHERE bank_account_id = ? AND matched = 0 ORDER BY line_date",
        (bank_account_id,),
    ).fetchall()

    return {
        "bank_account": acc["name"],
        "currency": acc["currency"],
        "opening_balance": float(acc["opening_balance"] or 0),
        "statement_balance": round(float(acc["opening_balance"] or 0) + float(total[1] or 0), 2),
        "lines_total": total[0],
        "lines_matched": mat[0],
        "lines_unmatched": total[0] - mat[0],
        "amount_matched": round(float(mat[1] or 0), 2),
        "amount_unmatched": round(float(total[1] or 0) - float(mat[1] or 0), 2),
        "reconciled_pct": round(mat[0] / total[0] * 100, 1) if total[0] else 0,
        "unmatched_lines": [dict(r) for r in unmatched_rows],
    }
