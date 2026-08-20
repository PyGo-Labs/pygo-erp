"""PyGo ERP V2.0 — Accounting module.

Provides:
- Chart of Accounts (plan de cuentas)
- Journal Entries (asientos contables)
- Trial Balance (balance de comprobación)
- Income Statement (estado de resultados / P&L)
- Balance Sheet (balance general)
- Auto-journal entries from sales/purchases
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.auth import Session, User
from core.registry import register


def get_db():
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# --- Chart of Accounts ---

@register("core.accounting.accounts.list")
def accounts_list(type=None, **kwargs):
    """List chart of accounts."""
    db = get_db()
    query = "SELECT * FROM accounts"
    params = []
    if type:
        query += " WHERE type = ?"
        params.append(type)
    query += " ORDER BY code"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.accounting.accounts.create")
def accounts_create(code=None, name=None, type=None, parent_id=None, token=None, **kwargs):
    """Create an account (admin only)."""
    if not code or not name or not type:
        return {"error": "code, name, type required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role != "admin":
            return {"error": "admin only"}
    
    valid_types = ["asset", "liability", "equity", "revenue", "expense"]
    if type not in valid_types:
        return {"error": f"type must be one of {valid_types}"}
    
    cursor = db.execute(
        "INSERT INTO accounts (code, name, type, parent_id) VALUES (?, ?, ?, ?)",
        (code, name, type, parent_id)
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "code": code, "name": name, "type": type}


@register("core.accounting.accounts.seed")
def accounts_seed(**kwargs):
    """Seed default chart of accounts."""
    db = get_db()
    
    if db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0:
        return {"message": "accounts already seeded"}
    
    # Default chart of accounts (simplified)
    default_accounts = [
        # Assets (Activo)
        ("1000", "Activo", "asset", None),
        ("1100", "Activo Circulante", "asset", 1),
        ("1101", "Caja", "asset", 2),
        ("1102", "Bancos", "asset", 2),
        ("1103", "Cuentas por Cobrar", "asset", 2),
        ("1104", "Inventario", "asset", 2),
        ("1200", "Activo Fijo", "asset", 1),
        ("1201", "Equipo de Cómputo", "asset", 7),
        # Liabilities (Pasivo)
        ("2000", "Pasivo", "liability", None),
        ("2100", "Pasivo Circulante", "liability", 10),
        ("2101", "Cuentas por Pagar", "liability", 11),
        ("2102", "IVA por Pagar", "liability", 11),
        # Equity (Capital)
        ("3000", "Capital", "equity", None),
        ("3100", "Capital Social", "equity", 14),
        ("3200", "Utilidades Retenidas", "equity", 14),
        # Revenue (Ingresos)
        ("4000", "Ingresos", "revenue", None),
        ("4100", "Ventas", "revenue", 17),
        ("4200", "Otros Ingresos", "revenue", 17),
        # Expenses (Gastos)
        ("5000", "Gastos", "expense", None),
        ("5100", "Costo de Ventas", "expense", 20),
        ("5200", "Gastos Operativos", "expense", 20),
        ("5201", "Sueldos", "expense", 22),
        ("5202", "Renta", "expense", 22),
        ("5203", "Servicios", "expense", 22),
    ]
    
    # Insert accounts without parent references first, then update
    account_ids = {}
    for i, (code, name, type_, parent_idx) in enumerate(default_accounts):
        cursor = db.execute(
            "INSERT INTO accounts (code, name, type) VALUES (?, ?, ?)",
            (code, name, type_)
        )
        account_ids[i + 1] = cursor.lastrowid
    
    # Update parent references
    for i, (code, name, type_, parent_idx) in enumerate(default_accounts):
        if parent_idx and parent_idx in account_ids:
            db.execute("UPDATE accounts SET parent_id = ? WHERE id = ?",
                       (account_ids[parent_idx], account_ids[i + 1]))
    
    db.commit()
    return {"seeded": len(default_accounts)}


# --- Journal Entries ---

@register("core.accounting.journal.list")
def journal_list(from_date=None, to_date=None, **kwargs):
    """List journal entries."""
    db = get_db()
    query = """
        SELECT je.*, je.description as entry_description,
        je.debit_total, je.credit_total
        FROM journal_entries je
    """
    filters = []
    params = []
    if from_date:
        filters.append("je.date >= ?")
        params.append(from_date)
    if to_date:
        filters.append("je.date <= ?")
        params.append(to_date)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY je.date DESC, je.id DESC"
    rows = db.execute(query, params).fetchall()
    
    result = []
    for row in rows:
        entry = dict(row)
        lines = db.execute("SELECT * FROM journal_entry_lines WHERE entry_id = ?", (entry["id"],)).fetchall()
        entry["lines"] = [dict(l) for l in lines]
        result.append(entry)
    return result


@register("core.accounting.journal.create")
def journal_create(description=None, lines=None, date=None, token=None, **kwargs):
    """Create a balanced journal entry."""
    if not description or not lines:
        return {"error": "description and lines required"}
    
    if not isinstance(lines, list) or len(lines) < 2:
        return {"error": "at least 2 line items required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user or user.role not in ("admin", "manager"):
            return {"error": "forbidden"}
    
    # Validate balanced
    debit_total = sum(float(l.get("debit", 0)) for l in lines)
    credit_total = sum(float(l.get("credit", 0)) for l in lines)
    
    if abs(debit_total - credit_total) > 0.01:
        return {"error": f"unbalanced: debit {debit_total} != credit {credit_total}"}
    
    entry_date = date or datetime.utcnow().isoformat()[:10]
    
    cursor = db.execute(
        """INSERT INTO journal_entries (date, description, debit_total, credit_total, user_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (entry_date, description, debit_total, credit_total,
         user.id if token else None, datetime.utcnow().isoformat())
    )
    entry_id = cursor.lastrowid
    
    for line in lines:
        db.execute(
            """INSERT INTO journal_entry_lines (entry_id, account_id, debit, credit, description)
               VALUES (?, ?, ?, ?, ?)""",
            (entry_id, line.get("account_id"), float(line.get("debit", 0)),
             float(line.get("credit", 0)), line.get("description", ""))
        )
    
    db.commit()
    return {"id": entry_id, "total": debit_total}


@register("core.accounting.journal.from_sale")
def journal_from_sale(order_id=None, token=None, **kwargs):
    """Auto-generate journal entry from sales order."""
    if not order_id:
        return {"error": "order_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    order = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "order not found"}
    
    # Get default accounts
    accounts = {}
    for acc in db.execute("SELECT * FROM accounts").fetchall():
        accounts[acc["code"]] = acc["id"]
    
    if "1103" not in accounts or "4101" not in accounts:
        return {"error": "accounts not seeded"}
    
    lines = [
        {"account_id": accounts["1103"], "debit": order["total"], "credit": 0, "description": f"Ventas order #{order_id}"},
        {"account_id": accounts["4101"], "debit": 0, "credit": order["subtotal"], "description": "Ingreso por venta"},
    ]
    
    if order["tax"] > 0 and "2102" in accounts:
        lines[1]["credit"] = order["subtotal"]
        lines.append({"account_id": accounts["2102"], "debit": 0, "credit": order["tax"], "description": "IVA cobrado"})
    
    return journal_create(description=f"Venta #{order_id}", lines=lines, token=token)


# --- Trial Balance ---

@register("core.accounting.trial_balance")
def trial_balance(**kwargs):
    """Trial Balance — all account balances."""
    db = get_db()
    rows = db.execute("""
        SELECT a.code, a.name, a.type,
               COALESCE(SUM(jel.debit), 0) as total_debit,
               COALESCE(SUM(jel.credit), 0) as total_credit,
               COALESCE(SUM(jel.debit), 0) - COALESCE(SUM(jel.credit), 0) as balance
        FROM accounts a
        LEFT JOIN journal_entry_lines jel ON jel.account_id = a.id
        LEFT JOIN journal_entries je ON je.id = jel.entry_id
        GROUP BY a.id
        ORDER BY a.code
    """).fetchall()
    return [dict(r) for r in rows]


# --- Income Statement (P&L) ---

@register("core.accounting.income_statement")
def income_statement(**kwargs):
    """Income Statement — Revenue minus Expenses."""
    db = get_db()
    
    revenue = db.execute("""
        SELECT COALESCE(SUM(jel.credit) - SUM(jel.debit), 0) as total
        FROM journal_entry_lines jel
        JOIN accounts a ON jel.account_id = a.id
        WHERE a.type = 'revenue'
    """).fetchone()["total"]
    
    expenses = db.execute("""
        SELECT COALESCE(SUM(jel.debit) - SUM(jel.credit), 0) as total
        FROM journal_entry_lines jel
        JOIN accounts a ON jel.account_id = a.id
        WHERE a.type = 'expense'
    """).fetchone()["total"]
    
    return {
        "revenue": revenue,
        "expenses": expenses,
        "net_income": revenue - expenses,
    }


# --- Balance Sheet ---

@register("core.accounting.balance_sheet")
def balance_sheet(**kwargs):
    """Balance Sheet — Assets = Liabilities + Equity."""
    db = get_db()
    
    assets = db.execute("""
        SELECT COALESCE(SUM(jel.debit) - SUM(jel.credit), 0) as total
        FROM journal_entry_lines jel
        JOIN accounts a ON jel.account_id = a.id
        WHERE a.type = 'asset'
    """).fetchone()["total"]
    
    liabilities = db.execute("""
        SELECT COALESCE(SUM(jel.credit) - SUM(jel.debit), 0) as total
        FROM journal_entry_lines jel
        JOIN accounts a ON jel.account_id = a.id
        WHERE a.type = 'liability'
    """).fetchone()["total"]
    
    equity = db.execute("""
        SELECT COALESCE(SUM(jel.credit) - SUM(jel.debit), 0) as total
        FROM journal_entry_lines jel
        JOIN accounts a ON jel.account_id = a.id
        WHERE a.type = 'equity'
    """).fetchone()["total"]
    
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "balanced": abs(assets - liabilities - equity) < 0.01,
    }


# --- Account Details ---

@register("core.accounting.accounts.detail")
def accounts_detail(account_id=None, **kwargs):
    """Get account details with transactions."""
    if not account_id:
        return {"error": "account_id required"}
    
    db = get_db()
    account = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        return {"error": "not found"}
    
    lines = db.execute("""
        SELECT jel.*, je.date, je.description as entry_description
        FROM journal_entry_lines jel
        JOIN journal_entries je ON jel.entry_id = je.id
        WHERE jel.account_id = ?
        ORDER BY je.date DESC
    """, (account_id,)).fetchall()
    
    result = dict(account)
    result["transactions"] = [dict(l) for l in lines]
    return result
