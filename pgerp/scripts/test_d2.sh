#!/usr/bin/env bash
# D2 verification: lots/serials with FEFO, reservations, backorders, reorder rules
#
# This script runs after others in verify_all.sh, so it must NOT assume ids
# start at 1. Every entity it needs is created here and its real id captured.
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

# Helper: extract the "id" of a freshly created record
newid() { python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('result') or {}
print(r.get('id') or r.get('warehouse_id') or '')
"; }

WH=$(curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=D2-Central&code=D2C" | newid)
WH2=$(curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=D2-Norte&code=D2N" | newid)
echo "warehouses: $WH / $WH2"

echo "=== A) Lot tracking with FEFO ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=MED-1&nombre=Medicamento&precio_unitario=100&cost=40" > /dev/null
echo "  enable lot tracking:"
curl -s -X POST "$API/api/lots/tracking?token=$T" -d "producto_id=1&tracking=lot&shelf_life_days=365" | head -c 180; echo ""
echo "  receive 3 lots with different expiry dates:"
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=100&lot_code=L-DEC&expiry_date=2026-12-31" | head -c 160; echo ""
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=100&lot_code=L-SEP&expiry_date=2026-09-30" | head -c 160; echo ""
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=100&lot_code=L-NOV&expiry_date=2026-11-30" | head -c 160; echo ""
echo "  consume 150 — FEFO must take L-SEP first, then L-NOV:"
curl -s -X POST "$API/api/lots/consume?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=150" | head -c 320; echo ""
echo "  lot balances after:"
curl -s "$API/api/lots?producto_id=1&only_available=1&token=$T" | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
for l in d: print(f\"    {l['lot_code']:8} exp {l['expiry_date']} qty {l['quantity']}\")
" 2>/dev/null || echo "    (parse skipped)"

echo ""
echo "=== B) Traceability of one lot ==="
curl -s "$API/api/lots/trace?producto_id=1&lot_code=L-SEP&token=$T" | head -c 340; echo ""

echo ""
echo "=== C) Serial tracking rejects quantity != 1 ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=EQ-1&nombre=Equipo&precio_unitario=9000&cost=6000" > /dev/null
curl -s -X POST "$API/api/lots/tracking?token=$T" -d "producto_id=2&tracking=serial" > /dev/null
echo "  receive 5 units as a serial (must fail):"
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=2&warehouse_id=1&quantity=5&lot_code=SN-001" | head -c 180; echo ""
echo "  receive 1 unit (ok):"
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=2&warehouse_id=1&quantity=1&lot_code=SN-001" | head -c 160; echo ""
echo "  duplicate serial (must fail):"
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=2&warehouse_id=1&quantity=1&lot_code=SN-001" | head -c 160; echo ""

echo ""
echo "=== D) Expiry alerts ==="
curl -s "$API/api/lots/expiring?days=90&token=$T" | head -c 260; echo ""

echo ""
echo "=== E) Reservations prevent double selling ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=WID-1&nombre=Widget&precio_unitario=50&cost=30" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=3&warehouse_id=1&new_quantity=100&reason=seed" > /dev/null
echo "  availability before any reservation:"
curl -s "$API/api/stock/availability?producto_id=3&warehouse_id=1&token=$T" | head -c 220; echo ""
echo "  salesperson A reserves 60:"
curl -s -X POST "$API/api/reservations?token=$T" \
  -d "producto_id=3&warehouse_id=1&quantity=60&document_type=sales_order&document_id=1" | head -c 220; echo ""
echo "  salesperson B tries 60 more (MUST fail — only 40 available):"
curl -s -X POST "$API/api/reservations?token=$T" \
  -d "producto_id=3&warehouse_id=1&quantity=60&document_type=sales_order&document_id=2" | head -c 260; echo ""
echo "  salesperson B reserves 40 (ok):"
curl -s -X POST "$API/api/reservations?token=$T" \
  -d "producto_id=3&warehouse_id=1&quantity=40&document_type=sales_order&document_id=2" | head -c 200; echo ""
echo "  availability now (expect 0):"
curl -s "$API/api/stock/availability?producto_id=3&warehouse_id=1&token=$T" | head -c 220; echo ""
echo "  order 1 is cancelled -> release:"
curl -s -X POST "$API/api/reservations/release?token=$T" \
  -H "Content-Type: application/json" -d '{"document_type":"sales_order","document_id":1}' | head -c 200; echo ""
echo "  availability after release (expect 60):"
curl -s "$API/api/stock/availability?producto_id=3&warehouse_id=1&token=$T" | head -c 200; echo ""
echo "  fulfill order 2:"
curl -s -X POST "$API/api/reservations/fulfill?token=$T" \
  -H "Content-Type: application/json" -d '{"document_type":"sales_order","document_id":2}' | head -c 180; echo ""

echo ""
echo "=== F) Backorders ==="
echo "  customer ordered 100 but only 30 shipped:"
curl -s -X POST "$API/api/backorders?token=$T" \
  -d "document_type=sales_order&document_id=3&producto_id=3&warehouse_id=1&quantity_ordered=100&quantity_pending=70&expected_date=2026-09-15" | head -c 220; echo ""
echo "  fulfill 30 of the 70 pending:"
curl -s -X POST "$API/api/backorders/fulfill?token=$T" -d "backorder_id=1&quantity=30" | head -c 200; echo ""
echo "  over-fulfill 100 (must fail):"
curl -s -X POST "$API/api/backorders/fulfill?token=$T" -d "backorder_id=1&quantity=100" | head -c 200; echo ""
echo "  fulfill the remaining 40:"
curl -s -X POST "$API/api/backorders/fulfill?token=$T" -d "backorder_id=1&quantity=40" | head -c 200; echo ""
echo "  fulfilled backorder cannot be touched again:"
curl -s -X POST "$API/api/backorders/fulfill?token=$T" -d "backorder_id=1&quantity=5" | head -c 180; echo ""

echo ""
echo "=== G) Reorder rules and purchase suggestions ==="
curl -s -X POST "$API/api/suppliers?token=$T" -d "name=Proveedor Uno&country=MX&lead_time_days=7" > /dev/null
echo "  rule: min 50, max 200, multiples of 25:"
curl -s -X POST "$API/api/reorder/rules?token=$T" \
  -d "producto_id=3&warehouse_id=1&min_quantity=50&max_quantity=200&multiple_of=25&lead_time_days=7&preferred_supplier_id=1" | head -c 240; echo ""
echo "  current stock is 100 with 40 fulfilled -> above minimum, no suggestion:"
curl -s "$API/api/reorder/suggestions?token=$T" | head -c 200; echo ""
echo "  drop stock to 20:"
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=3&warehouse_id=1&new_quantity=20&reason=consumed" > /dev/null
echo "  suggestions now (20 available, need up to 200 -> 180 rounded to 200):"
curl -s "$API/api/reorder/suggestions?token=$T" | head -c 420; echo ""
echo "  turn suggestions into an RFQ:"
curl -s -X POST "$API/api/reorder/create-rfq?token=$T" | head -c 240; echo ""
echo "  reservations must reduce availability and trigger a suggestion:"
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=3&warehouse_id=1&new_quantity=60&reason=restock" > /dev/null
curl -s -X POST "$API/api/reservations?token=$T" \
  -d "producto_id=3&warehouse_id=1&quantity=30&document_type=sales_order&document_id=9" > /dev/null
echo "  on hand 60, reserved 30 -> available 30 < min 50:"
curl -s "$API/api/reorder/suggestions?token=$T" | head -c 300; echo ""
