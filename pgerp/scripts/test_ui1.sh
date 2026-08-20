#!/usr/bin/env bash
# UI-1 verification: pages serve as HTML and the flows they drive actually work
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "=== A) Pages serve real HTML ==="
for v in /ventas /compras /inventario /setup /; do
  read -r code ctype < <(curl -s -o /tmp/p.html -w "%{http_code} %{content_type}\n" "$API$v")
  size=$(wc -c < /tmp/p.html)
  alpine=$(grep -c 'x-data=' /tmp/p.html)
  printf "  %-12s %s  %-26s %6sB  alpine:%s\n" "$v" "$code" "$ctype" "$size" "$alpine"
done

echo ""
echo "=== B) Sales flow the /ventas page drives ==="
curl -s -X POST "$API/api/clientes?token=$T" -d "nombre=UI Test Client&email=ui@test.com" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=UI-P1&nombre=UI Product&precio_unitario=250&cost=150" > /dev/null
echo "  order create (API expects items, not lines):"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":4,"price":250}]}' | head -c 200; echo ""
echo "  tax preview (what the form calls):"
curl -s -X POST "$API/api/tax/compute-document?token=$T" -H "Content-Type: application/json" \
  -d '{"lines":[{"amount":1000,"quantity":1}]}' | head -c 200; echo ""
echo "  stock the product so delivery can succeed:"
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Sales WH&code=SWH" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=1&warehouse_id=1&new_quantity=50&reason=seed for delivery" | head -c 120; echo ""
echo "  confirm -> deliver -> invoice (order_id passed in body):"
for a in confirm deliver invoice; do
  printf "    %-8s " "$a"
  curl -s -X POST "$API/api/sales/orders/1/$a?token=$T" \
    -H "Content-Type: application/json" -d '{"order_id":1}' | head -c 150; echo ""
done

echo ""
echo "=== C) Purchase flow the /compras page drives ==="
curl -s -X POST "$API/api/suppliers?token=$T" -d "name=UI Supplier&country=MX&lead_time_days=7" > /dev/null
echo "  rfq create (10 units so a partial receipt is meaningful):"
curl -s -X POST "$API/api/rfq?token=$T" -H "Content-Type: application/json" \
  -d '{"lines":[{"producto_id":1,"qty":10}]}' | head -c 160; echo ""
echo "  quote submit:"
curl -s -X POST "$API/api/rfq/quotes?token=$T" -H "Content-Type: application/json" \
  -d '{"rfq_id":1,"supplier_id":1,"delivery_days":7,"lines":[{"producto_id":1,"qty":10,"unit_price":140}]}' | head -c 160; echo ""
echo "  compare:"
curl -s "$API/api/rfq/compare?rfq_id=1&token=$T" | head -c 250; echo ""
echo "  award:"
curl -s -X POST "$API/api/rfq/award?token=$T" -d "quote_id=1" | head -c 180; echo ""
echo "  purchase orders awaiting receipt (what the page lists):"
curl -s "$API/api/sales/purchase?token=$T" | head -c 220; echo ""
echo "  pending lines for PO 1:"
curl -s "$API/api/purchase/receipts/pending?purchase_order_id=1&token=$T" | head -c 250; echo ""
echo "  register partial receipt (6 of 10):"
curl -s -X POST "$API/api/purchase/receipts?token=$T" -H "Content-Type: application/json" \
  -d '{"purchase_order_id":1,"warehouse_id":1,"lines":[{"producto_id":1,"qty_received":6}]}' | head -c 220; echo ""

echo ""
echo "=== D) Inventory flow the /inventario page drives ==="
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=UI WH A&code=UIA" > /dev/null
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=UI WH B&code=UIB" > /dev/null
echo "  adjust:"
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=1&warehouse_id=1&new_quantity=100&reason=UI test" | head -c 160; echo ""
echo "  transfer 30 from WH1 to WH2 (API expects from_warehouse/to_warehouse):"
curl -s -X POST "$API/api/inventory/stock/transfer?token=$T" -H "Content-Type: application/json" \
  -d '{"product_id":1,"from_warehouse":1,"to_warehouse":2,"quantity":30}' | head -c 180; echo ""
echo "  stock after:"
curl -s "$API/api/inventory/stock?token=$T" | head -c 300; echo ""
echo "  movements:"
curl -s "$API/api/inventory/stock/movements?token=$T" | head -c 200; echo ""
echo "  alerts:"
curl -s "$API/api/inventory/stock/alerts?token=$T" | head -c 150; echo ""
