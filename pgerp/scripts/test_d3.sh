#!/usr/bin/env bash
# D3 verification: sales returns + credit notes + line discounts + credit limits
# Assumes a FRESH database (ids start at 1).
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Central&code=CEN" > /dev/null
curl -s -X POST "$API/api/clientes?token=$T" -d "nombre=Cliente Uno&email=c1@x.com" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=D3-1&nombre=Producto&precio_unitario=100&cost=60" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=1&warehouse_id=1&new_quantity=200&reason=seed" > /dev/null
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=200&unit_cost=60" > /dev/null

echo "=== A) Line discounts change the totals ==="
echo "  order 10 x 100 with 20% discount (expect gross 1000, discount 200, subtotal 800):"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":10,"price":100,"discount_pct":20}]}' | head -c 300; echo ""
echo "  invalid discount 150% must be rejected:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":1,"price":100,"discount_pct":150}]}' | head -c 200; echo ""
echo "  mixed lines, only one discounted:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":5,"price":100,"discount_pct":10},{"producto_id":1,"quantity":5,"price":100}]}' | head -c 260; echo ""

echo ""
echo "=== B) Credit limit blocks over-selling ==="
echo "  set limit 2000:"
curl -s -X POST "$API/api/credit/limit?token=$T" -d "cliente_id=1&credit_limit=2000" | head -c 180; echo ""
echo "  current exposure:"
curl -s "$API/api/credit/exposure?cliente_id=1&token=$T" | head -c 320; echo ""
echo "  check an extra 500:"
curl -s "$API/api/credit/check?cliente_id=1&amount=500&token=$T" | head -c 260; echo ""
echo "  order for 5000 must be REFUSED:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":50,"price":100}]}' | head -c 340; echo ""
echo "  raise the limit to 50000 and retry (must succeed):"
curl -s -X POST "$API/api/credit/limit?token=$T" -d "cliente_id=1&credit_limit=50000" > /dev/null
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":50,"price":100}]}' | head -c 180; echo ""
echo "  put the customer on hold -> everything is refused:"
curl -s -X POST "$API/api/credit/limit?token=$T" -d "cliente_id=1&credit_hold=1" | head -c 160; echo ""
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":1,"price":100}]}' | head -c 220; echo ""
curl -s -X POST "$API/api/credit/limit?token=$T" -d "cliente_id=1&credit_hold=0" > /dev/null

echo ""
echo "=== C) Sales return: goods back, cost back, credit note out ==="
echo "  confirm and deliver order 1 (10 units):"
curl -s -X POST "$API/api/sales/orders/1/confirm?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' > /dev/null
curl -s -X POST "$API/api/sales/orders/1/deliver?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' | head -c 180; echo ""
echo "  return 4 of the 10 sold:"
curl -s -X POST "$API/api/sales-returns?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"sales_order_id":1,"warehouse_id":1,"reason":"Producto danado","lines":[{"producto_id":1,"quantity":4}]}' | head -c 300; echo ""
echo "  returning 20 (more than sold) must be REFUSED:"
curl -s -X POST "$API/api/sales-returns?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"sales_order_id":1,"warehouse_id":1,"lines":[{"producto_id":1,"quantity":20}]}' | head -c 260; echo ""
echo "  credit before receiving must be REFUSED:"
curl -s -X POST "$API/api/sales-returns/credit?token=$T" -d "return_id=1" | head -c 200; echo ""
echo "  receive the goods (stock and cost layer return):"
curl -s -X POST "$API/api/sales-returns/receive?token=$T" -d "return_id=1" | head -c 320; echo ""
echo "  issue the credit note:"
curl -s -X POST "$API/api/sales-returns/credit?token=$T" -d "return_id=1" | head -c 240; echo ""
echo "  a second return of 8 must be REFUSED (only 6 left of the 10):"
curl -s -X POST "$API/api/sales-returns?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"sales_order_id":1,"warehouse_id":1,"lines":[{"producto_id":1,"quantity":8}]}' | head -c 260; echo ""

echo ""
echo "=== D) Credit note applied to an invoice ==="
echo "  invoice for 1000:"
curl -s -X POST "$API/api/facturas?token=$T" -d "cliente_id=1&total=1000" | head -c 140; echo ""
echo "  credit notes available:"
curl -s "$API/api/credit-notes?cliente_id=1&token=$T" | head -c 300; echo ""
echo "  apply 320 of the note to the invoice:"
curl -s -X POST "$API/api/credit-notes/apply?token=$T" -H "Content-Type: application/json" \
  -d '{"credit_note_id":1,"invoice_id":1,"amount":320}' | head -c 320; echo ""
echo "  over-applying must be REFUSED:"
curl -s -X POST "$API/api/credit-notes/apply?token=$T" -H "Content-Type: application/json" \
  -d '{"credit_note_id":1,"invoice_id":1,"amount":9999}' | head -c 240; echo ""
echo "  an applied note cannot be cancelled:"
curl -s -X POST "$API/api/credit-notes/cancel?token=$T" -d "credit_note_id=1" | head -c 200; echo ""

echo ""
echo "=== E) Credit audit trail ==="
echo "  blocked decisions recorded:"
curl -s "$API/api/credit/events?cliente_id=1&blocked_only=1&token=$T" | head -c 340; echo ""
echo "  exposure now nets the open credit note:"
curl -s "$API/api/credit/exposure?cliente_id=1&token=$T" | head -c 340; echo ""
echo "  inventory value after the return:"
curl -s "$API/api/valuation/stock-value?producto_id=1&token=$T" | head -c 220; echo ""
