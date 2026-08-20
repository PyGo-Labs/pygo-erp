# Testing — PyGo ERP

Two complementary layers. Both must pass before a commit.

## 1. Unit / integration tests (pytest)

```bash
cd pgerp
PYTHONPATH=app python -m pytest tests/ -q
```

The DB is rebuilt from **real migrations** for every test (`tests/conftest.py`),
so the schema under test is the production schema. This is what catches column
drift — a test that only checks `callable(fn)` would not.

| File | Covers |
|------|--------|
| `test_regressions.py` | Every bug that actually shipped. Add a case here whenever you fix one. |
| `test_accounting_full.py` | Cost centers, budgets, fixed assets, payments, aging, bank reconciliation |
| `test_hr.py` | Contract wage normalisation, leave validation, expense workflow |
| `test_mrp.py` | Multi-level BOM explosion, scrap, costing, production lifecycle |
| `test_tax_modules.py` | Tax engine (all 4 modes) and the installable module system |
| `test_commercial_governance.py` | UoM, payment terms, sequences, pricelists, setup wizard, audit, permissions |
| `test_auth.py` `test_crm.py` `test_inventory.py` `test_projects.py` `test_reports.py` `test_sales.py` | Original smoke-level coverage |

### Fixtures available

- `db_conn` — fresh migrated DB (autouse)
- `seed_commercial` — UoM, pricelists, payment terms, sequences
- `seed_taxes` — generic tax engine data
- `seed_accounting` — chart of accounts + cost centers
- `seed_hr` — leave types
- `make_product`, `make_warehouse`, `make_stock`, `make_employee` — factories

### Writing a good test here

Assert on **computed values**, not on the shape of the response:

```python
# Weak: passes even when the maths is wrong
assert "monthly_equivalent" in result

# Strong: fails if annual/12 ever breaks
assert float(result["monthly_equivalent"]) == 50000.0
```

## 2. End-to-end verification scripts

These exercise the running server over HTTP, so they also prove that a handler
has a route and that the Go/Python bridge passes arguments correctly.

```bash
bash scripts/verify_all.sh      # every script against a clean server
bash scripts/restart_dev.sh --fresh   # clean restart, wipes the dev DB
bash scripts/stats.sh           # handlers, routes, migrations, modules
```

Individual scripts: `test_b2_purchasing`, `test_b3_accounting`, `test_b4_hr`,
`test_b5_mrp`, `test_a_modules`, `test_c_setup`, `test_ui1`..`test_ui4`,
`test_users_perms`.

## Verifying that a test actually catches its bug

A regression test is worthless until you have seen it fail. Reintroduce the
defect, confirm the failure, then restore:

```bash
cp app/core/accounting.py /tmp/acc.bak
# remove the SELECT keyword from journal_list
PYTHONPATH=app python -m pytest tests/test_regressions.py::TestJournalListSelect -q  # must FAIL
cp /tmp/acc.bak app/core/accounting.py
```

## Pitfalls learned the hard way

- **`HANDLERS` is process-global.** Module install/uninstall leaks across tests
  in the same run. Assert on module *state*, not on registry size.
- **Handler names are plural in some modules**: `boms_create`, `boms_explode`,
  `production_check_availability`, `bank_statement_import` (singular),
  `tax_groups_create`. Grep `^def ` before writing a test.
- **Parameter names differ from the HTTP field names**: `uom_convert(qty=,
  from_uom=, to_uom=)`, `payment_terms_schedule(term_id=, start_date=)`,
  `attachments_attach(size_bytes=)`.
- **`tax_compute(amount=...)` takes the line subtotal already multiplied.**
  `quantity` only scales *fixed* per-unit taxes (same convention as Odoo).
- **Expense analytic lines are written on approval**, not when the report is
  created.
- **`exit_code 0` from a piped script means nothing.** Always grep the captured
  output for `error`, `Traceback`, `Method Not Allowed`.
