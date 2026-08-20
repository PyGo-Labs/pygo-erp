#!/usr/bin/env bash
# Full B2 purchasing cycle smoke test
set -e
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

curl -s -X POST "$API/api/productos?token=$T" -d "codigo=WID-1&nombre=Widget&precio=100" > /dev/null
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Main WH&code=MAIN" > /dev/null
curl -s -X POST "$API/api/suppliers?token=$T" -d "name=Acme Supply&country=US&lead_time_days=5" > /dev/null
curl -s -X POST "$API/api/suppliers?token=$T" -d "name=Global Parts&country=DE&lead_time_days=12" > /dev/null

echo "1) RFQ"
curl -s -X POST "$API/api/rfq?token=$T" -H "Content-Type: application/json" \
  -d '{"lines":[{"producto_id":1,"qty":100}]}'
echo ""

curl -s -X POST "$API/api/rfq/1/send?token=$T" > /dev/null

echo "2) Quotes"
curl -s -X POST "$API/api/rfq/quotes?token=$T" -H "Content-Type: application/json" \
  -d '{"rfq_id":1,"supplier_id":1,"lead_time_days":5,"lines":[{"producto_id":1,"qty":100,"unit_price":95}]}'
echo ""
curl -s -X POST "$API/api/rfq/quotes?token=$T" -H "Content-Type: application/json" \
  -d '{"rfq_id":1,"supplier_id":2,"lead_time_days":12,"lines":[{"producto_id":1,"qty":100,"unit_price":88}]}'
echo ""

echo "3) Award cheapest"
curl -s -X POST "$API/api/rfq/award?token=$T" -d "quote_id=2&warehouse_id=1"
echo ""

echo "4) Partial receipt 40/100"
curl -s -X POST "$API/api/purchase/receipts?token=$T" -H "Content-Type: application/json" \
  -d '{"purchase_order_id":1,"warehouse_id":1,"lines":[{"producto_id":1,"qty_received":40}]}'
echo ""

echo "5) Pending after partial"
curl -s "$API/api/purchase/receipts/pending?purchase_order_id=1&token=$T"
echo ""

echo "6) Stock after receipt"
curl -s "$API/api/inventory/stock?token=$T"
echo ""

echo "7) Receive remaining 60"
curl -s -X POST "$API/api/purchase/receipts?token=$T" -H "Content-Type: application/json" \
  -d '{"purchase_order_id":1,"warehouse_id":1,"lines":[{"producto_id":1,"qty_received":60}]}'
echo ""

echo "8) Over-receive should fail"
curl -s -X POST "$API/api/purchase/receipts?token=$T" -H "Content-Type: application/json" \
  -d '{"purchase_order_id":1,"warehouse_id":1,"lines":[{"producto_id":1,"qty_received":5}]}'
echo ""

echo "9) Return 10 units from receipt 1"
curl -s -X POST "$API/api/purchase/returns?token=$T" -H "Content-Type: application/json" \
  -d '{"receipt_id":1,"reason":"damaged","lines":[{"producto_id":1,"qty":10}]}'
echo ""

echo "10) Final stock (expect 90)"
curl -s "$API/api/inventory/stock?token=$T"
echo ""

echo "11) Best supplier price for 100u"
curl -s -X POST "$API/api/suppliers/agreements?token=$T" -d "supplier_id=1&producto_id=1&price=95&min_qty=1" > /dev/null
curl -s -X POST "$API/api/suppliers/agreements?token=$T" -d "supplier_id=2&producto_id=1&price=88&min_qty=50" > /dev/null
curl -s "$API/api/suppliers/best-price?producto_id=1&qty=100&token=$T"
echo ""
