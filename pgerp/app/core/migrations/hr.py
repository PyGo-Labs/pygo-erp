"""PyGo ERP — Migrations for HR base (employees, contracts, leave, expenses)."""
from core.orm.migrations import Migration, migration


@migration("047_create_hr_org")
class CreateHrOrg(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT,
                parent_id INTEGER,
                manager_id INTEGER,
                cost_center_id INTEGER,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS job_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                department_id INTEGER,
                min_salary REAL DEFAULT 0,
                max_salary REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_code TEXT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                birth_date TEXT,
                hire_date TEXT,
                termination_date TEXT,
                department_id INTEGER,
                position_id INTEGER,
                manager_id INTEGER,
                user_id INTEGER,
                cost_center_id INTEGER,
                status TEXT DEFAULT 'active',
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(department_id, status);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS employees;
            DROP TABLE IF EXISTS job_positions;
            DROP TABLE IF EXISTS departments;
        """)


@migration("048_create_hr_contracts")
class CreateHrContracts(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                contract_type TEXT DEFAULT 'permanent',
                date_start TEXT,
                date_end TEXT,
                wage REAL DEFAULT 0,
                wage_period TEXT DEFAULT 'monthly',
                currency TEXT DEFAULT 'USD',
                weekly_hours REAL DEFAULT 40,
                status TEXT DEFAULT 'active',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            );
            CREATE INDEX IF NOT EXISTS idx_contract_emp ON contracts(employee_id, status);
        """)

    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS contracts")


@migration("049_create_hr_leave")
class CreateHrLeave(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leave_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT,
                days_per_year REAL DEFAULT 0,
                is_paid INTEGER DEFAULT 1,
                requires_approval INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                leave_type_id INTEGER NOT NULL,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                days REAL DEFAULT 0,
                reason TEXT,
                status TEXT DEFAULT 'draft',
                approved_by INTEGER,
                approved_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS leave_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                leave_type_id INTEGER NOT NULL,
                year TEXT,
                days_allocated REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_leave_emp ON leave_requests(employee_id, status);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS leave_allocations;
            DROP TABLE IF EXISTS leave_requests;
            DROP TABLE IF EXISTS leave_types;
        """)


@migration("050_create_hr_expenses")
class CreateHrExpenses(Migration):
    def up(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS expense_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folio TEXT,
                employee_id INTEGER NOT NULL,
                title TEXT,
                total REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                status TEXT DEFAULT 'draft',
                submitted_at TEXT,
                approved_by INTEGER,
                approved_at TEXT,
                paid_at TEXT,
                payment_id INTEGER,
                company_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS expense_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                expense_date TEXT,
                category TEXT,
                description TEXT,
                amount REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                cost_center_id INTEGER,
                account_id INTEGER,
                receipt_file_id INTEGER,
                FOREIGN KEY (report_id) REFERENCES expense_reports(id)
            );
            CREATE INDEX IF NOT EXISTS idx_exp_emp ON expense_reports(employee_id, status);
        """)

    def down(self, conn):
        conn.executescript("""
            DROP TABLE IF EXISTS expense_lines;
            DROP TABLE IF EXISTS expense_reports;
        """)
