"""Tests for the generic tax engine and the installable module system."""
import pytest


class TestTaxComputation:
    def test_excluded_percent(self, seed_taxes, db_conn):
        from core.tax_engine import tax_compute
        tid = db_conn.execute(
            "SELECT id FROM taxes WHERE code = 'STD'").fetchone()["id"]
        r = tax_compute(amount=1000, quantity=1, tax_ids=[tid])
        assert float(r["untaxed_amount"]) == 1000.0
        assert float(r["total_taxes"]) == 160.0
        assert float(r["total"]) == 1160.0

    def test_price_included_is_backed_out(self, db_conn):
        from core.tax_engine import tax_create, tax_compute
        t = tax_create(name="IVA incluido", code="INC16", computation="percent",
                       amount=16, price_include=1)
        r = tax_compute(amount=1160, quantity=1, tax_ids=[t["id"]])
        assert float(r["untaxed_amount"]) == pytest.approx(1000.0, abs=0.01)
        assert float(r["total_taxes"]) == pytest.approx(160.0, abs=0.01)
        assert float(r["total"]) == pytest.approx(1160.0, abs=0.01)

    def test_fixed_amount(self, db_conn):
        from core.tax_engine import tax_create, tax_compute
        t = tax_create(name="Cuota fija", code="FIJO", computation="fixed", amount=25)
        r = tax_compute(amount=1000, quantity=1, tax_ids=[t["id"]])
        assert float(r["total_taxes"]) == 25.0
        assert float(r["total"]) == 1025.0

    def test_cascade_raises_base_for_later_taxes(self, db_conn):
        """include_base_amount must lift the base of subsequent taxes."""
        from core.tax_engine import tax_create, tax_compute
        first = tax_create(name="Verde", code="VERDE", computation="percent",
                           amount=8, sequence=5, include_base_amount=1)
        second = tax_create(name="IVA", code="IVA16C", computation="percent",
                            amount=16, sequence=10)
        r = tax_compute(amount=1000, quantity=1,
                        tax_ids=[first["id"], second["id"]])
        amounts = {t["code"]: float(t["amount"]) for t in r["taxes"]}
        assert amounts["VERDE"] == 80.0
        # base becomes 1080 -> 16% = 172.8
        assert amounts["IVA16C"] == pytest.approx(172.8, abs=0.01)
        assert float(r["total"]) == pytest.approx(1252.8, abs=0.01)

    def test_percent_of_tax(self, db_conn):
        from core.tax_engine import tax_create, tax_compute
        base_tax = tax_create(name="IVA", code="IVAP", computation="percent",
                              amount=16, sequence=10)
        surcharge = tax_create(name="Recargo", code="SUR5",
                               computation="percent_of_tax", amount=5, sequence=20)
        r = tax_compute(amount=1000, quantity=1,
                        tax_ids=[base_tax["id"], surcharge["id"]])
        amounts = {t["code"]: float(t["amount"]) for t in r["taxes"]}
        assert amounts["IVAP"] == 160.0
        assert amounts["SUR5"] == pytest.approx(8.0, abs=0.01)  # 5% of 160
        assert float(r["total"]) == pytest.approx(1168.0, abs=0.01)

    def test_withholding_is_subtracted(self, db_conn):
        from core.tax_engine import tax_create, tax_compute
        iva = tax_create(name="IVA", code="IVAW", computation="percent",
                         amount=16, sequence=10)
        ret = tax_create(name="Retencion", code="RETW", computation="percent",
                         amount=10, sequence=30, is_withholding=1)
        r = tax_compute(amount=1000, quantity=1, tax_ids=[iva["id"], ret["id"]])
        assert float(r["total_taxes"]) == 160.0
        assert float(r["total_withheld"]) == 100.0
        assert float(r["total"]) == 1060.0

    def test_quantity_multiplies_fixed_taxes_only(self, seed_taxes, db_conn):
        """`amount` is already the line subtotal; quantity applies per-unit
        fixed taxes (same convention as Odoo), it does not scale the base."""
        from core.tax_engine import tax_compute, tax_create
        pct = db_conn.execute("SELECT id FROM taxes WHERE code='STD'").fetchone()["id"]
        r = tax_compute(amount=500, quantity=5, tax_ids=[pct])
        assert float(r["untaxed_amount"]) == 500.0, "percent taxes use the given base"
        assert float(r["total_taxes"]) == 80.0

        fixed = tax_create(name="Cuota unitaria", code="UNIT2",
                           computation="fixed", amount=2)
        rf = tax_compute(amount=500, quantity=5, tax_ids=[fixed["id"]])
        assert float(rf["total_taxes"]) == 10.0, "2 per unit x 5 units"

    def test_document_totals_sum_lines(self, seed_taxes, db_conn):
        from core.tax_engine import tax_compute_document
        tid = db_conn.execute("SELECT id FROM taxes WHERE code='STD'").fetchone()["id"]
        r = tax_compute_document(lines=[
            {"amount": 1000, "quantity": 1, "tax_ids": [tid]},
            {"amount": 500, "quantity": 1, "tax_ids": [tid]},
        ])
        assert float(r["untaxed_amount"]) == 1500.0
        assert float(r["total_taxes"]) == 240.0
        assert float(r["total"]) == 1740.0

    def test_no_taxes_returns_base_untouched(self):
        from core.tax_engine import tax_compute
        r = tax_compute(amount=750, quantity=1, tax_ids=[])
        assert float(r["untaxed_amount"]) == 750.0
        assert float(r["total"]) == 750.0
        assert float(r["total_taxes"]) == 0.0


class TestTaxGroups:
    def test_group_applies_all_member_taxes(self, db_conn):
        from core.tax_engine import tax_create, tax_groups_create, tax_compute
        a = tax_create(name="A", code="GA", computation="percent", amount=10)
        b = tax_create(name="B", code="GB", computation="percent", amount=5)
        group = tax_groups_create(name="Combo", code="COMBO",
                                 tax_ids=[a["id"], b["id"]])
        assert "error" not in group, group

        r = tax_compute(amount=1000, quantity=1, tax_group_id=group["id"])
        assert float(r["total_taxes"]) == 150.0
        assert len(r["taxes"]) == 2


class TestModuleSystem:
    def test_scan_discovers_l10n_mx(self):
        from core.module_manager import modules_scan
        r = modules_scan()
        assert "error" not in r, r
        assert "l10n_mx" in r["modules"]

    def test_handler_absent_before_install(self):
        """A scanned-but-not-installed module must not register handlers.

        HANDLERS is a process-global registry, so this asserts on module state
        rather than dict size: another test may already have imported l10n_mx.
        """
        from core.module_manager import modules_scan, modules_list
        modules_scan()
        mod = next(m for m in modules_list() if m["name"] == "l10n_mx")
        if mod["state"] == "installed":
            pytest.skip("module already installed in this process")
        assert mod["state"] in ("uninstalled", "disabled")
        assert mod["migrations_applied"] == 0

    def test_install_registers_handlers_and_migrations(self):
        from core.module_manager import modules_scan, modules_install
        from core.registry import HANDLERS
        modules_scan()

        r = modules_install(name="l10n_mx")
        assert "error" not in r, r
        assert r["state"] == "installed"
        assert r["installed"][0]["migrations_applied"] > 0
        # The handler must be callable regardless of import order
        assert "l10n_mx.compute_tax" in HANDLERS
        assert callable(HANDLERS["l10n_mx.compute_tax"])

    def test_installed_module_seeds_its_own_taxes(self, db_conn):
        from core.module_manager import modules_scan, modules_install
        modules_scan()
        modules_install(name="l10n_mx")
        n = db_conn.execute(
            "SELECT COUNT(*) FROM taxes WHERE module_name = 'l10n_mx'").fetchone()[0]
        assert n > 0, "the module must own the taxes it creates"

    def test_module_taxes_compute_through_the_generic_engine(self, db_conn):
        from core.module_manager import modules_scan, modules_install
        from core.tax_engine import tax_compute
        modules_scan()
        modules_install(name="l10n_mx")
        iva = db_conn.execute(
            "SELECT id FROM taxes WHERE code = 'IVA16'").fetchone()
        r = tax_compute(amount=1000, quantity=1, tax_ids=[iva["id"]])
        assert float(r["total_taxes"]) == 160.0

    def test_disable_deactivates_hooks(self):
        from core.module_manager import (modules_scan, modules_install,
                                         modules_disable, hooks_list)
        modules_scan()
        modules_install(name="l10n_mx")
        assert len(hooks_list()) > 0

        r = modules_disable(name="l10n_mx")
        assert "error" not in r, r
        assert r["state"] == "disabled"
        active = [h for h in hooks_list() if h["is_active"]]
        assert not active, "disabling must deactivate every hook of the module"

    def test_enable_restores_hooks(self):
        from core.module_manager import (modules_scan, modules_install,
                                         modules_disable, modules_enable, hooks_list)
        modules_scan()
        modules_install(name="l10n_mx")
        modules_disable(name="l10n_mx")
        r = modules_enable(name="l10n_mx")
        assert r["state"] == "installed"
        assert any(h["is_active"] for h in hooks_list())

    def test_hook_run_reflects_module_state(self):
        from core.module_manager import (modules_scan, modules_install,
                                         modules_disable, modules_enable, hooks_run)
        modules_scan()
        modules_install(name="l10n_mx")
        enabled = hooks_run(hook_point="invoice.before_create", payload={"probe": True})
        assert enabled["executed"] >= 1

        modules_disable(name="l10n_mx")
        disabled = hooks_run(hook_point="invoice.before_create", payload={"probe": True})
        assert disabled["executed"] == 0

        modules_enable(name="l10n_mx")
        again = hooks_run(hook_point="invoice.before_create", payload={"probe": True})
        assert again["executed"] >= 1

    def test_install_unknown_module_errors(self):
        from core.module_manager import modules_install
        assert "error" in modules_install(name="l10n_nowhere")

    def test_module_info_lists_hooks_and_migrations(self):
        from core.module_manager import modules_scan, modules_install, modules_info
        modules_scan()
        modules_install(name="l10n_mx")
        info = modules_info(name="l10n_mx")
        assert info["state"] == "installed"
        assert len(info["hooks"]) > 0
        assert len(info["migrations"]) > 0
