"""l10n_mx migrations.

Each function named migration_* receives a live DB connection and is applied
once, tracked in module_migrations. Module migrations only touch their own
tables or insert data — they never alter core schema.
"""


def migration_001_seed_mx_taxes(conn):
    """Insert Mexican taxes into the generic tax engine."""
    existing = conn.execute(
        "SELECT COUNT(*) FROM taxes WHERE country = 'MX'"
    ).fetchone()[0]
    if existing:
        return

    taxes = [
        # (name, code, computation, amount, price_include, withholding, sequence, scope)
        ("IVA 16%", "IVA16", "percent", 16, 0, 0, 10, "both"),
        ("IVA 8% Frontera", "IVA8", "percent", 8, 0, 0, 10, "both"),
        ("IVA 0%", "IVA0", "percent", 0, 0, 0, 10, "both"),
        ("IVA 16% Incluido", "IVA16_INC", "percent", 16, 1, 0, 10, "sale"),
        ("Retención IVA 10.67%", "RET_IVA", "percent", 10.6667, 0, 1, 20, "purchase"),
        ("Retención ISR 10%", "RET_ISR", "percent", 10, 0, 1, 20, "purchase"),
        ("IEPS 8%", "IEPS8", "percent", 8, 0, 0, 5, "both"),
        ("IEPS 26.5%", "IEPS265", "percent", 26.5, 0, 0, 5, "both"),
    ]
    ids = {}
    for name, code, comp, amt, incl, wh, seq, scope in taxes:
        cur = conn.execute(
            "INSERT INTO taxes (name, code, country, computation, amount, price_include, "
            "is_withholding, sequence, scope, module_name) "
            "VALUES (?, ?, 'MX', ?, ?, ?, ?, ?, ?, 'l10n_mx')",
            (name, code, comp, amt, incl, wh, seq, scope),
        )
        ids[code] = cur.lastrowid

    # Tax groups reflecting real Mexican combinations
    groups = [
        ("IVA 16% (General)", "MX_IVA16", ["IVA16"]),
        ("IVA 16% + Retenciones (Servicios)", "MX_SERV", ["IVA16", "RET_IVA", "RET_ISR"]),
        ("IEPS 8% + IVA 16%", "MX_IEPS_IVA", ["IEPS8", "IVA16"]),
        ("Frontera 8%", "MX_FRONTERA", ["IVA8"]),
    ]
    for name, code, tax_codes in groups:
        cur = conn.execute(
            "INSERT INTO tax_groups (name, code, country, description) "
            "VALUES (?, ?, 'MX', 'Mexican tax combination')",
            (name, code),
        )
        gid = cur.lastrowid
        for tc in tax_codes:
            if tc in ids:
                conn.execute(
                    "INSERT INTO tax_group_taxes (tax_group_id, tax_id) VALUES (?, ?)",
                    (gid, ids[tc]),
                )


def migration_002_create_mx_tables(conn):
    """Module-owned tables: CFDI metadata and SAT catalogs."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mx_cfdi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            uuid TEXT,
            serie TEXT,
            folio TEXT,
            rfc_emisor TEXT,
            rfc_receptor TEXT,
            uso_cfdi TEXT,
            forma_pago TEXT,
            metodo_pago TEXT,
            regimen_fiscal TEXT,
            subtotal REAL DEFAULT 0,
            total REAL DEFAULT 0,
            status TEXT DEFAULT 'draft',
            stamped_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS mx_sat_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_mx_cat ON mx_sat_catalog(catalog, code);
    """)

    catalogs = [
        ("uso_cfdi", "G01", "Adquisición de mercancías"),
        ("uso_cfdi", "G03", "Gastos en general"),
        ("uso_cfdi", "I01", "Construcciones"),
        ("uso_cfdi", "P01", "Por definir"),
        ("forma_pago", "01", "Efectivo"),
        ("forma_pago", "03", "Transferencia electrónica de fondos"),
        ("forma_pago", "04", "Tarjeta de crédito"),
        ("forma_pago", "99", "Por definir"),
        ("metodo_pago", "PUE", "Pago en una sola exhibición"),
        ("metodo_pago", "PPD", "Pago en parcialidades o diferido"),
        ("regimen_fiscal", "601", "General de Ley Personas Morales"),
        ("regimen_fiscal", "605", "Sueldos y Salarios"),
        ("regimen_fiscal", "612", "Personas Físicas con Actividades Empresariales"),
    ]
    for cat, code, desc in catalogs:
        exists = conn.execute(
            "SELECT 1 FROM mx_sat_catalog WHERE catalog = ? AND code = ?", (cat, code)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO mx_sat_catalog (catalog, code, description) VALUES (?, ?, ?)",
                (cat, code, desc),
            )


def migration_003_register_hooks(conn):
    """Register this module's extension hooks on core points."""
    hooks = [
        ("invoice.before_create", "l10n_mx.validate_rfc", 50),
        ("invoice.after_create", "l10n_mx.prepare_cfdi", 100),
    ]
    for point, handler, priority in hooks:
        exists = conn.execute(
            "SELECT 1 FROM module_hooks WHERE module_name = 'l10n_mx' AND hook_point = ? "
            "AND handler = ?",
            (point, handler),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO module_hooks (module_name, hook_point, handler, priority) "
                "VALUES ('l10n_mx', ?, ?, ?)",
                (point, handler, priority),
            )
