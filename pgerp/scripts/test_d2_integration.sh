#!/usr/bin/env bash
# D2 integration: reservations + lots wired into the real sales/purchase flow
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Central&code=CEN" > /dev/null
curl -s -X POST "$API/api/clientes?token=$T" -d "nombre=Cliente Uno&email=c1@x.com" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=INT-1&nombre=Producto&precio_unitario=100&cost=0" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=1&warehouse_id=1&new_quantity=50&reason=seed" > /dev/null
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=50&unit_cost=40" > /dev/null

echo "=== A) Confirming reserves what exists and backorders the rest ==="
echo "  order 80 units when only 50 are on hand:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":80,"price":100}]}' > /dev/null
echo "  confirm:"
curl -s -X POST "$API/api/sales/orders/1/confirm?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' | head -c 300; echo ""
echo "  availability (50 on hand, 50 reserved -> 0 available):"
curl -s "$API/api/stock/availability?producto_id=1&warehouse_id=1&token=$T" | head -c 200; echo ""
echo "  backorder created for the missing 30:"
curl -s "$API/api/backorders?token=$T" | head -c 260; echo ""

echo ""
echo "=== B) A second order cannot take the reserved stock ==="
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":20,"price":100}]}' > /dev/null
echo "  confirm order 2 (all 20 must go to backorder):"
curl -s -X POST "$API/api/sales/orders/2/confirm?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":2}' | head -c 280; echo ""

echo ""
echo "=== C) Lot-tracked product flows through purchase and sale ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=MED-9&nombre=Vacuna&precio_unitario=500&cost=0" > /dev/null
curl -s -X POST "$API/api/lots/tracking?token=$T" -d "producto_id=2&tracking=lot" > /dev/null
curl -s -X POST "$API/api/suppliers?token=$T" -d "name=Farma&country=MX" > /dev/null
curl -s -X POST "$API/api/rfq?token=$T" -H "Content-Type: application/json" \
  -d '{"lines":[{"producto_id":2,"qty":60}]}' > /dev/null
curl -s -X POST "$API/api/rfq/quotes?token=$T" -H "Content-Type: application/json" \
  -d '{"rfq_id":1,"supplier_id":1,"lines":[{"producto_id":2,"qty":60,"unit_price":200}]}' > /dev/null
curl -s -X POST "$API/api/rfq/award?token=$T" -d "quote_id=1" > /dev/null
echo "  receive 60 with an explicit lot and expiry:"
curl -s -X POST "$API/api/purchase/receipts?token=$T" -H "Content-Type: application/json" \
  -d '{"purchase_order_id":1,"warehouse_id":1,"lines":[{"producto_id":2,"qty_received":60,"lot_code":"LOTE-A","expiry_date":"2026-10-15"}]}' | head -c 180; echo ""
echo "  the lot exists with its expiry:"
curl -s "$API/api/lots?producto_id=2&token=$T" | head -c 300; echo ""
echo "  sell 25 and deliver — the lot must be issued:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":2,"quantity":25,"price":500}]}' > /dev/null
curl -s -X POST "$API/api/sales/orders/3/confirm?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":3}' > /dev/null
curl -s -X POST "$API/api/sales/orders/3/deliver?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":3}' | head -c 340; echo ""
echo "  lot balance after the sale (expect 35):"
curl -s "$API/api/lots?producto_id=2&only_available=1&token=$T" | head -c 220; echo ""
echo "  full traceability of LOTE-A:"
curl -s "$API/api/lots/trace?producto_id=2&lot_code=LOTE-A&token=$T" | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
print(f\"    received {d['total_received']} issued {d['total_issued']} on hand {d['on_hand']}\")
for m in d['movements']:
    print(f\"    {m['direction']:3} {m['quantity']:6} {m['source_type'] or '-'} #{m['source_id'] or '-'}\")
" 2>/dev/null || echo "    (parse skipped)"
echo "  reservation was fulfilled, not left dangling:"
curl -s "$API/api/reservations?document_type=sales_order&document_id=3&status=fulfilled&token=$T" | head -c 200; echo ""
