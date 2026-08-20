"""Tests for D2 reservations, backorders and reorder rules."""
import pytest


class TestAvailability:
    def test_requires_product(self):
        from core.reservations import stock_availability
        assert "error" in stock_availability()

    def test_unknown_product_errors(self):
        from core.reservations import stock_availability
        assert "error" in stock_availability(producto_id=99999)

    def test_available_equals_on_hand_without_reservations(self, make_product,
                                                          make_warehouse, make_stock):
        from core.reservations import stock_availability
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)
        a = stock_availability(producto_id=pid, warehouse_id=wid)
        assert a["on_hand"] == 100.0
        assert a["reserved"] == 0.0
        assert a["available"] == 100.0


class TestReservations:
    def test_requires_all_fields(self, make_product, make_warehouse):
        from core.reservations import reservations_reserve
        assert "error" in reservations_reserve(producto_id=make_product(),
                                              warehouse_id=make_warehouse())

    def test_zero_quantity_rejected(self, make_product, make_warehouse, make_stock):
        from core.reservations import reservations_reserve
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 10)
        r = reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=0,
                                document_type="sales_order", document_id=1)
        assert "error" in r

    def test_reservation_reduces_available(self, make_product, make_warehouse,
                                           make_stock):
        from core.reservations import reservations_reserve, stock_availability
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)

        r = reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=60,
                                document_type="sales_order", document_id=1)
        assert "error" not in r, r
        assert r["available_after"] == 40.0

        a = stock_availability(producto_id=pid, warehouse_id=wid)
        assert a["on_hand"] == 100.0, "physical stock does not move on reservation"
        assert a["reserved"] == 60.0
        assert a["available"] == 40.0

    def test_cannot_over_promise(self, make_product, make_warehouse, make_stock):
        """The core reason reservations exist: two people selling one unit."""
        from core.reservations import reservations_reserve
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)

        reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=60,
                            document_type="sales_order", document_id=1)
        second = reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=60,
                                     document_type="sales_order", document_id=2)
        assert "error" in second
        assert second["available"] == 40.0
        assert second["already_reserved"] == 60.0
        assert second["on_hand"] == 100.0

    def test_reserving_exactly_what_is_left_works(self, make_product, make_warehouse,
                                                  make_stock):
        from core.reservations import reservations_reserve, stock_availability
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)
        reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=60,
                            document_type="sales_order", document_id=1)
        r = reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=40,
                                document_type="sales_order", document_id=2)
        assert "error" not in r
        assert stock_availability(producto_id=pid, warehouse_id=wid)["available"] == 0.0

    def test_release_frees_the_stock(self, make_product, make_warehouse, make_stock):
        from core.reservations import (reservations_reserve, reservations_release,
                                       stock_availability)
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)
        reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=60,
                            document_type="sales_order", document_id=1)

        rel = reservations_release(document_type="sales_order", document_id=1)
        assert rel["released"] == 1
        assert rel["quantity_released"] == 60.0
        assert stock_availability(producto_id=pid, warehouse_id=wid)["available"] == 100.0

    def test_release_without_reservation_errors(self):
        from core.reservations import reservations_release
        assert "error" in reservations_release(document_type="sales_order",
                                              document_id=999)

    def test_fulfill_closes_the_reservation(self, make_product, make_warehouse,
                                            make_stock):
        from core.reservations import (reservations_reserve, reservations_fulfill,
                                       reservations_list)
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)
        reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=40,
                            document_type="sales_order", document_id=2)

        f = reservations_fulfill(document_type="sales_order", document_id=2)
        assert f["fulfilled"] == 1
        assert f["quantity"] == 40.0
        assert reservations_list(document_type="sales_order", document_id=2,
                                status="active") == []

    def test_released_reservation_cannot_be_fulfilled(self, make_product,
                                                      make_warehouse, make_stock):
        from core.reservations import (reservations_reserve, reservations_release,
                                       reservations_fulfill)
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 50)
        reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=10,
                            document_type="sales_order", document_id=5)
        reservations_release(document_type="sales_order", document_id=5)
        assert "error" in reservations_fulfill(document_type="sales_order",
                                              document_id=5)

    def test_reservations_are_per_warehouse(self, make_product, make_warehouse,
                                            make_stock):
        from core.reservations import reservations_reserve, stock_availability
        pid = make_product()
        w1, w2 = make_warehouse("Central", "CEN"), make_warehouse("Norte", "NOR")
        make_stock(pid, w1, 50)
        make_stock(pid, w2, 50)

        reservations_reserve(producto_id=pid, warehouse_id=w1, quantity=50,
                            document_type="sales_order", document_id=1)
        assert stock_availability(producto_id=pid, warehouse_id=w1)["available"] == 0.0
        assert stock_availability(producto_id=pid, warehouse_id=w2)["available"] == 50.0


class TestBackorders:
    def test_requires_fields(self):
        from core.reservations import backorders_create
        assert "error" in backorders_create(document_type="sales_order")

    def test_zero_pending_rejected(self, make_product):
        from core.reservations import backorders_create
        r = backorders_create(document_type="sales_order", document_id=1,
                              producto_id=make_product(), quantity_pending=0)
        assert "error" in r

    def test_create_records_what_is_missing(self, make_product, make_warehouse):
        from core.reservations import backorders_create
        r = backorders_create(document_type="sales_order", document_id=3,
                              producto_id=make_product(), warehouse_id=make_warehouse(),
                              quantity_ordered=100, quantity_pending=70,
                              expected_date="2026-09-15")
        assert "error" not in r, r
        assert r["quantity_ordered"] == 100.0
        assert r["quantity_pending"] == 70.0
        assert r["status"] == "pending"

    def test_partial_fulfilment_leaves_a_remainder(self, make_product):
        from core.reservations import backorders_create, backorders_fulfill
        bo = backorders_create(document_type="sales_order", document_id=3,
                               producto_id=make_product(), quantity_ordered=100,
                               quantity_pending=70)
        r = backorders_fulfill(backorder_id=bo["backorder_id"], quantity=30)
        assert r["quantity_pending"] == 40.0
        assert r["status"] == "partial"

    def test_over_fulfilment_rejected(self, make_product):
        from core.reservations import backorders_create, backorders_fulfill
        bo = backorders_create(document_type="sales_order", document_id=3,
                               producto_id=make_product(), quantity_pending=40)
        r = backorders_fulfill(backorder_id=bo["backorder_id"], quantity=100)
        assert "error" in r
        assert "only 40" in r["error"]

    def test_completing_the_remainder_closes_it(self, make_product):
        from core.reservations import backorders_create, backorders_fulfill
        bo = backorders_create(document_type="sales_order", document_id=3,
                               producto_id=make_product(), quantity_pending=70)
        backorders_fulfill(backorder_id=bo["backorder_id"], quantity=30)
        r = backorders_fulfill(backorder_id=bo["backorder_id"], quantity=40)
        assert r["quantity_pending"] == 0.0
        assert r["status"] == "fulfilled"

    def test_fulfilled_backorder_is_final(self, make_product):
        from core.reservations import backorders_create, backorders_fulfill
        bo = backorders_create(document_type="sales_order", document_id=3,
                               producto_id=make_product(), quantity_pending=10)
        backorders_fulfill(backorder_id=bo["backorder_id"], quantity=10)
        r = backorders_fulfill(backorder_id=bo["backorder_id"], quantity=5)
        assert "error" in r
        assert "already fulfilled" in r["error"]

    def test_cancel_stops_further_fulfilment(self, make_product):
        from core.reservations import (backorders_create, backorders_cancel,
                                      backorders_fulfill)
        bo = backorders_create(document_type="sales_order", document_id=3,
                               producto_id=make_product(), quantity_pending=10)
        assert backorders_cancel(backorder_id=bo["backorder_id"])["cancelled"] is True
        assert "error" in backorders_fulfill(backorder_id=bo["backorder_id"],
                                            quantity=5)

    def test_pending_list_excludes_closed(self, make_product):
        from core.reservations import (backorders_create, backorders_fulfill,
                                       backorders_list)
        pid = make_product()
        open_bo = backorders_create(document_type="sales_order", document_id=1,
                                    producto_id=pid, quantity_pending=50)
        done = backorders_create(document_type="sales_order", document_id=2,
                                 producto_id=pid, quantity_pending=10)
        backorders_fulfill(backorder_id=done["backorder_id"], quantity=10)

        pending = backorders_list(status="pending")
        ids = [b["id"] for b in pending]
        assert open_bo["backorder_id"] in ids
        assert done["backorder_id"] not in ids


class TestReorderRules:
    def test_requires_fields(self, make_product):
        from core.reservations import reorder_rules_create
        assert "error" in reorder_rules_create(producto_id=make_product())

    def test_max_below_min_rejected(self, make_product, make_warehouse):
        from core.reservations import reorder_rules_create
        r = reorder_rules_create(producto_id=make_product(),
                                 warehouse_id=make_warehouse(),
                                 min_quantity=100, max_quantity=50)
        assert "error" in r

    def test_second_call_updates_instead_of_duplicating(self, make_product,
                                                        make_warehouse):
        from core.reservations import reorder_rules_create, reorder_rules_list
        pid, wid = make_product(), make_warehouse()
        first = reorder_rules_create(producto_id=pid, warehouse_id=wid,
                                     min_quantity=50, max_quantity=200)
        second = reorder_rules_create(producto_id=pid, warehouse_id=wid,
                                      min_quantity=80, max_quantity=300)
        assert first["action"] == "created"
        assert second["action"] == "updated"
        assert len(reorder_rules_list(producto_id=pid)) == 1

    def test_no_suggestion_above_minimum(self, make_product, make_warehouse,
                                         make_stock):
        from core.reservations import reorder_rules_create, reorder_suggestions
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 100)
        reorder_rules_create(producto_id=pid, warehouse_id=wid, min_quantity=50,
                             max_quantity=200)
        assert reorder_suggestions()["count"] == 0

    def test_suggestion_tops_up_to_maximum(self, make_product, make_warehouse,
                                           make_stock):
        from core.reservations import reorder_rules_create, reorder_suggestions
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 20)
        reorder_rules_create(producto_id=pid, warehouse_id=wid, min_quantity=50,
                             max_quantity=200)
        s = reorder_suggestions()
        assert s["count"] == 1
        assert s["suggestions"][0]["suggested_quantity"] == 180.0

    def test_multiple_of_rounds_up(self, make_product, make_warehouse, make_stock):
        from core.reservations import reorder_rules_create, reorder_suggestions
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 20)
        reorder_rules_create(producto_id=pid, warehouse_id=wid, min_quantity=50,
                             max_quantity=200, multiple_of=25)
        # needs 180, must round up to the next multiple of 25 -> 200
        assert reorder_suggestions()["suggestions"][0]["suggested_quantity"] == 200.0

    def test_reservations_can_trigger_a_suggestion(self, make_product, make_warehouse,
                                                   make_stock):
        """Physical stock looks fine but it is already promised away."""
        from core.reservations import (reorder_rules_create, reservations_reserve,
                                       reorder_suggestions)
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 60)
        reorder_rules_create(producto_id=pid, warehouse_id=wid, min_quantity=50,
                             max_quantity=200)
        assert reorder_suggestions()["count"] == 0, "60 on hand is above the minimum"

        reservations_reserve(producto_id=pid, warehouse_id=wid, quantity=30,
                            document_type="sales_order", document_id=9)
        s = reorder_suggestions()
        assert s["count"] == 1, "30 available is below the minimum of 50"
        assert s["suggestions"][0]["on_hand"] == 60.0
        assert s["suggestions"][0]["reserved"] == 30.0
        assert s["suggestions"][0]["available"] == 30.0
        assert s["suggestions"][0]["suggested_quantity"] == 170.0

    def test_lead_time_sets_expected_date(self, make_product, make_warehouse,
                                          make_stock):
        from core.reservations import reorder_rules_create, reorder_suggestions
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 10)
        reorder_rules_create(producto_id=pid, warehouse_id=wid, min_quantity=50,
                             max_quantity=100, lead_time_days=7)
        assert reorder_suggestions()["suggestions"][0]["expected_date"] is not None

    def test_create_rfq_from_suggestions(self, seed_commercial, make_product,
                                         make_warehouse, make_stock, db_conn):
        from core.reservations import reorder_rules_create, reorder_create_rfq
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 5)
        reorder_rules_create(producto_id=pid, warehouse_id=wid, min_quantity=50,
                             max_quantity=100)

        r = reorder_create_rfq()
        assert r["created"] is True
        assert r["lines"] == 1
        line = db_conn.execute(
            "SELECT qty FROM rfq_lines WHERE rfq_id = ?", (r["rfq_id"],)).fetchone()
        assert float(line["qty"]) == 95.0, "the RFQ must carry the suggested quantity"

    def test_create_rfq_does_nothing_when_stocked(self, seed_commercial, make_product,
                                                  make_warehouse, make_stock):
        from core.reservations import reorder_rules_create, reorder_create_rfq
        pid, wid = make_product(), make_warehouse()
        make_stock(pid, wid, 500)
        reorder_rules_create(producto_id=pid, warehouse_id=wid, min_quantity=50,
                             max_quantity=100)
        r = reorder_create_rfq()
        assert r["created"] is False
