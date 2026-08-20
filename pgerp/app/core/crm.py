"""PyGo ERP V2.0 — CRM module.

Provides:
- Leads (prospectos) management
- Opportunities (oportunidades de venta)
- Sales Pipeline (pipeline de ventas)
- Contacts (contactos)
- Activities (llamadas, emails, reuniones, notas)
- Campaigns (campañas de marketing)
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.auth import Session, User
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


# --- Leads ---

@register("core.crm.leads.list")
def leads_list(status=None, **kwargs):
    """List leads (optionally filtered by status)."""
    db = get_db()
    query = "SELECT * FROM leads"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.crm.leads.create")
def leads_create(name=None, email=None, phone=None, company=None, source=None, notes=None, token=None, **kwargs):
    """Create a new lead."""
    if not name:
        return {"error": "name required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
        user_id = user.id
    else:
        user_id = None
    
    cursor = db.execute(
        """INSERT INTO leads (name, email, phone, company, source, notes, status, user_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?)""",
        (name, email, phone, company, source, notes, user_id, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "status": "new"}


@register("core.crm.leads.update")
def leads_update(lead_id=None, token=None, **kwargs):
    """Update a lead."""
    if not lead_id:
        return {"error": "lead_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    row = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    
    allowed = ["name", "email", "phone", "company", "source", "notes", "status"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [lead_id]
        db.execute(f"UPDATE leads SET {sets} WHERE id = ?", vals)
        db.commit()
    
    return dict(db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())


@register("core.crm.leads.convert")
def leads_convert(lead_id=None, token=None, **kwargs):
    """Convert lead to opportunity."""
    if not lead_id:
        return {"error": "lead_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
    
    lead = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not lead:
        return {"error": "not found"}
    
    # Create opportunity from lead
    cursor = db.execute(
        """INSERT INTO opportunities (name, company, contact_name, contact_email, contact_phone,
           value, stage, probability, source, expected_close_date, user_id, lead_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'qualified', 50, ?, date('now', '+30 days'), ?, ?)""",
        (lead["name"], lead["company"], lead["name"], lead["email"], lead["phone"],
         kwargs.get("value", 0), lead["source"], user.id if token else None, lead_id,
         datetime.utcnow().isoformat())
    )
    
    # Update lead status
    db.execute("UPDATE leads SET status = 'converted' WHERE id = ?", (lead_id,))
    db.commit()
    
    return {"converted": True, "opportunity_id": cursor.lastrowid}


# --- Opportunities ---

@register("core.crm.opportunities.list")
def opportunities_list(stage=None, **kwargs):
    """List opportunities (optionally filtered by stage)."""
    db = get_db()
    query = "SELECT * FROM opportunities"
    params = []
    if stage:
        query += " WHERE stage = ?"
        params.append(stage)
    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.crm.opportunities.create")
def opportunities_create(name=None, value=0, stage="prospecting", token=None, **kwargs):
    """Create an opportunity."""
    if not name:
        return {"error": "name required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
        user_id = user.id
    else:
        user_id = None
    
    cursor = db.execute(
        """INSERT INTO opportunities (name, company, contact_name, contact_email, value, stage,
           probability, source, expected_close_date, user_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, date('now', '+30 days'), ?, ?)""",
        (name, kwargs.get("company"), kwargs.get("contact_name"), kwargs.get("contact_email"),
         value, stage, kwargs.get("probability", 50), kwargs.get("source"),
         user_id, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid, "stage": stage}


@register("core.crm.opportunities.update")
def opportunities_update(opportunity_id=None, token=None, **kwargs):
    """Update an opportunity."""
    if not opportunity_id:
        return {"error": "opportunity_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    row = db.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    
    allowed = ["name", "company", "contact_name", "contact_email", "value", "stage",
               "probability", "source", "expected_close_date"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [opportunity_id]
        db.execute(f"UPDATE opportunities SET {sets} WHERE id = ?", vals)
        db.commit()
    
    return dict(db.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone())


@register("core.crm.opportunities.won")
def opportunities_won(opportunity_id=None, token=None):
    """Mark opportunity as won → creates sales order."""
    if not opportunity_id:
        return {"error": "opportunity_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
    
    opp = db.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
    if not opp:
        return {"error": "not found"}
    
    # Create cliente if not exists
    cliente_id = None
    if opp["contact_email"]:
        existing = db.execute("SELECT * FROM clientes WHERE email = ?", (opp["contact_email"],)).fetchone()
        if not existing:
            cursor = db.execute("INSERT INTO clientes (nombre, email) VALUES (?, ?)",
                              (opp["contact_name"] or opp["name"], opp["contact_email"]))
            cliente_id = cursor.lastrowid
        else:
            cliente_id = existing["id"]
    
    db.execute("UPDATE opportunities SET stage = 'won' WHERE id = ?", (opportunity_id,))
    db.commit()
    
    return {"won": True, "opportunity_id": opportunity_id, "cliente_id": cliente_id}


@register("core.crm.opportunities.lost")
def opportunities_lost(opportunity_id=None, reason=None, token=None):
    """Mark opportunity as lost."""
    if not opportunity_id:
        return {"error": "opportunity_id required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
    
    db.execute("UPDATE opportunities SET stage = 'lost', notes = COALESCE(notes, '') || ? WHERE id = ?",
               (f" [LOST: {reason}]", opportunity_id))
    db.commit()
    
    return {"lost": True, "opportunity_id": opportunity_id}


# --- Pipeline ---

@register("core.crm.pipeline.summary")
def pipeline_summary(**kwargs):
    """Pipeline summary — opportunities by stage."""
    db = get_db()
    rows = db.execute("""
        SELECT stage, COUNT(*) as count, SUM(value) as total_value, AVG(probability) as avg_probability
        FROM opportunities
        WHERE stage NOT IN ('won', 'lost')
        GROUP BY stage
        ORDER BY
            CASE stage
                WHEN 'prospecting' THEN 1
                WHEN 'qualification' THEN 2
                WHEN 'proposal' THEN 3
                WHEN 'negotiation' THEN 4
                WHEN 'qualified' THEN 5
                ELSE 6
            END
    """).fetchall()
    return [dict(r) for r in rows]


@register("core.crm.pipeline.funnel")
def pipeline_funnel(**kwargs):
    """Full funnel view (leads + opportunities)."""
    db = get_db()
    
    leads_by_status = db.execute("""
        SELECT status, COUNT(*) as count FROM leads GROUP BY status
    """).fetchall()
    
    opps_by_stage = db.execute("""
        SELECT stage, COUNT(*) as count, SUM(value) as value FROM opportunities GROUP BY stage
    """).fetchall()
    
    total_leads = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    total_opps = db.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    won_opps = db.execute("SELECT COALESCE(SUM(value), 0) FROM opportunities WHERE stage = 'won'").fetchone()[0]
    
    return {
        "leads_by_status": [dict(r) for r in leads_by_status],
        "opps_by_stage": [dict(r) for r in opps_by_stage],
        "totals": {"leads": total_leads, "opportunities": total_opps, "won_value": won_opps}
    }


# --- Activities ---

@register("core.crm.activities.list")
def activities_list(related_type=None, related_id=None, **kwargs):
    """List activities."""
    db = get_db()
    query = "SELECT * FROM activities"
    filters = []
    params = []
    if related_type:
        filters.append("related_type = ?")
        params.append(related_type)
    if related_id:
        filters.append("related_id = ?")
        params.append(related_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY created_at DESC LIMIT 100"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@register("core.crm.activities.create")
def activities_create(type=None, subject=None, description=None, related_type=None, related_id=None, token=None, **kwargs):
    """Create an activity (call, email, meeting, note)."""
    if not type or not subject:
        return {"error": "type and subject required"}
    
    db = get_db()
    if token:
        session = Session.find_by_token(db, token)
        if not session:
            return {"error": "not authenticated"}
        user = User.find_by_id(db, session.user_id)
        if not user:
            return {"error": "user not found"}
        user_id = user.id
    else:
        user_id = None
    
    cursor = db.execute(
        """INSERT INTO activities (type, subject, description, related_type, related_id, user_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (type, subject, description, related_type, related_id, user_id, datetime.utcnow().isoformat())
    )
    db.commit()
    
    return {"id": cursor.lastrowid}


# --- Contacts ---

@register("core.crm.contacts.list")
def contacts_list(**kwargs):
    """List CRM contacts (from clientes + leads)."""
    db = get_db()
    
    clientes = db.execute("SELECT *, 'cliente' as source FROM clientes").fetchall()
    leads = db.execute("SELECT *, 'lead' as source FROM leads").fetchall()
    
    return [dict(r) for r in list(clientes) + list(leads)]


# --- Dashboard stats ---

@register("core.crm.dashboard")
def crm_dashboard(**kwargs):
    """CRM dashboard stats."""
    db = get_db()
    
    return {
        "total_leads": db.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
        "new_leads": db.execute("SELECT COUNT(*) FROM leads WHERE status = 'new'").fetchone()[0],
        "total_opportunities": db.execute("SELECT COUNT(*) FROM opportunities WHERE stage NOT IN ('won', 'lost')").fetchone()[0],
        "pipeline_value": db.execute("SELECT COALESCE(SUM(value), 0) FROM opportunities WHERE stage NOT IN ('won', 'lost')").fetchone()[0],
        "won_this_month": db.execute("SELECT COALESCE(SUM(value), 0) FROM opportunities WHERE stage = 'won'").fetchone()[0],
    }
