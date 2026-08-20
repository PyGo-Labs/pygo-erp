"""PyGo ERP V2.0 — Email notifications.

Sends notifications via SMTP for important events:
- New order created
- Invoice generated
- Stock alert
- Payment received
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import sys
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

from core.registry import register


# --- SMTP Config ---

def get_smtp_config():
    """Get SMTP configuration from environment."""
    return {
        "host": os.environ.get("PYGO_SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("PYGO_SMTP_PORT", "587")),
        "user": os.environ.get("PYGO_SMTP_USER", ""),
        "password": os.environ.get("PYGO_SMTP_PASS", ""),
        "from_email": os.environ.get("PYGO_SMTP_FROM", os.environ.get("PYGO_SMTP_USER", "")),
        "use_tls": os.environ.get("PYGO_SMTP_TLS", "true").lower() == "true",
    }


def send_email(to_email=None, subject=None, body=None, html_body=None, attachments=None, **kwargs):
    """Send an email via SMTP."""
    if not to_email or not subject:
        return {"error": "to_email and subject required"}
    
    config = get_smtp_config()
    
    if not config["user"] or not config["password"]:
        return {
            "error": "SMTP not configured",
            "config": {
                "host": config["host"],
                "port": config["port"],
                "user": config["user"] or "(not set)",
                "has_password": bool(config["password"]),
            },
            "tip": "Set PYGO_SMTP_USER and PYGO_SMTP_PASS env vars"
        }
    
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = config["from_email"]
        msg["To"] = to_email
        msg["Subject"] = subject
        
        if body:
            msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))
        
        if attachments:
            for filepath in attachments:
                if os.path.exists(filepath):
                    with open(filepath, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(filepath)}")
                    msg.attach(part)
        
        with smtplib.SMTP(config["host"], config["port"]) as server:
            if config["use_tls"]:
                server.starttls()
            server.login(config["user"], config["password"])
            server.send_message(msg)
        
        return {"sent": True, "to": to_email, "subject": subject}
    
    except Exception as e:
        return {"error": str(e)}


# --- Notification Handlers ---

@register("core.notifications.order_created")
def notify_order_created(order_id=None, to_email=None, **kwargs):
    """Notify that a sales order was created."""
    if not order_id:
        return {"error": "order_id required"}
    
    def get_db():
        """Use the request-scoped connection owned by core.main when available."""
        try:
            from core.main import get_db as _shared
            return _shared()
        except Exception:
            pass
        import sqlite3
        conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"),
                               timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn
    
    db = get_db()
    order = db.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return {"error": "order not found"}
    
    client = db.execute("SELECT * FROM clientes WHERE id = ?", (order["cliente_id"],)).fetchone()
    
    html = f"""
    <html><body>
    <h2>Orden de Venta Creada</h2>
    <p>Se ha creado la orden <b>#{order_id}</b></p>
    <p>Cliente: {client["nombre"] if client else "N/A"}</p>
    <p>Total: ${order["total"]:,.2f}</p>
    <p>Estado: {order["status"]}</p>
    <hr><p><small>PyGo ERP V2.0</small></p>
    </body></html>
    """
    
    return send_email(
        to_email=to_email,
        subject=f"Orden de Venta #{order_id} Creada",
        html_body=html,
    )


@register("core.notifications.invoice_generated")
def notify_invoice_generated(invoice_id=None, to_email=None, pdf_path=None, **kwargs):
    """Notify that an invoice was generated."""
    if not invoice_id:
        return {"error": "invoice_id required"}
    
    def get_db():
        import sqlite3
        conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"))
        conn.row_factory = sqlite3.Row
        return conn
    
    db = get_db()
    invoice = db.execute("SELECT * FROM facturas WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return {"error": "invoice not found"}
    
    client = db.execute("SELECT * FROM clientes WHERE id = ?", (invoice["cliente_id"],)).fetchone()
    
    html = f"""
    <html><body>
    <h2>Factura Generada</h2>
    <p>Se ha generado la factura <b>#{invoice_id}</b></p>
    <p>Cliente: {client["nombre"] if client else "N/A"}</p>
    <p>Total: ${invoice["total"]:,.2f}</p>
    <p>Fecha: {invoice["fecha"]}</p>
    <hr><p><small>PyGo ERP V2.0</small></p>
    </body></html>
    """
    
    return send_email(
        to_email=to_email,
        subject=f"Factura #{invoice_id} Generada",
        html_body=html,
        attachments=[pdf_path] if pdf_path else None,
    )


@register("core.notifications.stock_alert")
def notify_stock_alert(producto_id=None, to_email=None, **kwargs):
    """Notify stock below minimum."""
    if not producto_id:
        return {"error": "producto_id required"}
    
    def get_db():
        import sqlite3
        conn = sqlite3.connect(os.environ.get("PYGO_DB", "/tmp/pgerp.db"))
        conn.row_factory = sqlite3.Row
        return conn
    
    db = get_db()
    product = db.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
    if not product:
        return {"error": "product not found"}
    
    stock = db.execute(
        "SELECT COALESCE(SUM(quantity), 0) as total FROM stock WHERE producto_id = ?",
        (producto_id,)
    ).fetchone()["total"]
    
    html = f"""
    <html><body>
    <h2>⚠️ Alerta de Stock</h2>
    <p>El producto <b>{product["nombre"]}</b> está bajo mínimo.</p>
    <p>Stock actual: {stock}</p>
    <p>Stock mínimo: {product["stock_minimo"]}</p>
    <hr><p><small>PyGo ERP V2.0</small></p>
    </body></html>
    """
    
    return send_email(
        to_email=to_email,
        subject=f"Alerta de Stock: {product['nombre']}",
        html_body=html,
    )


@register("core.notifications.send_test")
def notify_test(to_email=None, **kwargs):
    """Send a test email."""
    return send_email(
        to_email=to_email,
        subject="PyGo ERP - Email Test",
        html_body="<html><body><h2>✅ Email Test OK</h2><p>PyGo ERP V2.0 - Notifications working</p></body></html>",
    )


@register("core.notifications.config")
def notify_config(**kwargs):
    """Check email configuration status."""
    config = get_smtp_config()
    return {
        "smtp_host": config["host"],
        "smtp_port": config["port"],
        "smtp_user": config["user"] or "(not set)",
        "has_password": bool(config["password"]),
        "configured": bool(config["user"] and config["password"]),
        "tip": "Set PYGO_SMTP_HOST, PYGO_SMTP_PORT, PYGO_SMTP_USER, PYGO_SMTP_PASS"
    }
