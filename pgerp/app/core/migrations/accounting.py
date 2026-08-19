"""PyGo ERP V2.0 — Migrations for Real Accounting (IVA, Retenciones, DIOT, Multimoneda)."""
from core.orm.migrations import Migration, migration


@migration("019_create_tax_rates")
class CreateTaxRates(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tax_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rate REAL NOT NULL,
                type TEXT DEFAULT 'iva' CHECK(type IN ('iva', 'isr', 'ieps', 'retention', 'local')),
                is_retention INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        
        # Seed default tax rates (Mexico)
        if conn.execute("SELECT COUNT(*) FROM tax_rates").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO tax_rates (name, rate, type, is_retention) VALUES (?, ?, ?, ?)",
                [
                    ("IVA 16%", 16.0, "iva", 0),
                    ("IVA 0%", 0.0, "iva", 0),
                    ("IVA Exento", 0.0, "iva", 0),
                    ("ISR Retención 10%", 10.0, "isr", 1),
                    ("ISR Retención 1.25%", 1.25, "isr", 1),
                    ("IEPS 8%", 8.0, "ieps", 0),
                    ("IEPS 16%", 16.0, "ieps", 0),
                ]
            )
            conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS tax_rates")
        conn.commit()


@migration("020_create_currencies")
class CreateCurrencies(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS currencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                symbol TEXT,
                is_base INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        
        # Seed default currencies
        if conn.execute("SELECT COUNT(*) FROM currencies").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO currencies (code, name, symbol, is_base) VALUES (?, ?, ?, ?)",
                [
                    ("MXN", "Peso Mexicano", "$", 1),
                    ("USD", "Dolar Americano", "US$", 0),
                    ("EUR", "Euro", "€", 0),
                    ("COP", "Peso Colombiano", "$", 0),
                    ("ARS", "Peso Argentino", "$", 0),
                    ("CLP", "Peso Chileno", "$", 0),
                    ("PEN", "Sol Perueno", "S/", 0),
                ]
            )
            conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS currencies")
        conn.commit()


@migration("021_create_exchange_rates")
class CreateExchangeRates(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                currency_id INTEGER NOT NULL,
                rate REAL NOT NULL,
                date TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(currency_id, date)
            )
        """)
        conn.commit()
        
        # Seed some exchange rates
        if conn.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0] == 0:
            usd = conn.execute("SELECT id FROM currencies WHERE code = 'USD'").fetchone()
            if usd:
                conn.execute(
                    "INSERT INTO exchange_rates (currency_id, rate, date) VALUES (?, ?, ?)",
                    (usd["id"], 17.50, "2026-08-18")
                )
                conn.execute(
                    "INSERT INTO exchange_rates (currency_id, rate, date) VALUES (?, ?, ?)",
                    (usd["id"], 17.55, "2026-08-19")
                )
            conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS exchange_rates")
        conn.commit()


@migration("022_create_retention_concepts")
class CreateRetentionConcepts(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS retention_concepts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT,
                rate REAL NOT NULL,
                type TEXT DEFAULT 'isr' CHECK(type IN ('isr', 'iva', 'ieps')),
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        
        # Seed default retention concepts
        if conn.execute("SELECT COUNT(*) FROM retention_concepts").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO retention_concepts (name, code, rate, type) VALUES (?, ?, ?, ?)",
                [
                    ("Honorarios", "HON", 10.0, "isr"),
                    ("Arrendamiento", "ARR", 10.0, "isr"),
                    ("Servicios Profesionales", "PROF", 10.0, "isr"),
                    ("IVA Retencion", "IVAR", 6.0, "iva"),
                    ("ISR 1.25% Servicios", "ISR1", 1.25, "isr"),
                ]
            )
            conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS retention_concepts")
        conn.commit()


@migration("023_create_fiscal_periods")
class CreateFiscalPeriods(Migration):
    def up(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fiscal_periods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                year TEXT NOT NULL,
                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed', 'locked')),
                closed_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(month, year)
            )
        """)
        conn.commit()
    
    def down(self, conn):
        conn.execute("DROP TABLE IF EXISTS fiscal_periods")
        conn.commit()
