"""PyGo ERP — HR core: departments, positions, employees, contracts."""
import os
import sys
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base)
sys.path.insert(0, os.path.join(base, "app"))

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


# --- Departments ---

@register("core.hr.departments.list")
def departments_list(**kwargs):
    db = get_db()
    rows = db.execute(
        "SELECT d.*, c.name AS cost_center_name, "
        "(SELECT COUNT(*) FROM employees e WHERE e.department_id = d.id AND e.status='active') AS headcount "
        "FROM departments d LEFT JOIN cost_centers c ON c.id = d.cost_center_id ORDER BY d.name"
    ).fetchall()
    return [dict(r) for r in rows]


@register("core.hr.departments.create")
def departments_create(name=None, code=None, parent_id=None, manager_id=None,
                       cost_center_id=None, company_id=None, **kwargs):
    if not name:
        return {"error": "name required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO departments (name, code, parent_id, manager_id, cost_center_id, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, code, parent_id, manager_id, cost_center_id, company_id),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name, "code": code}


# --- Positions ---

@register("core.hr.positions.list")
def positions_list(**kwargs):
    db = get_db()
    rows = db.execute(
        "SELECT p.*, d.name AS department_name FROM job_positions p "
        "LEFT JOIN departments d ON d.id = p.department_id "
        "WHERE p.is_active = 1 ORDER BY p.title"
    ).fetchall()
    return [dict(r) for r in rows]


@register("core.hr.positions.create")
def positions_create(title=None, department_id=None, min_salary=0, max_salary=0, **kwargs):
    if not title:
        return {"error": "title required"}
    db = get_db()
    cur = db.execute(
        "INSERT INTO job_positions (title, department_id, min_salary, max_salary) VALUES (?, ?, ?, ?)",
        (title, department_id, float(min_salary or 0), float(max_salary or 0)),
    )
    db.commit()
    return {"id": cur.lastrowid, "title": title}


# --- Employees ---

@register("core.hr.employees.list")
def employees_list(department_id=None, status="active", **kwargs):
    db = get_db()
    sql = (
        "SELECT e.*, d.name AS department_name, p.title AS position_title, "
        "m.first_name || ' ' || m.last_name AS manager_name "
        "FROM employees e "
        "LEFT JOIN departments d ON d.id = e.department_id "
        "LEFT JOIN job_positions p ON p.id = e.position_id "
        "LEFT JOIN employees m ON m.id = e.manager_id WHERE 1=1"
    )
    params = []
    if status:
        sql += " AND e.status = ?"
        params.append(status)
    if department_id:
        sql += " AND e.department_id = ?"
        params.append(department_id)
    sql += " ORDER BY e.last_name, e.first_name"
    rows = db.execute(sql, params).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        contract = db.execute(
            "SELECT wage, wage_period, currency, contract_type FROM contracts "
            "WHERE employee_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (r["id"],),
        ).fetchone()
        d["active_contract"] = dict(contract) if contract else None
        out.append(d)
    return out


@register("core.hr.employees.create")
def employees_create(
    first_name=None, last_name=None, email=None, phone=None,
    employee_code=None, birth_date=None, hire_date=None,
    department_id=None, position_id=None, manager_id=None,
    cost_center_id=None, user_id=None, company_id=None, **kwargs
):
    if not first_name or not last_name:
        return {"error": "first_name and last_name required"}
    db = get_db()
    hire = hire_date or datetime.utcnow().strftime("%Y-%m-%d")
    cur = db.execute(
        "INSERT INTO employees (employee_code, first_name, last_name, email, phone, birth_date, "
        "hire_date, department_id, position_id, manager_id, cost_center_id, user_id, company_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (employee_code, first_name, last_name, email, phone, birth_date, hire,
         department_id, position_id, manager_id, cost_center_id, user_id, company_id),
    )
    db.commit()
    return {
        "id": cur.lastrowid,
        "name": f"{first_name} {last_name}",
        "hire_date": hire,
        "status": "active",
    }


@register("core.hr.employees.update")
def employees_update(id=None, **kwargs):
    if not id:
        return {"error": "id required"}
    allowed = ["first_name", "last_name", "email", "phone", "birth_date", "hire_date",
               "department_id", "position_id", "manager_id", "cost_center_id",
               "status", "employee_code"]
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return {"error": "no valid fields"}
    db = get_db()
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE employees SET {sets} WHERE id = ?", list(fields.values()) + [id])
    db.commit()
    row = db.execute("SELECT * FROM employees WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else {"error": "not found"}


@register("core.hr.employees.terminate")
def employees_terminate(employee_id=None, termination_date=None, **kwargs):
    if not employee_id:
        return {"error": "employee_id required"}
    db = get_db()
    emp = db.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    if not emp:
        return {"error": "employee not found"}
    if emp["status"] == "terminated":
        return {"error": "employee already terminated"}

    tdate = termination_date or datetime.utcnow().strftime("%Y-%m-%d")
    db.execute(
        "UPDATE employees SET status = 'terminated', termination_date = ? WHERE id = ?",
        (tdate, employee_id),
    )
    db.execute(
        "UPDATE contracts SET status = 'closed', date_end = ? WHERE employee_id = ? AND status = 'active'",
        (tdate, employee_id),
    )
    db.commit()
    return {
        "employee_id": employee_id,
        "name": f"{emp['first_name']} {emp['last_name']}",
        "status": "terminated",
        "termination_date": tdate,
    }


# --- Contracts ---

@register("core.hr.contracts.list")
def contracts_list(employee_id=None, **kwargs):
    db = get_db()
    sql = (
        "SELECT c.*, e.first_name || ' ' || e.last_name AS employee_name "
        "FROM contracts c LEFT JOIN employees e ON e.id = c.employee_id WHERE 1=1"
    )
    params = []
    if employee_id:
        sql += " AND c.employee_id = ?"
        params.append(employee_id)
    sql += " ORDER BY c.id DESC"
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@register("core.hr.contracts.create")
def contracts_create(
    employee_id=None, wage=None, contract_type="permanent",
    date_start=None, date_end=None, wage_period="monthly",
    currency="USD", weekly_hours=40, notes=None, **kwargs
):
    if not employee_id or wage is None:
        return {"error": "employee_id and wage required"}
    try:
        wage = float(wage)
    except (TypeError, ValueError):
        return {"error": "wage must be numeric"}
    if wage <= 0:
        return {"error": "wage must be > 0"}
    if contract_type not in ("permanent", "fixed_term", "part_time", "intern", "contractor"):
        return {"error": "invalid contract_type"}
    if wage_period not in ("monthly", "annual", "hourly", "daily"):
        return {"error": "wage_period must be monthly|annual|hourly|daily"}

    db = get_db()
    if not db.execute("SELECT 1 FROM employees WHERE id = ?", (employee_id,)).fetchone():
        return {"error": "employee not found"}

    start = date_start or datetime.utcnow().strftime("%Y-%m-%d")
    # close any previous active contract
    db.execute(
        "UPDATE contracts SET status = 'closed' WHERE employee_id = ? AND status = 'active'",
        (employee_id,),
    )
    cur = db.execute(
        "INSERT INTO contracts (employee_id, contract_type, date_start, date_end, wage, "
        "wage_period, currency, weekly_hours, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (employee_id, contract_type, start, date_end, wage, wage_period,
         currency, float(weekly_hours or 40), notes),
    )
    db.commit()

    monthly = wage
    if wage_period == "annual":
        monthly = wage / 12
    elif wage_period == "hourly":
        monthly = wage * float(weekly_hours or 40) * 52 / 12
    elif wage_period == "daily":
        monthly = wage * 21.67

    return {
        "id": cur.lastrowid,
        "employee_id": employee_id,
        "wage": wage,
        "wage_period": wage_period,
        "monthly_equivalent": round(monthly, 2),
        "contract_type": contract_type,
        "status": "active",
    }


@register("core.hr.headcount")
def hr_headcount(**kwargs):
    """Headcount and payroll cost overview (no country-specific payroll)."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM employees WHERE status = 'active'").fetchone()[0]
    terminated = db.execute("SELECT COUNT(*) FROM employees WHERE status = 'terminated'").fetchone()[0]

    by_dept = db.execute(
        "SELECT COALESCE(d.name,'Unassigned') AS department, COUNT(e.id) AS headcount "
        "FROM employees e LEFT JOIN departments d ON d.id = e.department_id "
        "WHERE e.status = 'active' GROUP BY d.id ORDER BY headcount DESC"
    ).fetchall()

    contracts = db.execute(
        "SELECT c.wage, c.wage_period, c.weekly_hours FROM contracts c "
        "JOIN employees e ON e.id = c.employee_id "
        "WHERE c.status = 'active' AND e.status = 'active'"
    ).fetchall()

    monthly_cost = 0.0
    for c in contracts:
        w = float(c["wage"] or 0)
        p = c["wage_period"]
        if p == "annual":
            monthly_cost += w / 12
        elif p == "hourly":
            monthly_cost += w * float(c["weekly_hours"] or 40) * 52 / 12
        elif p == "daily":
            monthly_cost += w * 21.67
        else:
            monthly_cost += w

    return {
        "active_employees": total,
        "terminated_employees": terminated,
        "with_active_contract": len(contracts),
        "by_department": [dict(r) for r in by_dept],
        "monthly_payroll_cost": round(monthly_cost, 2),
        "annual_payroll_cost": round(monthly_cost * 12, 2),
    }
