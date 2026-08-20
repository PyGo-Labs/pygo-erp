"""Tests for D2 lot and serial tracking (FEFO, traceability, expiry)."""
import pytest


@pytest.fixture
def tracked_product(make_product):
    """A lot-tracked product."""
    from core.lots import lots_set_tracking
    pid = make_product("MED-1", "Medicamento", 100, 40)
    lots_set_tracking(producto_id=pid, tracking="lot", shelf_life_days=365)
    return pid


class TestTrackingPolicy:
    def test_default_is_none(self, make_product, db_conn):
        pid = make_product()
        row = db_conn.execute("SELECT tracking FROM productos WHERE id = ?",
                              (pid,)).fetchone()
        assert (row["tracking"] or "none") == "none"

    def test_invalid_policy_rejected(self, make_product):
        from core.lots import lots_set_tracking
        pid = make_product()
        r = lots_set_tracking(producto_id=pid, tracking="telepathy")
        assert "error" in r
        assert "allowed" in r

    def test_untracked_product_cannot_receive_lots(self, make_product, make_warehouse):
        from core.lots import lots_receive
        pid, wid = make_product(), make_warehouse()
        r = lots_receive(producto_id=pid, warehouse_id=wid, quantity=10,
                         lot_code="L-1")
        assert "error" in r


class TestFefoConsumption:
    def _three_lots(self, pid, wid):
        from core.lots import lots_receive
        lots_receive(producto_id=pid, warehouse_id=wid, quantity=100,
                     lot_code="L-DEC", expiry_date="2026-12-31")
        lots_receive(producto_id=pid, warehouse_id=wid, quantity=100,
                     lot_code="L-SEP", expiry_date="2026-09-30")
        lots_receive(producto_id=pid, warehouse_id=wid, quantity=100,
                     lot_code="L-NOV", expiry_date="2026-11-30")

    def test_consumes_earliest_expiry_first(self, tracked_product, make_warehouse):
        from core.lots import lots_consume
        wid = make_warehouse()
        self._three_lots(tracked_product, wid)

        r = lots_consume(producto_id=tracked_product, warehouse_id=wid, quantity=150)
        codes = [c["lot_code"] for c in r["consumed"]]
        assert codes == ["L-SEP", "L-NOV"], "first expired must go out first"
        assert r["consumed"][0]["quantity"] == 100.0
        assert r["consumed"][1]["quantity"] == 50.0
        assert r["shortage"] == 0.0

    def test_untouched_lot_keeps_its_stock(self, tracked_product, make_warehouse):
        from core.lots import lots_consume, lots_list
        wid = make_warehouse()
        self._three_lots(tracked_product, wid)
        lots_consume(producto_id=tracked_product, warehouse_id=wid, quantity=150)

        balances = {l["lot_code"]: float(l["quantity"])
                    for l in lots_list(producto_id=tracked_product, only_available=1)}
        assert balances["L-DEC"] == 100.0, "the latest expiry must not be touched"
        assert balances["L-NOV"] == 50.0
        assert "L-SEP" not in balances

    def test_specific_lot_can_be_forced(self, tracked_product, make_warehouse):
        from core.lots import lots_consume, lots_list
        wid = make_warehouse()
        self._three_lots(tracked_product, wid)
        dec = next(l for l in lots_list(producto_id=tracked_product)
                   if l["lot_code"] == "L-DEC")

        r = lots_consume(producto_id=tracked_product, warehouse_id=wid,
                         quantity=20, lot_id=dec["id"])
        assert [c["lot_code"] for c in r["consumed"]] == ["L-DEC"]

    def test_shortage_is_reported_not_hidden(self, tracked_product, make_warehouse):
        from core.lots import lots_receive, lots_consume
        wid = make_warehouse()
        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=10,
                     lot_code="L-ONLY", expiry_date="2026-10-01")
        r = lots_consume(producto_id=tracked_product, warehouse_id=wid, quantity=35)
        assert r["shortage"] == 25.0

    def test_lots_without_expiry_go_last(self, tracked_product, make_warehouse):
        from core.lots import lots_receive, lots_consume
        wid = make_warehouse()
        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=50,
                     lot_code="L-NOEXP", expiry_date=None)
        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=50,
                     lot_code="L-DATED", expiry_date="2027-01-01")
        r = lots_consume(producto_id=tracked_product, warehouse_id=wid, quantity=60)
        assert r["consumed"][0]["lot_code"] == "L-DATED"


class TestSerialTracking:
    @pytest.fixture
    def serial_product(self, make_product):
        from core.lots import lots_set_tracking
        pid = make_product("EQ-1", "Equipo", 9000, 6000)
        lots_set_tracking(producto_id=pid, tracking="serial")
        return pid

    def test_quantity_must_be_one(self, serial_product, make_warehouse):
        from core.lots import lots_receive
        r = lots_receive(producto_id=serial_product, warehouse_id=make_warehouse(),
                         quantity=5, lot_code="SN-001")
        assert "error" in r
        assert "one unit" in r["error"]

    def test_single_unit_accepted(self, serial_product, make_warehouse):
        from core.lots import lots_receive
        r = lots_receive(producto_id=serial_product, warehouse_id=make_warehouse(),
                         quantity=1, lot_code="SN-001")
        assert "error" not in r
        assert r["tracking"] == "serial"

    def test_duplicate_serial_rejected(self, serial_product, make_warehouse):
        from core.lots import lots_receive
        wid = make_warehouse()
        lots_receive(producto_id=serial_product, warehouse_id=wid, quantity=1,
                     lot_code="SN-001")
        r = lots_receive(producto_id=serial_product, warehouse_id=wid, quantity=1,
                         lot_code="SN-001")
        assert "error" in r
        assert "already exists" in r["error"]

    def test_autogenerated_code_when_omitted(self, serial_product, make_warehouse):
        from core.lots import lots_receive
        r = lots_receive(producto_id=serial_product, warehouse_id=make_warehouse(),
                         quantity=1)
        assert r["lot_code"].startswith("SN-")


class TestTraceability:
    def test_trace_reconstructs_the_history(self, tracked_product, make_warehouse):
        from core.lots import lots_receive, lots_consume, lots_trace
        wid = make_warehouse()
        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=100,
                     lot_code="L-TRACE", expiry_date="2026-10-01")
        lots_consume(producto_id=tracked_product, warehouse_id=wid, quantity=30,
                     source_type="sales_order", source_id=7)

        t = lots_trace(producto_id=tracked_product, lot_code="L-TRACE")
        assert t["total_received"] == 100.0
        assert t["total_issued"] == 30.0
        assert t["on_hand"] == 70.0
        assert len(t["movements"]) == 2
        assert t["movements"][0]["direction"] == "in"
        out = t["movements"][1]
        assert out["direction"] == "out"
        assert out["source_type"] == "sales_order"
        assert out["source_id"] == 7

    def test_unknown_lot_errors(self):
        from core.lots import lots_trace
        assert "error" in lots_trace(lot_id=99999)

    def test_requires_an_identifier(self):
        from core.lots import lots_trace
        assert "error" in lots_trace()


class TestExpiryAlerts:
    def test_separates_expired_from_expiring(self, tracked_product, make_warehouse):
        from core.lots import lots_receive, lots_expiring
        from datetime import datetime, timedelta
        wid = make_warehouse()
        past = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        soon = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        far = (datetime.now() + timedelta(days=400)).strftime("%Y-%m-%d")

        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=40,
                     lot_code="L-PAST", expiry_date=past)
        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=25,
                     lot_code="L-SOON", expiry_date=soon)
        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=10,
                     lot_code="L-FAR", expiry_date=far)

        r = lots_expiring(days=30)
        assert [l["lot_code"] for l in r["expired"]] == ["L-PAST"]
        assert [l["lot_code"] for l in r["expiring_soon"]] == ["L-SOON"]
        assert r["expired_count"] == 1
        assert r["expiring_count"] == 1

    def test_consumed_lots_are_not_alerted(self, tracked_product, make_warehouse):
        from core.lots import lots_receive, lots_consume, lots_expiring
        from datetime import datetime, timedelta
        wid = make_warehouse()
        soon = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        lots_receive(producto_id=tracked_product, warehouse_id=wid, quantity=20,
                     lot_code="L-GONE", expiry_date=soon)
        lots_consume(producto_id=tracked_product, warehouse_id=wid, quantity=20)

        r = lots_expiring(days=30)
        codes = [l["lot_code"] for l in r["expired"] + r["expiring_soon"]]
        assert "L-GONE" not in codes, "a lot with no stock is not a risk"

    def test_shelf_life_derives_expiry(self, make_product, make_warehouse):
        from core.lots import lots_set_tracking, lots_receive
        pid = make_product("SL-1", "Perecedero", 50, 20)
        lots_set_tracking(producto_id=pid, tracking="lot", shelf_life_days=30)
        r = lots_receive(producto_id=pid, warehouse_id=make_warehouse(), quantity=10)
        assert r["expiry_date"] is not None, "shelf_life_days must set an expiry"
