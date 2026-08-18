"""PyGo ERP V2.0 — Reports module.

Provides:
- Dashboard aggregation (cross-module)
- Sales reports (ventas por período, top productos, top clientes)
- Inventory reports (stock actual, movimientos, alertas)
- Financial reports (P&L, balance, cashflow)
- CRM reports (pipeline, conversion, actividad)
- Project reports (progreso, horas, costos)
- Export ready (JSON para PDF/Excel futuro)
"""
import sys
import os
from datetime import datetime, timedelta

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


# --- Main Dashboard ---

@register("core.reports.dashboard")
def reports_dashboard(**kwargs):
    """Main ERP dashboard — aggregated from all modules."""
    db = get_db()
    
    # Inventory
    productos = db.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    stock_total = db.execute("SELECT COALESCE(SUM(quantity), 0) FROM stock").fetchone()[0]
    stock_alerts = db.execute("""
        SELECT COUNT(*) FROM productos p
        LEFT JOIN stock s ON s.producto_id = p.id
        WHERE p.stock_minimo IS NOT NULL AND COALESCE(s.quantity, 0) < p.stock_minimo
    """).fetchone()[0]
    
    # Sales
    sales_month = db.execute("""
        SELECT COALESCE(SUM(total), 0) FROM sales_orders
        WHERE status = 'invoiced' AND created_at >= date('now', '-30 days')
    """).fetchone()[0]
    
    orders_pending = db.execute("""
        SELECT COUNT(*) FROM sales_orders WHERE status IN ('draft', 'confirmed')
    """).fetchone()[0]
    
    # Financial
    revenue = db.execute("""
        SELECT COALESCE(SUM(jel.credit) - SUM(jel.debit), 0)
        FROM journal_entry_lines jel
        JOIN accounts a ON jel.account_id = a.id AND a.type = 'revenue'
    """).fetchone()[0]
    
    expenses = db.execute("""
        SELECT COALESCE(SUM(jel.debit) - SUM(jel.credit), 0)
        FROM journal_entry_lines jel
        JOIN accounts a ON jel.account_id = a.id AND a.type = 'expense'
    """).fetchone()[0]
    
    # CRM
    total_leads = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    total_opps = db.execute("SELECT COUNT(*) FROM opportunities WHERE stage NOT IN ('won', 'lost')").fetchone()[0]
    pipeline_value = db.execute("SELECT COALESCE(SUM(value), 0) FROM opportunities WHERE stage NOT IN ('won', 'lost')").fetchone()[0]
    
    # Projects
    active_projects = db.execute("SELECT COUNT(*) FROM projects WHERE status IN ('planning', 'in_progress')").fetchone()[0]
    total_hours = db.execute("SELECT COALESCE(SUM(hours), 0) FROM timesheets").fetchone()[0]
    
    return {
        "inventory": {"productos": productos, "stock_total": stock_total, "alerts": stock_alerts},
        "sales": {"month_revenue": sales_month, "pending_orders": orders_pending},
        "financial": {"revenue": revenue, "expenses": expenses, "net_income": revenue - expenses},
        "crm": {"leads": total_leads, "opportunities": total_opps, "pipeline_value": pipeline_value},
        "projects": {"active": active_projects, "total_hours": total_hours},
    }


# --- Sales Reports ---

@register("core.reports.sales.by_period")
def sales_by_period(period="month", **kwargs):
    """Sales by period (daily, weekly, monthly)."""
    db = get_db()
    
    if period == "day":
        group_clause = "DATE(so.created_at)"
        date_format = "%Y-%m-%d"
    elif period == "week":
        group_clause = "STRFTIME('%Y-W%W', so.created_at)"
        date_format = "%Y-W%W"
    else:  # month
        group_clause = "STRFTIME('%Y-%m', so.created_at)"
        date_format = "%Y-%m"
    
    rows = db.execute(f"""
        SELECT {group_clause} as period,
               COUNT(*) as orders,
               COALESCE(SUM(total), 0) as revenue,
               COALESCE(AVG(total), 0) as avg_order
        FROM sales_orders so
        WHERE status = 'invoiced'
        GROUP BY period
        ORDER BY period DESC
        LIMIT 12
    """).fetchall()
    
    return [dict(r) for r in rows]


@register("core.reports.sales.top_products")
def top_products(limit=10, **kwargs):
    """Top selling products."""
    db = get_db()
    rows = db.execute("""
        SELECT p.codigo, p.nombre,
               COALESCE(SUM(soi.quantity), 0) as total_qty,
               COALESCE(SUM(soi.quantity * soi.precio_unitario), 0) as total_revenue
        FROM productos p
        LEFT JOIN sales_order_items soi ON soi.producto_id = p.id
        LEFT JOIN sales_orders so ON soi.order_id = so.id AND so.status = 'invoiced'
        GROUP BY p.id
        ORDER BY total_revenue DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


@register("core.reports.sales.top_clients")
def top_clients(limit=10, **kwargs):
    """Top clients by revenue."""
    db = get_db()
    rows = db.execute("""
        SELECT c.nombre, c.email,
               COUNT(so.id) as orders,
               COALESCE(SUM(so.total), 0) as total_revenue
        FROM clientes c
        LEFT JOIN sales_orders so ON so.cliente_id = c.id AND so.status = 'invoiced'
        GROUP BY c.id
        ORDER BY total_revenue DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# --- Inventory Reports ---

@register("core.reports.inventory.stock_status")
def stock_status(**kwargs):
    """Current stock status across warehouses."""
    db = get_db()
    rows = db.execute("""
        SELECT p.codigo, p.nombre,
               COALESCE(SUM(s.quantity), 0) as total_stock,
               p.stock_minimo,
               CASE WHEN p.stock_minimo IS NOT NULL AND COALESCE(SUM(s.quantity), 0) < p.stock_minimo
                    THEN 'LOW' ELSE 'OK' END as status
        FROM productos p
        LEFT JOIN stock s ON s.producto_id = p.id
        GROUP BY p.id
        ORDER BY total_stock ASC
    """).fetchall()
    return [dict(r) for r in rows]


@register("core.reports.inventory.movements")
def inventory_movements(days=30, **kwargs):
    """Recent inventory movements."""
    db = get_db()
    rows = db.execute("""
        SELECT sm.*, p.nombre as producto_nombre
        FROM stock_movements sm
        JOIN productos p ON sm.producto_id = p.id
        WHERE sm.created_at >= date('now', '-' || ? || ' days')
        ORDER BY sm.created_at DESC
    """, (days,)).fetchall()
    return [dict(r) for r in rows]


# --- Financial Reports ---

@register("core.reports.financial.cashflow")
def cashflow(months=6, **kwargs):
    """Cash flow by month (simplified)."""
    db = get_db()
    rows = db.execute("""
        SELECT STRFTIME('%Y-%m', je.date) as month,
               COALESCE(SUM(CASE WHEN a.type = 'revenue' THEN jel.credit - jel.debit ELSE 0 END), 0) as inflow,
               COALESCE(SUM(CASE WHEN a.type = 'expense' THEN jel.debit - jel.credit ELSE 0 END), 0) as outflow
        FROM journal_entry_lines jel
        JOIN journal_entries je ON jel.entry_id = je.id
        JOIN accounts a ON jel.account_id = a.id
        WHERE a.type IN ('revenue', 'expense')
        GROUP BY month
        ORDER BY month DESC
        LIMIT ?
    """, (months,)).fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["net"] = d["inflow"] - d["outflow"]
        result.append(d)
    return result


# --- CRM Reports ---

@register("core.reports.crm.conversion")
def crm_conversion(**kwargs):
    """Lead to opportunity conversion rate."""
    db = get_db()
    
    total_leads = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    converted = db.execute("SELECT COUNT(*) FROM leads WHERE status = 'converted'").fetchone()[0]
    won = db.execute("SELECT COUNT(*) FROM opportunities WHERE stage = 'won'").fetchone()[0]
    
    return {
        "total_leads": total_leads,
        "converted": converted,
        "won": won,
        "lead_to_opp_rate": (converted / total_leads * 100) if total_leads > 0 else 0,
        "opp_to_won_rate": (won / converted * 100) if converted > 0 else 0,
    }


@register("core.reports.crm.activity_summary")
def activity_summary(**kwargs):
    """Activity summary by type."""
    db = get_db()
    rows = db.execute("""
        SELECT type, COUNT(*) as count
        FROM activities
        GROUP BY type
        ORDER BY count DESC
    """).fetchall()
    return [dict(r) for r in rows]


# --- Project Reports ---

@register("core.reports.projects.progress")
def project_progress(**kwargs):
    """Project progress overview."""
    db = get_db()
    rows = db.execute("""
        SELECT p.name, p.status,
               COUNT(t.id) as total_tasks,
               SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as completed_tasks,
               COALESCE(SUM(ts.hours), 0) as total_hours
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        LEFT JOIN timesheets ts ON ts.task_id = t.id
        GROUP BY p.id
    """).fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        total = d["total_tasks"]
        d["progress_pct"] = (d["completed_tasks"] / total * 100) if total > 0 else 0
        result.append(d)
    return result


# --- Export ---

@register("core.reports.export")
def report_export(report_type=None, format="json", **kwargs):
    """Export report data (JSON for now, ready for PDF/Excel)."""
    if not report_type:
        return {"error": "report_type required"}
    
    db = get_db()
    data = {}
    
    if report_type == "sales":
        data = sales_by_period(**kwargs)
    elif report_type == "inventory":
        data = stock_status()
    elif report_type == "financial":
        data = cashflow()
    elif report_type == "crm":
        data = crm_conversion()
    elif report_type == "projects":
        data = project_progress()
    elif report_type == "full":
        data = reports_dashboard()
    else:
        return {"error": f"unknown report: {report_type}"}
    
    return {
        "report": report_type,
        "format": format,
        "generated_at": datetime.utcnow().isoformat(),
        "data": data,
    }
