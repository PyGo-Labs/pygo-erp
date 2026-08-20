"""Tests for full accounting: cost centers, budgets, fixed assets, treasury."""
import pytest


class TestCostCenters:
    def test_seed_creates_centers(self, seed_accounting, db_conn):
        n = db_conn.execute("SELECT COUNT(*) FROM cost_centers").fetchone()[0]
        assert n > 0

    def test_allocate_requires_center(self, seed_accounting):
        from core.accounting_analytic import cost_centers_allocate
        assert "error" in cost_centers_allocate(amount=100)

    def test_allocation_appears_in_report(self, seed_accounting):
        from core.accounting_analytic import cost_centers_allocate, cost_centers_report
        r = cost_centers_allocate(cost_center_id=1, amount=12000,
                                  entry_date="2026-08-10", description="Renta")
        assert "error" not in r, r

        report = cost_centers_report()
        target = next(c for c in report["cost_centers"] if c["id"] == 1)
        assert float(target["total"]) == 12000.0
        assert target["lines"] == 1

    def test_multiple_allocations_accumulate(self, seed_accounting):
        from core.accounting_analytic import cost_centers_allocate, cost_centers_report
        for amount in (1000, 2500, 500):
            cost_centers_allocate(cost_center_id=2, amount=amount)
        report = cost_centers_report()
        target = next(c for c in report["cost_centers"] if c["id"] == 2)
        assert float(target["total"]) == 4000.0
        assert target["lines"] == 3


class TestBudgets:
    def test_create_with_lines(self, seed_accounting):
        from core.accounting_analytic import budgets_create
        r = budgets_create(
            name="Opex 2026", fiscal_year="2026",
            date_from="2026-01-01", date_to="2026-12-31",
            lines=[{"cost_center_id": 1, "planned_amount": 40000},
                   {"cost_center_id": 2, "planned_amount": 20000}],
        )
        assert "error" not in r, r
        assert r["lines"] == 2

    def test_vs_actual_computes_consumption(self, seed_accounting):
        from core.accounting_analytic import (budgets_create, cost_centers_allocate,
                                              budgets_vs_actual)
        budgets_create(name="Opex", fiscal_year="2026",
                       date_from="2026-01-01", date_to="2026-12-31",
                       lines=[{"cost_center_id": 1, "planned_amount": 40000}])
        cost_centers_allocate(cost_center_id=1, amount=8000, entry_date="2026-03-01")

        result = budgets_vs_actual(budget_id=1)
        line = result["lines"][0]
        assert float(line["planned"]) == 40000.0
        assert float(line["actual"]) == 8000.0
        assert float(line["consumed_pct"]) == 20.0
        assert float(line["variance"]) == 32000.0
        assert line["over_budget"] is False

    def test_vs_actual_flags_overspend(self, seed_accounting):
        from core.accounting_analytic import (budgets_create, cost_centers_allocate,
                                              budgets_vs_actual)
        budgets_create(name="Tight", fiscal_year="2026",
                       date_from="2026-01-01", date_to="2026-12-31",
                       lines=[{"cost_center_id": 1, "planned_amount": 1000}])
        cost_centers_allocate(cost_center_id=1, amount=1500, entry_date="2026-03-01")

        line = budgets_vs_actual(budget_id=1)["lines"][0]
        assert line["over_budget"] is True
        assert float(line["consumed_pct"]) == 150.0
        assert float(line["variance"]) == -500.0


class TestFixedAssets:
    def test_straight_line_monthly_amount(self, seed_accounting):
        from core.accounting_assets import assets_create
        r = assets_create(name="Camioneta", acquisition_cost=120000,
                          salvage_value=12000, useful_life_months=48,
                          acquisition_date="2026-01-01")
        assert "error" not in r, r
        # (120000 - 12000) / 48 = 2250
        assert float(r["monthly_depreciation"]) == 2250.0

    def test_requires_cost(self):
        from core.accounting_assets import assets_create
        assert "error" in assets_create(name="Sin costo")

    def test_schedule_covers_useful_life(self, seed_accounting):
        from core.accounting_assets import assets_create, assets_schedule
        assets_create(name="Equipo", acquisition_cost=60000, salvage_value=0,
                      useful_life_months=12, acquisition_date="2026-01-01")
        sched = assets_schedule(asset_id=1)
        assert sched["periods"] == 12
        assert len(sched["schedule"]) == 12
        first, last = sched["schedule"][0], sched["schedule"][-1]
        assert float(first["amount"]) == 5000.0
        assert float(last["book_value"]) == pytest.approx(0.0, abs=0.01)

    def test_depreciate_updates_book_value(self, seed_accounting):
        from core.accounting_assets import assets_create, assets_depreciate
        assets_create(name="Equipo", acquisition_cost=60000, salvage_value=0,
                      useful_life_months=60, acquisition_date="2026-01-01")
        r = assets_depreciate(asset_id=1, period="2026-01")
        assert "error" not in r, r
        assert float(r["amount"]) == 1000.0
        assert float(r["book_value"]) == 59000.0

    def test_same_period_cannot_be_depreciated_twice(self, seed_accounting):
        from core.accounting_assets import assets_create, assets_depreciate
        assets_create(name="Equipo", acquisition_cost=60000, salvage_value=0,
                      useful_life_months=60, acquisition_date="2026-01-01")
        assert "error" not in assets_depreciate(asset_id=1, period="2026-02")
        second = assets_depreciate(asset_id=1, period="2026-02")
        assert "error" in second
        assert "already" in second["error"].lower()

    def test_declining_balance_is_front_loaded(self, seed_accounting):
        from core.accounting_assets import assets_create, assets_schedule
        assets_create(name="Servidor", acquisition_cost=100000, salvage_value=0,
                      useful_life_months=48, acquisition_date="2026-01-01",
                      method="declining_balance")
        sched = assets_schedule(asset_id=1)["schedule"]
        assert float(sched[0]["amount"]) > float(sched[10]["amount"]), (
            "declining balance must depreciate more in early periods")

    def test_summary_totals(self, seed_accounting):
        from core.accounting_assets import assets_create, assets_depreciate, assets_summary
        assets_create(name="A", acquisition_cost=50000, salvage_value=0,
                      useful_life_months=50, acquisition_date="2026-01-01",
                      category="Equipo")
        assets_depreciate(asset_id=1, period="2026-01")
        s = assets_summary()
        assert float(s["total_acquisition_cost"]) == 50000.0
        assert float(s["total_accumulated_depreciation"]) == 1000.0
        assert float(s["total_book_value"]) == 49000.0


class TestTreasuryPayments:
    def test_payment_requires_amount(self):
        from core.accounting_treasury import payments_register
        assert "error" in payments_register()

    def test_payment_allocation_reduces_invoice_balance(self, seed_commercial, db_conn):
        from core.accounting_treasury import payments_register, ar_aging
        db_conn.execute("INSERT INTO clientes (nombre, email) VALUES ('Cliente', 'c@x.com')")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid) VALUES (1, 23200, 0)")
        db_conn.commit()

        r = payments_register(
            amount=9000, payment_type="inbound", partner_type="customer",
            partner_id=1, payment_date="2026-08-14",
            allocations=[{"document_type": "invoice", "document_id": 1, "amount": 9000}],
        )
        assert "error" not in r, r
        assert float(r["allocated"]) == 9000.0
        assert float(r["unallocated"]) == 0.0

        aging = ar_aging(as_of="2026-08-20")
        assert float(aging["total_receivable"]) == 14200.0

    def test_ar_aging_buckets_overdue_invoice(self, seed_commercial, db_conn):
        from core.accounting_treasury import ar_aging
        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.execute(
            "INSERT INTO facturas (cliente_id, total, amount_paid, due_date) "
            "VALUES (1, 5000, 0, '2026-05-01')")
        db_conn.commit()

        aging = ar_aging(as_of="2026-08-20")
        inv = aging["invoices"][0]
        assert inv["days_overdue"] > 90
        assert inv["bucket"] == "over_90"
        assert float(aging["buckets"]["over_90"]) == 5000.0


class TestBankReconciliation:
    def test_import_and_auto_match(self, seed_commercial, db_conn):
        from core.accounting_treasury import (bank_accounts_create, payments_register,
                                              bank_statement_import,
                                              bank_reconcile_auto, bank_reconcile_status)
        bank = bank_accounts_create(name="Principal", currency="MXN",
                                    opening_balance=25000)
        assert "error" not in bank, bank

        db_conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente')")
        db_conn.commit()
        payments_register(amount=9000, payment_type="inbound",
                          partner_type="customer", partner_id=1,
                          payment_date="2026-08-14", bank_account_id=bank["id"])

        imported = bank_statement_import(
            bank_account_id=bank["id"], reference="AGO",
            lines=[{"line_date": "2026-08-14", "description": "Pago cliente", "amount": 9000},
                   {"line_date": "2026-08-16", "description": "Deposito", "amount": 1200},
                   {"line_date": "2026-08-18", "description": "Comision", "amount": -180}],
        )
        assert imported["imported"] == 3

        matched = bank_reconcile_auto(bank_account_id=bank["id"])
        assert matched["matched_count"] == 1, "the 9000 payment must match"
        assert matched["still_unmatched"] == 2

        status = bank_reconcile_status(bank_account_id=bank["id"])
        assert status["lines_total"] == 3
        assert status["lines_matched"] == 1
        assert float(status["amount_matched"]) == 9000.0
        assert float(status["reconciled_pct"]) == pytest.approx(33.3, abs=0.1)
