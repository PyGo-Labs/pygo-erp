"""PyGo ERP V2.0 — Reports package.

Provides:
- Dashboard aggregation (cross-module)
- Sales reports
- Inventory reports
- PDF generation (Invoice, Quote, Ticket)
"""
import os
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import sys
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

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
    """Main ERP dashboard."""
    db = get_db()
    productos = db.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    stock_total = db.execute("SELECT COALESCE(SUM(quantity), 0) FROM stock").fetchone()[0]
    sales_month = db.execute("SELECT COALESCE(SUM(total), 0) FROM sales_orders WHERE status = 'invoiced'").fetchone()[0]
    orders_pending = db.execute("SELECT COUNT(*) FROM sales_orders WHERE status IN ('draft', 'confirmed')").fetchone()[0]
    total_leads = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    total_opps = db.execute("SELECT COUNT(*) FROM opportunities WHERE stage NOT IN ('won', 'lost')").fetchone()[0]
    pipeline_value = db.execute("SELECT COALESCE(SUM(value), 0) FROM opportunities WHERE stage NOT IN ('won', 'lost')").fetchone()[0]
    active_projects = db.execute("SELECT COUNT(*) FROM projects WHERE status IN ('planning', 'in_progress')").fetchone()[0]
    total_hours = db.execute("SELECT COALESCE(SUM(hours), 0) FROM timesheets").fetchone()[0]
    return {
        "inventory": {"productos": productos, "stock_total": stock_total},
        "sales": {"month_revenue": sales_month, "pending_orders": orders_pending},
        "financial": {"revenue": 0, "expenses": 0, "net_income": 0},
        "crm": {"leads": total_leads, "opportunities": total_opps, "pipeline_value": pipeline_value},
        "projects": {"active": active_projects, "total_hours": total_hours},
    }


# --- Sales Reports ---

@register("core.reports.sales.by_period")
def sales_by_period(period="month", **kwargs):
    """Sales by period."""
    db = get_db()
    rows = db.execute("""
        SELECT STRFTIME('%Y-%m', created_at) as period,
               COUNT(*) as orders,
               COALESCE(SUM(total), 0) as revenue
        FROM sales_orders
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


# --- Export ---

@register("core.reports.export")
def report_export(report_type=None, **kwargs):
    """Export report data."""
    if not report_type:
        return {"error": "report_type required"}
    
    db = get_db()
    data = {}
    
    if report_type == "full":
        data = reports_dashboard()
    elif report_type == "sales":
        data = sales_by_period()
    else:
        return {"error": f"unknown report: {report_type}"}
    
    return {
        "report": report_type,
        "format": "json",
        "generated_at": datetime.utcnow().isoformat(),
        "data": data,
    }


# --- PDF Reports ---

@register("core.reports.pdf.invoice")
def reports_pdf_invoice(invoice_id=None, **kwargs):
    """Generate invoice PDF."""
    if not invoice_id:
        return {"error": "invoice_id required"}
    from core.reports.pdf import PDFReportGenerator
    db = get_db()
    invoice = db.execute("SELECT * FROM facturas WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return {"error": "invoice not found"}
    client = db.execute("SELECT * FROM clientes WHERE id = ?", (invoice["cliente_id"],)).fetchone()
    order = db.execute("SELECT * FROM sales_orders WHERE id = ?", (invoice["sales_order_id"],)).fetchone()
    items = []
    if order:
        for oi in db.execute("SELECT * FROM sales_order_items WHERE order_id = ?", (order["id"],)).fetchall():
            product = db.execute("SELECT * FROM productos WHERE id = ?", (oi["producto_id"],)).fetchone()
            items.append({
                "codigo": product["codigo"] if product else "-",
                "nombre": product["nombre"] if product else "Producto",
                "quantity": oi["quantity"],
                "precio_unitario": oi["precio_unitario"],
            })
    generator = PDFReportGenerator()
    os.makedirs("/tmp/pgerp_uploads", exist_ok=True)
    output_path = f"/tmp/pgerp_uploads/invoice_{invoice_id}.pdf"
    generator.generate_invoice({
        "id": invoice_id,
        "folio": f"FAC-{int(invoice_id):06d}",
        "date": invoice["fecha"],
        "client": {"name": client["nombre"] if client else "", "email": client["email"] if client else ""},
        "items": items,
        "subtotal": invoice["total"] * 0.86,
        "tax": invoice["total"] * 0.14,
        "total": invoice["total"],
    }, output_path)
    return {"pdf_path": output_path, "invoice_id": invoice_id}


@register("core.reports.pdf.quote")
def reports_pdf_quote(quote_id=None, **kwargs):
    """Generate quote PDF."""
    if not quote_id:
        return {"error": "quote_id required"}
    from core.reports.pdf import PDFReportGenerator
    db = get_db()
    quote = db.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    if not quote:
        return {"error": "quote not found"}
    client = db.execute("SELECT * FROM clientes WHERE id = ?", (quote["cliente_id"],)).fetchone()
    items = []
    for qi in db.execute("SELECT * FROM quote_items WHERE quote_id = ?", (quote_id,)).fetchall():
        product = db.execute("SELECT * FROM productos WHERE id = ?", (qi["producto_id"],)).fetchone()
        items.append({
            "codigo": product["codigo"] if product else "-",
            "nombre": product["nombre"] if product else "Producto",
            "quantity": qi["quantity"],
            "precio_unitario": qi["precio_unitario"],
        })
    generator = PDFReportGenerator()
    os.makedirs("/tmp/pgerp_uploads", exist_ok=True)
    output_path = f"/tmp/pgerp_uploads/quote_{quote_id}.pdf"
    quote_dict = dict(quote)
    generator.generate_quote({
        "id": quote_id,
        "folio": f"COT-{int(quote_id):06d}",
        "date": quote["created_at"],
        "valid_until": quote["valid_until"] if quote["valid_until"] else "",
        "client": {"name": client["nombre"] if client else "", "email": client["email"] if client else ""},
        "items": items,
        "notes": quote_dict.get("notes", ""),
    }, output_path)
    return {"pdf_path": output_path, "quote_id": quote_id}


@register("core.reports.pdf.ticket")
def reports_pdf_ticket(order_id=None, **kwargs):
    """Generate sales ticket PDF."""
    if not order_id:
        return {"error": "order_id required"}
    from core.reports.pdf import PDFReportGenerator
    db = get_db()
    order = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "order not found"}
    client = db.execute("SELECT * FROM clientes WHERE id = ?", (order["cliente_id"],)).fetchone()
    items = []
    for oi in db.execute("SELECT * FROM sales_order_items WHERE order_id = ?", (order_id,)).fetchall():
        product = db.execute("SELECT * FROM productos WHERE id = ?", (oi["producto_id"],)).fetchone()
        items.append({
            "codigo": product["codigo"] if product else "-",
            "nombre": product["nombre"] if product else "Producto",
            "quantity": oi["quantity"],
            "precio_unitario": oi["precio_unitario"],
        })
    generator = PDFReportGenerator()
    os.makedirs("/tmp/pgerp_uploads", exist_ok=True)
    output_path = f"/tmp/pgerp_uploads/ticket_{order_id}.pdf"
    generator.generate_ticket({
        "id": order_id,
        "folio": f"TKT-{int(order_id):06d}",
        "date": order["created_at"],
        "client": {"name": client["nombre"] if client else ""},
        "items": items,
        "total": order["total"],
    }, output_path)
    return {"pdf_path": output_path, "order_id": order_id}
