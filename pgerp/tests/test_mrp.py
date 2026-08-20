"""Tests for MRP: multi-level BOM explosion, costing, production lifecycle."""
import pytest


@pytest.fixture
def bike_bom(make_product):
    """Two-level structure: Bici -> 2 Ruedas (-> 1 Rim + 32 Radios) + 1 Cuadro."""
    from core.mrp_bom import boms_create
    bici = make_product("BICI", "Bicicleta", 5000, 0)
    rueda = make_product("RUEDA", "Rueda", 800, 0)
    rim = make_product("RIM", "Rim", 400, 400)
    radio = make_product("RADIO", "Radio", 10, 10)
    cuadro = make_product("CUADRO", "Cuadro", 1200, 1200)

    boms_create(producto_id=rueda, quantity=1,
               lines=[{"component_id": rim, "quantity": 1},
                      {"component_id": radio, "quantity": 32}])
    boms_create(producto_id=bici, quantity=1,
               lines=[{"component_id": rueda, "quantity": 2},
                      {"component_id": cuadro, "quantity": 1}])
    return {"bici": bici, "rueda": rueda, "rim": rim,
            "radio": radio, "cuadro": cuadro}


class TestBomExplosion:
    def test_requires_product(self):
        from core.mrp_bom import boms_create
        assert "error" in boms_create(lines=[{"component_id": 1, "quantity": 1}])

    def test_product_cannot_be_its_own_component(self, make_product):
        from core.mrp_bom import boms_create
        pid = make_product()
        r = boms_create(producto_id=pid, quantity=1,
                       lines=[{"component_id": pid, "quantity": 1}])
        assert "error" in r, "a product must not be a component of itself"

    def test_explosion_resolves_sub_assemblies(self, bike_bom):
        from core.mrp_bom import boms_explode
        r = boms_explode(producto_id=bike_bom["bici"], quantity=10)
        assert "error" not in r, r

        raw = {m["component_id"]: float(m["qty_required"]) for m in r["raw_materials"]}
        # 10 bikes -> 20 wheels -> 20 rims and 640 spokes, plus 10 frames
        assert raw[bike_bom["rim"]] == 20.0
        assert raw[bike_bom["radio"]] == 640.0
        assert raw[bike_bom["cuadro"]] == 10.0
        # The sub-assembly itself is not raw material
        assert bike_bom["rueda"] not in raw

    def test_scrap_increases_requirement(self, make_product):
        from core.mrp_bom import boms_create, boms_explode
        mesa = make_product("MESA", "Mesa", 3000, 0)
        pata = make_product("PATA", "Pata", 150, 150)
        boms_create(producto_id=mesa, quantity=1,
                   lines=[{"component_id": pata, "quantity": 4, "scrap_pct": 5}])

        r = boms_explode(producto_id=mesa, quantity=10)
        raw = {m["component_id"]: float(m["qty_required"]) for m in r["raw_materials"]}
        # 4 x 10 x 1.05 = 42
        assert raw[pata] == 42.0

    def test_material_cost_uses_price_when_cost_unset(self, make_product):
        from core.mrp_bom import boms_create, boms_explode
        prod = make_product("X", "X", 1000, 0)
        comp = make_product("C", "C", 250, 0)  # cost 0, price 250
        boms_create(producto_id=prod, quantity=1,
                   lines=[{"component_id": comp, "quantity": 2}])
        r = boms_explode(producto_id=prod, quantity=1)
        assert float(r["total_material_cost"]) == 500.0, (
            "cost must fall back to precio_unitario when cost is zero")

    def test_explosion_scales_linearly(self, bike_bom):
        from core.mrp_bom import boms_explode
        one = boms_explode(producto_id=bike_bom["bici"], quantity=1)
        ten = boms_explode(producto_id=bike_bom["bici"], quantity=10)
        assert float(ten["total_material_cost"]) == pytest.approx(
            float(one["total_material_cost"]) * 10, abs=0.01)


class TestBomCosting:
    def test_labor_cost_from_routing(self, make_product):
        from core.mrp_bom import boms_create, boms_cost
        from core.mrp_production import work_centers_create, routings_create
        mesa = make_product("MESA", "Mesa", 3000, 0)
        madera = make_product("MAD", "Madera", 200, 200)

        wc = work_centers_create(name="Linea", cost_per_hour=450, efficiency_pct=100)
        routing = routings_create(name="Ensamble", operations=[
            {"sequence": 10, "name": "Cortar", "work_center_id": wc["id"],
             "setup_minutes": 20, "minutes_per_unit": 10},
            {"sequence": 20, "name": "Ensamblar", "work_center_id": wc["id"],
             "setup_minutes": 10, "minutes_per_unit": 15},
        ])
        boms_create(producto_id=mesa, quantity=1, routing_id=routing["id"],
                   lines=[{"component_id": madera, "quantity": 1}])

        r = boms_cost(producto_id=mesa, quantity=10)
        # op1: 20 + 10*10 = 120 min -> 2h -> 900 ; op2: 10 + 15*10 = 160 min -> 1200
        assert float(r["labor_cost"]) == 2100.0
        assert float(r["material_cost"]) == 2000.0
        assert float(r["total_cost"]) == 4100.0
        assert float(r["unit_cost"]) == 410.0


class TestProductionLifecycle:
    def _order(self, bike_bom, make_warehouse, qty=10):
        from core.mrp_production import production_create
        wid = make_warehouse("Planta", "PLA")
        order = production_create(producto_id=bike_bom["bici"], quantity=qty,
                                  warehouse_id=wid)
        return order, wid

    def test_order_captures_costs(self, bike_bom, make_warehouse):
        order, _ = self._order(bike_bom, make_warehouse)
        assert "error" not in order, order
        assert float(order["material_cost"]) > 0
        assert order["status"] == "draft"

    def test_availability_reports_shortages(self, bike_bom, make_warehouse):
        from core.mrp_production import production_check_availability
        order, _ = self._order(bike_bom, make_warehouse)
        avail = production_check_availability(order_id=order["id"])
        assert avail["can_produce"] is False
        assert all(m["shortage"] > 0 for m in avail["materials"])

    def test_cannot_start_without_stock(self, bike_bom, make_warehouse):
        from core.mrp_production import production_start
        order, _ = self._order(bike_bom, make_warehouse)
        r = production_start(order_id=order["id"])
        assert "error" in r
        assert r.get("shortages"), "the error must list what is missing"

    def test_start_consumes_materials(self, bike_bom, make_warehouse, make_stock, db_conn):
        from core.mrp_production import production_start, production_check_availability
        order, wid = self._order(bike_bom, make_warehouse)
        make_stock(bike_bom["rim"], wid, 30)
        make_stock(bike_bom["radio"], wid, 700)
        make_stock(bike_bom["cuadro"], wid, 15)

        assert production_check_availability(order_id=order["id"])["can_produce"] is True
        r = production_start(order_id=order["id"])
        assert "error" not in r, r
        assert r["status"] == "in_progress"

        rim = db_conn.execute(
            "SELECT quantity FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (bike_bom["rim"], wid)).fetchone()["quantity"]
        assert float(rim) == 10.0, "20 rims consumed from 30"

    def test_complete_partial_scales_cost_and_yield(self, bike_bom, make_warehouse,
                                                    make_stock, db_conn):
        from core.mrp_production import production_start, production_complete
        order, wid = self._order(bike_bom, make_warehouse)
        make_stock(bike_bom["rim"], wid, 30)
        make_stock(bike_bom["radio"], wid, 700)
        make_stock(bike_bom["cuadro"], wid, 15)
        production_start(order_id=order["id"])

        r = production_complete(order_id=order["id"], quantity_produced=9)
        assert "error" not in r, r
        assert r["status"] == "done"
        assert float(r["yield_pct"]) == 90.0
        assert float(r["total_cost"]) == pytest.approx(
            float(order["total_cost"]) * 0.9, abs=0.01)

        produced = db_conn.execute(
            "SELECT quantity FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (bike_bom["bici"], wid)).fetchone()
        assert float(produced["quantity"]) == 9.0

    def test_cancel_returns_consumed_materials(self, bike_bom, make_warehouse,
                                               make_stock, db_conn):
        from core.mrp_production import production_start, production_cancel
        order, wid = self._order(bike_bom, make_warehouse)
        make_stock(bike_bom["rim"], wid, 30)
        make_stock(bike_bom["radio"], wid, 700)
        make_stock(bike_bom["cuadro"], wid, 15)
        production_start(order_id=order["id"])

        r = production_cancel(order_id=order["id"])
        assert "error" not in r, r
        rim = db_conn.execute(
            "SELECT quantity FROM stock WHERE producto_id = ? AND warehouse_id = ?",
            (bike_bom["rim"], wid)).fetchone()["quantity"]
        assert float(rim) == 30.0, "cancelling must return the consumed stock"

    def test_dashboard_counts_finished_order(self, bike_bom, make_warehouse, make_stock):
        from core.mrp_production import (production_start, production_complete,
                                         mrp_dashboard)
        order, wid = self._order(bike_bom, make_warehouse)
        make_stock(bike_bom["rim"], wid, 30)
        make_stock(bike_bom["radio"], wid, 700)
        make_stock(bike_bom["cuadro"], wid, 15)
        production_start(order_id=order["id"])
        production_complete(order_id=order["id"], quantity_produced=10)

        d = mrp_dashboard()
        assert d["orders_by_status"]["done"] == 1
        assert float(d["total_produced_qty"]) == 10.0
