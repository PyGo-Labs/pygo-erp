"""PyGo ERP V2.0 — PDF Report handlers."""
import sys
import os

base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


def get_db():
    import sqlite3
    db_path = os.environ.get("PYGO_DB", "/tmp/pgerp.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@register("core.reports.pdf.invoice")
def reports_pdf_invoice(invoice_id=None, **kwargs):
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
