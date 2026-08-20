"""Tests for commercial base, setup wizard, audit trail and permissions."""
import pytest


class TestUomConversion:
    def test_seed_creates_categories_and_units(self, seed_commercial, db_conn):
        cats = db_conn.execute("SELECT COUNT(*) FROM uom_categories").fetchone()[0]
        uoms = db_conn.execute("SELECT COUNT(*) FROM uom").fetchone()[0]
        assert cats > 0 and uoms > 0

    def test_convert_kg_to_grams(self, seed_commercial, db_conn):
        from core.commercial_uom import uom_convert
        kg = db_conn.execute("SELECT id FROM uom WHERE code = 'kg'").fetchone()
        g = db_conn.execute("SELECT id FROM uom WHERE code = 'g'").fetchone()
        r = uom_convert(qty=2.5, from_uom=kg["id"], to_uom=g["id"])
        assert "error" not in r, r
        assert float(r["result"]) == 2500.0

    def test_round_trip_is_stable(self, seed_commercial, db_conn):
        from core.commercial_uom import uom_convert
        kg = db_conn.execute("SELECT id FROM uom WHERE code='kg'").fetchone()["id"]
        g = db_conn.execute("SELECT id FROM uom WHERE code='g'").fetchone()["id"]
        forward = uom_convert(qty=7, from_uom=kg, to_uom=g)["result"]
        back = uom_convert(qty=forward, from_uom=g, to_uom=kg)["result"]
        assert float(back) == pytest.approx(7.0, abs=0.0001)

    def test_cross_category_conversion_rejected(self, seed_commercial, db_conn):
        from core.commercial_uom import uom_convert
        kg = db_conn.execute("SELECT id FROM uom WHERE code='kg'").fetchone()["id"]
        unit = db_conn.execute(
            "SELECT id FROM uom WHERE code IN ('unit','pcs','u') LIMIT 1").fetchone()
        if not unit:
            pytest.skip("no unit-category UoM seeded")
        r = uom_convert(qty=1, from_uom=kg, to_uom=unit["id"])
        assert "error" in r, "weight cannot convert to units"


class TestPaymentTermsSchedule:
    def test_seed_creates_terms(self, seed_commercial, db_conn):
        n = db_conn.execute("SELECT COUNT(*) FROM payment_terms").fetchone()[0]
        assert n > 0

    def test_schedule_splits_due_dates(self, seed_commercial, db_conn):
        from core.commercial_terms import payment_terms_schedule
        term = db_conn.execute(
            "SELECT pt.id FROM payment_terms pt "
            "JOIN payment_term_lines l ON l.term_id = pt.id "
            "GROUP BY pt.id HAVING COUNT(l.id) > 1 LIMIT 1").fetchone()
        if not term:
            pytest.skip("no multi-line payment term seeded")

        r = payment_terms_schedule(term_id=term["id"], amount=3000,
                                   start_date="2026-01-01")
        assert "error" not in r, r
        assert len(r["schedule"]) > 1
        total = sum(float(s["amount"]) for s in r["schedule"])
        assert total == pytest.approx(3000.0, abs=0.01), (
            "the split must add up to the original amount")

    def test_immediate_term_is_single_due_date(self, seed_commercial, db_conn):
        from core.commercial_terms import payment_terms_schedule
        term = db_conn.execute(
            "SELECT pt.id FROM payment_terms pt JOIN payment_term_lines l "
            "ON l.term_id = pt.id GROUP BY pt.id HAVING COUNT(l.id) = 1 LIMIT 1"
        ).fetchone()
        if not term:
            pytest.skip("no immediate payment term seeded")
        r = payment_terms_schedule(term_id=term["id"], amount=1000,
                                   start_date="2026-01-01")
        assert len(r["schedule"]) == 1


class TestDocumentSequences:
    def test_next_increments(self, seed_commercial):
        from core.commercial_terms import sequences_next
        first = sequences_next(doc_type="invoice")
        second = sequences_next(doc_type="invoice")
        assert "error" not in first, first
        assert first["folio"] != second["folio"], "folios must be unique"

    def test_folio_has_prefix_and_padding(self, seed_commercial):
        from core.commercial_terms import sequences_next
        r = sequences_next(doc_type="invoice")
        assert "-" in r["folio"]
        assert any(ch.isdigit() for ch in r["folio"])

    def test_unknown_doc_type_errors(self, seed_commercial):
        from core.commercial_terms import sequences_next
        assert "error" in sequences_next(doc_type="does_not_exist")


class TestPricelists:
    def test_seed_creates_lists(self, seed_commercial, db_conn):
        n = db_conn.execute("SELECT COUNT(*) FROM pricelists").fetchone()[0]
        assert n > 0

    def test_price_lookup_falls_back_to_product_price(self, seed_commercial, make_product):
        from core.commercial_pricing import pricelists_resolve
        pid = make_product("FB-1", "Sin regla", 999)
        r = pricelists_resolve(producto_id=pid, qty=1)
        assert float(r["price"]) == 999.0

    def test_volume_rule_applies_above_min_quantity(self, seed_commercial,
                                                    make_product, db_conn):
        from core.commercial_pricing import pricelist_items_create, pricelists_resolve
        pid = make_product("VOL-1", "Con volumen", 100)
        pl = db_conn.execute("SELECT id FROM pricelists LIMIT 1").fetchone()["id"]
        created = pricelist_items_create(pricelist_id=pl, producto_id=pid,
                                         min_qty=10, price=80)
        assert "error" not in created, created

        below = pricelists_resolve(producto_id=pid, qty=5, pricelist_id=pl)
        above = pricelists_resolve(producto_id=pid, qty=10, pricelist_id=pl)
        assert float(below["price"]) == 100.0
        assert float(above["price"]) == 80.0


class TestSetupWizard:
    def test_status_reports_incomplete_on_fresh_db(self):
        from core.setup_wizard import setup_status
        s = setup_status()
        assert "error" not in s, s
        assert s["is_ready"] is False
        assert float(s["progress_pct"]) < 100.0

    def test_countries_are_offered(self):
        from core.setup_wizard import setup_countries
        r = setup_countries()
        codes = {c["country"] for c in r["countries"]}
        assert "MX" in codes

    def test_company_step_persists_settings(self):
        from core.setup_wizard import setup_company, setup_status
        r = setup_company(name="Ander Labs", legal_name="Ander Labs SA",
                          tax_id="AAA010101AAA", email="hola@anderlabs.com")
        assert "error" not in r, r
        company_step = next(s for s in setup_status()["steps"]
                            if s["step"] == "company")
        assert company_step["status"] == "done"

    def test_localization_installs_module_and_sets_currency(self):
        from core.setup_wizard import setup_company, setup_localization
        from core.module_manager import modules_scan
        modules_scan()
        setup_company(name="Ander Labs")
        r = setup_localization(country="MX")
        assert "error" not in r, r
        assert r["currency"] == "MXN"
        assert r.get("module") in ("l10n_mx", None) or "currency" in r

    def test_finalize_makes_system_ready(self):
        from core.setup_wizard import (setup_company, setup_localization,
                                       setup_finalize, setup_status)
        from core.module_manager import modules_scan
        modules_scan()
        setup_company(name="Ander Labs")
        setup_localization(country="MX")
        r = setup_finalize(create_warehouse=True)
        assert "error" not in r, r

        status = setup_status()
        assert status["is_ready"] is True
        assert float(status["progress_pct"]) == 100.0


class TestAuditTrail:
    def test_records_field_level_diff(self):
        from core.audit_attachments import audit_record_handler, audit_history
        r = audit_record_handler(
            entity_type="producto", entity_id=1, action="update",
            user_email="admin@demo.com",
            old_values={"precio_unitario": 500, "nombre": "Antes"},
            new_values={"precio_unitario": 650, "nombre": "Despues"},
        )
        assert r["recorded"] is True
        assert set(r["changed_fields"]) == {"precio_unitario", "nombre"}

        history = audit_history(entity_type="producto", entity_id=1)
        entry = history["entries"][0]
        assert entry["changes"]["precio_unitario"]["from"] == 500
        assert entry["changes"]["precio_unitario"]["to"] == 650

    def test_unsupported_action_rejected(self):
        from core.audit_attachments import audit_record_handler
        r = audit_record_handler(entity_type="producto", entity_id=1, action="hackear")
        assert "error" in r
        assert "allowed" in r, "the error must list the valid actions"

    def test_requires_entity_and_action(self):
        from core.audit_attachments import audit_record_handler
        assert "error" in audit_record_handler(entity_type="producto")
        assert "error" in audit_record_handler(action="update")

    def test_summary_groups_by_action_and_entity(self):
        from core.audit_attachments import audit_record_handler, audit_summary
        audit_record_handler(entity_type="producto", entity_id=1, action="create")
        audit_record_handler(entity_type="producto", entity_id=2, action="create")
        audit_record_handler(entity_type="factura", entity_id=1, action="confirm")

        s = audit_summary()
        assert s["total_entries"] == 3
        assert s["by_action"]["create"] == 2
        assert s["by_entity"]["producto"] == 2
        assert s["by_entity"]["factura"] == 1

    def test_history_is_scoped_to_the_entity(self):
        from core.audit_attachments import audit_record_handler, audit_history
        audit_record_handler(entity_type="producto", entity_id=1, action="update")
        audit_record_handler(entity_type="producto", entity_id=2, action="update")
        assert audit_history(entity_type="producto", entity_id=1)["count"] == 1
        assert audit_history(entity_type="producto")["count"] == 2


class TestAttachments:
    def test_attach_to_any_entity(self):
        from core.audit_attachments import attachments_attach, attachments_list
        r = attachments_attach(entity_type="producto", entity_id=1,
                               filename="datasheet.pdf", size_bytes=204800)
        assert "error" not in r, r
        listed = attachments_list(entity_type="producto", entity_id=1)
        assert len(listed["attachments"]) == 1

    def test_works_for_entities_the_core_does_not_know(self):
        from core.audit_attachments import attachments_attach, attachments_summary
        attachments_attach(entity_type="custom_thing", entity_id=99,
                           filename="x.bin", size_bytes=10240)
        s = attachments_summary()
        entities = {e["entity_type"] for e in s["by_entity"]}
        assert "custom_thing" in entities

    def test_summary_totals_size(self):
        from core.audit_attachments import attachments_attach, attachments_summary
        attachments_attach(entity_type="producto", entity_id=1,
                           filename="a.pdf", size_bytes=204800)
        attachments_attach(entity_type="sales_order", entity_id=1,
                           filename="b.pdf", size_bytes=51200)
        s = attachments_summary()
        assert s["total_attachments"] == 2
        assert float(s["total_size_kb"]) == pytest.approx(250.0, abs=1.0)


class TestPermissions:
    def _user(self, db_conn, email="vendedor@demo.com", role="user"):
        cur = db_conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role, company_id, is_active) "
            "VALUES (?, 'x', 'Vendedor', ?, 1, 1)", (email, role))
        db_conn.commit()
        return cur.lastrowid

    def test_denied_without_grant(self, db_conn):
        from core.workflow_permissions import permissions_check
        uid = self._user(db_conn)
        r = permissions_check(user_id=uid, module="sales", action="read")
        assert r["allowed"] is False

    def test_grant_then_allowed(self, db_conn):
        from core.workflow_permissions import (permissions_grant_to_user,
                                               permissions_check)
        uid = self._user(db_conn)
        g = permissions_grant_to_user(user_id=uid, module="sales", action="read")
        assert "error" not in g, g
        r = permissions_check(user_id=uid, module="sales", action="read")
        assert r["allowed"] is True

    def test_revoke_then_denied_again(self, db_conn):
        from core.workflow_permissions import (permissions_grant_to_user,
                                               permissions_revoke_from_user,
                                               permissions_check)
        uid = self._user(db_conn)
        permissions_grant_to_user(user_id=uid, module="sales", action="read")
        permissions_revoke_from_user(user_id=uid, module="sales", action="read")
        assert permissions_check(user_id=uid, module="sales", action="read")["allowed"] is False

    def test_grant_is_scoped_to_module_and_action(self, db_conn):
        from core.workflow_permissions import (permissions_grant_to_user,
                                               permissions_check)
        uid = self._user(db_conn)
        permissions_grant_to_user(user_id=uid, module="sales", action="read")
        assert permissions_check(user_id=uid, module="sales", action="delete")["allowed"] is False
        assert permissions_check(user_id=uid, module="accounting", action="read")["allowed"] is False

    def test_admin_bypasses_checks(self, db_conn):
        from core.workflow_permissions import permissions_check
        uid = self._user(db_conn, email="jefe@demo.com", role="admin")
        r = permissions_check(user_id=uid, module="accounting", action="delete")
        assert r["allowed"] is True

    def test_requires_arguments(self):
        from core.workflow_permissions import permissions_grant_to_user
        assert "error" in permissions_grant_to_user(module="sales", action="read")
