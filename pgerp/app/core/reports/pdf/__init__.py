"""PyGo ERP V2.0 — PDF Report Generator.

Generates professional PDF documents:
- Factura (Invoice)
- Cotización (Quote)
- Ticket (Receipt)
"""
import os
from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


class PDFReportGenerator:
    """Generate PDF reports for PyGo ERP."""
    
    def __init__(self, company_name="PyGo ERP", company_rfc="ABC123456XYZ"):
        self.company_name = company_name
        self.company_rfc = company_rfc
        self.styles = getSampleStyleSheet()
        
        # Custom styles
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#2563EB'),
            spaceAfter=2,
        ))
        self.styles.add(ParagraphStyle(
            name='CompanyInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.grey,
        ))
        self.styles.add(ParagraphStyle(
            name='DocTitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#0F172A'),
            alignment=TA_RIGHT,
            spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name='DocNumber',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.grey,
            alignment=TA_RIGHT,
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading3'],
            fontSize=10,
            textColor=colors.HexColor('#2563EB'),
            spaceBefore=10,
            spaceAfter=4,
        ))
        self.styles.add(ParagraphStyle(
            name='TotalLabel',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
        ))
        self.styles.add(ParagraphStyle(
            name='TotalValue',
            parent=self.styles['Normal'],
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2563EB'),
            alignment=TA_RIGHT,
        ))
    
    def generate_invoice(self, data, output_path=None):
        """Generate a professional invoice PDF."""
        if output_path is None:
            output_path = f"/tmp/invoice_{data.get('id', 'draft')}.pdf"
        
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )
        
        elements = []
        
        # Header
        elements.append(Paragraph(self.company_name, self.styles['CompanyName']))
        elements.append(Paragraph(f"RFC: {self.company_rfc}", self.styles['CompanyInfo']))
        elements.append(Spacer(1, 12))
        
        # Title
        elements.append(Paragraph("FACTURA", self.styles['DocTitle']))
        elements.append(Paragraph(f"Folio: {data.get('folio', 'SIN FOLIO')}", self.styles['DocNumber']))
        elements.append(Paragraph(f"Fecha: {data.get('date', datetime.now().strftime('%d/%m/%Y'))}", self.styles['DocNumber']))
        elements.append(Spacer(1, 20))
        
        # Client info
        elements.append(Paragraph("DATOS DEL CLIENTE", self.styles['SectionHeader']))
        client = data.get('client', {})
        client_info = f"""
        <b>{client.get('name', 'Cliente General')}</b><br/>
        {client.get('address', '')}<br/>
        {client.get('email', '')}
        """
        elements.append(Paragraph(client_info, self.styles['Normal']))
        elements.append(Spacer(1, 16))
        
        # Items table
        elements.append(Paragraph("CONCEPTOS", self.styles['SectionHeader']))
        
        items_data = [['Código', 'Descripción', 'Cantidad', 'P. Unitario', 'Importe']]
        
        subtotal = 0
        for item in data.get('items', []):
            qty = item.get('quantity', 1)
            price = item.get('precio_unitario', item.get('price', 0))
            importe = qty * price
            subtotal += importe
            items_data.append([
                item.get('codigo', '-'),
                item.get('nombre', item.get('description', '')),
                str(qty),
                f"${price:,.2f}",
                f"${importe:,.2f}",
            ])
        
        table = Table(items_data, colWidths=[70, 200, 60, 80, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))
        
        # Totals
        tax = data.get('tax', subtotal * 0.16)
        total = data.get('total', subtotal + tax)
        
        totals_data = [
            ['', '', '', 'Subtotal:', f"${subtotal:,.2f}"],
            ['', '', '', 'IVA (16%):', f"${tax:,.2f}"],
            ['', '', '', 'TOTAL:', f"${total:,.2f}"],
        ]
        totals_table = Table(totals_data, colWidths=[70, 200, 60, 80, 80])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (3, -1), (-1, -1), 12),
            ('TEXTCOLOR', (3, -1), (-1, -1), colors.HexColor('#2563EB')),
            ('LINEABOVE', (3, -1), (-1, -1), 1, colors.HexColor('#2563EB')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(totals_table)
        
        # Footer
        elements.append(Spacer(1, 30))
        footer_text = """
        <para alignment="center" fontSize="8" textColor="grey">
        Este documento es una representación impresa de un CFDI.<br/>
        PyGo ERP V2.0 — Sistema de Facturación Electrónica
        </para>
        """
        elements.append(Paragraph(footer_text, self.styles['Normal']))
        
        doc.build(elements)
        return output_path
    
    def generate_quote(self, data, output_path=None):
        """Generate a professional quote PDF."""
        if output_path is None:
            output_path = f"/tmp/quote_{data.get('id', 'draft')}.pdf"
        
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )
        
        elements = []
        
        # Header
        elements.append(Paragraph(self.company_name, self.styles['CompanyName']))
        elements.append(Paragraph(f"RFC: {self.company_rfc}", self.styles['CompanyInfo']))
        elements.append(Spacer(1, 12))
        
        # Title
        elements.append(Paragraph("COTIZACIÓN", self.styles['DocTitle']))
        elements.append(Paragraph(f"Folio: {data.get('folio', 'SIN FOLIO')}", self.styles['DocNumber']))
        elements.append(Paragraph(f"Fecha: {data.get('date', datetime.now().strftime('%d/%m/%Y'))}", self.styles['DocNumber']))
        elements.append(Paragraph(f"Vigente hasta: {data.get('valid_until', 'N/A')}", self.styles['DocNumber']))
        elements.append(Spacer(1, 20))
        
        # Client info
        elements.append(Paragraph("CLIENTE", self.styles['SectionHeader']))
        client = data.get('client', {})
        client_info = f"""
        <b>{client.get('name', '')}</b><br/>
        {client.get('email', '')}
        """
        elements.append(Paragraph(client_info, self.styles['Normal']))
        elements.append(Spacer(1, 16))
        
        # Items
        elements.append(Paragraph("DESCRIPCIÓN", self.styles['SectionHeader']))
        
        items_data = [['Cantidad', 'Concepto', 'P. Unitario', 'Total']]
        
        subtotal = 0
        for item in data.get('items', []):
            qty = item.get('quantity', 1)
            price = item.get('precio_unitario', item.get('price', 0))
            total_line = qty * price
            subtotal += total_line
            items_data.append([
                str(qty),
                item.get('nombre', item.get('description', '')),
                f"${price:,.2f}",
                f"${total_line:,.2f}",
            ])
        
        table = Table(items_data, colWidths=[60, 250, 80, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))
        
        # Totals
        tax = subtotal * 0.16
        total = subtotal + tax
        
        totals_data = [
            ['', '', 'Subtotal:', f"${subtotal:,.2f}"],
            ['', '', 'IVA (16%):', f"${tax:,.2f}"],
            ['', '', 'TOTAL:', f"${total:,.2f}"],
        ]
        totals_table = Table(totals_data, colWidths=[60, 250, 80, 80])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (2, -1), (-1, -1), 12),
            ('TEXTCOLOR', (2, -1), (-1, -1), colors.HexColor('#2563EB')),
            ('LINEABOVE', (2, -1), (-1, -1), 1, colors.HexColor('#2563EB')),
        ]))
        elements.append(totals_table)
        
        # Notes
        elements.append(Spacer(1, 20))
        notes = data.get('notes', '')
        if notes:
            elements.append(Paragraph("NOTAS", self.styles['SectionHeader']))
            elements.append(Paragraph(notes, self.styles['Normal']))
        
        # Footer
        elements.append(Spacer(1, 30))
        footer = """
        <para alignment="center" fontSize="8" textColor="grey">
        Esta cotización es válida por 30 días a partir de la fecha de emisión.<br/>
        PyGo ERP V2.0
        </para>
        """
        elements.append(Paragraph(footer, self.styles['Normal']))
        
        doc.build(elements)
        return output_path
    
    def generate_ticket(self, data, output_path=None):
        """Generate a small receipt/ticket PDF."""
        if output_path is None:
            output_path = f"/tmp/ticket_{data.get('id', 'draft')}.pdf"
        
        doc = SimpleDocTemplate(
            output_path,
            pagesize=(80 * mm, 200 * mm),
            rightMargin=10,
            leftMargin=10,
            topMargin=10,
            bottomMargin=10,
        )
        
        elements = []
        
        # Header
        elements.append(Paragraph(f"<b>{self.company_name}</b>", self.styles['Normal']))
        elements.append(Paragraph(f"RFC: {self.company_rfc}", self.styles['CompanyInfo']))
        elements.append(Spacer(1, 8))
        
        # Title
        elements.append(Paragraph("<b>NOTA DE VENTA</b>", self.styles['DocTitle']))
        elements.append(Paragraph(f"Folio: {data.get('folio', 'N/A')}", self.styles['DocNumber']))
        elements.append(Paragraph(f"Fecha: {data.get('date', datetime.now().strftime('%d/%m/%Y %H:%M'))}", self.styles['DocNumber']))
        elements.append(Spacer(1, 12))
        
        # Items
        for item in data.get('items', []):
            qty = item.get('quantity', 1)
            price = item.get('precio_unitario', item.get('price', 0))
            line_total = qty * price
            item_text = f"{qty}x {item.get('nombre', '')}"
            elements.append(Paragraph(item_text, self.styles['Normal']))
            elements.append(Paragraph(f"${line_total:,.2f}", self.styles['DocNumber']))
        
        elements.append(Spacer(1, 12))
        
        # Total
        total = data.get('total', 0)
        elements.append(Paragraph(f"<b>TOTAL: ${total:,.2f}</b>", self.styles['TotalValue']))
        
        elements.append(Spacer(1, 20))
        footer = """
        <para alignment="center" fontSize="7" textColor="grey">
        Gracias por su compra<br/>
        PyGo ERP V2.0
        </para>
        """
        elements.append(Paragraph(footer, self.styles['Normal']))
        
        doc.build(elements)
        return output_path
