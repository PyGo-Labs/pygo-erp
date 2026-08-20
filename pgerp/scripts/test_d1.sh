#!/usr/bin/env bash
# D1 verification: inventory valuation (FIFO/average), multicurrency, period locking
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "=== A) FIFO: two layers at different costs ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=VAL-1&nombre=Widget&precio_unitario=200&cost=0" > /dev/null
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Central&code=CEN" > /dev/null
echo "  layer 1: 100 units @ 10"
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=100&unit_cost=10" | head -c 180; echo ""
echo "  layer 2: 100 units @ 14"
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=100&unit_cost=14" | head -c 180; echo ""
echo "  stock value (expect 200 units / 2400):"
curl -s "$API/api/valuation/stock-value?producto_id=1&token=$T" | head -c 240; echo ""
echo "  consume 150 under FIFO (expect 100x10 + 50x14 = 1700):"
curl -s -X POST "$API/api/valuation/consume?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=150&source_type=test" | head -c 260; echo ""
echo "  remaining value (expect 50 units / 700):"
curl -s "$API/api/valuation/stock-value?producto_id=1&token=$T" | head -c 200; echo ""

echo ""
echo "=== B) Average costing on the same layers ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=VAL-2&nombre=Gadget&precio_unitario=300&cost=0" > /dev/null
curl -s -X POST "$API/api/valuation/method?token=$T" -d "producto_id=2&method=average" | head -c 160; echo ""
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=2&warehouse_id=1&quantity=100&unit_cost=10" > /dev/null
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=2&warehouse_id=1&quantity=100&unit_cost=20" > /dev/null
echo "  consume 150 under average (expect 150 x 15 = 2250):"
curl -s -X POST "$API/api/valuation/consume?token=$T" \
  -d "producto_id=2&warehouse_id=1&quantity=150&source_type=test" | head -c 220; echo ""

echo ""
echo "=== C) Purchase receipt creates a layer at the real price ==="
curl -s -X POST "$API/api/suppliers?token=$T" -d "name=Proveedor&country=MX" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=VAL-3&nombre=Tornillo&precio_unitario=5&cost=0" > /dev/null
RFQ=$(curl -s -X POST "$API/api/rfq?token=$T" -H "Content-Type: application/json" \
  -d '{"lines":[{"producto_id":3,"qty":500}]}')
echo "  rfq: $(echo $RFQ | head -c 80)"
curl -s -X POST "$API/api/rfq/quotes?token=$T" -H "Content-Type: application/json" \
  -d '{"rfq_id":1,"supplier_id":1,"lines":[{"producto_id":3,"qty":500,"unit_price":3.5}]}' > /dev/null
curl -s -X POST "$API/api/rfq/award?token=$T" -d "quote_id=1" > /dev/null
echo "  receive 500 @ 3.5:"
curl -s -X POST "$API/api/purchase/receipts?token=$T" -H "Content-Type: application/json" \
  -d '{"purchase_order_id":1,"warehouse_id":1,"lines":[{"producto_id":3,"qty_received":500}]}' | head -c 200; echo ""
echo "  layer created automatically (expect unit_cost 3.5):"
curl -s "$API/api/valuation/layers?producto_id=3&token=$T" | head -c 300; echo ""

echo ""
echo "=== D) Sale delivery reports a REAL cogs ==="
curl -s -X POST "$API/api/clientes?token=$T" -d "nombre=Cliente Uno&email=c1@x.com" > /dev/null
echo "  order 200 units of the FIFO product:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":3,"quantity":200,"price":5}]}' | head -c 180; echo ""
curl -s -X POST "$API/api/sales/orders/1/confirm?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' > /dev/null
echo "  deliver (expect cogs = 200 x 3.5 = 700):"
curl -s -X POST "$API/api/sales/orders/1/deliver?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' | head -c 220; echo ""
echo "  COGS report:"
curl -s "$API/api/valuation/cogs?token=$T" | head -c 320; echo ""

echo ""
echo "=== E) Fiscal periods actually block postings ==="
echo "  generate 2026:"
curl -s -X POST "$API/api/periods/generate-year?token=$T" -d "year=2026" | head -c 200; echo ""
echo "  check open date:"
curl -s "$API/api/periods/check?date=2026-03-15&token=$T" | head -c 160; echo ""
echo "  post into March (should succeed):"
curl -s -X POST "$API/api/journal?token=$T" -H "Content-Type: application/json" \
  -d '{"description":"Asiento marzo","date":"2026-03-15","lines":[{"account_id":1,"debit":100,"credit":0},{"account_id":2,"debit":0,"credit":100}]}' | head -c 160; echo ""
echo "  close March:"
curl -s -X POST "$API/api/periods/close?token=$T" -d "year=2026&month=3" | head -c 200; echo ""
echo "  check the same date again:"
curl -s "$API/api/periods/check?date=2026-03-15&token=$T" | head -c 200; echo ""
echo "  post into March again (MUST be refused):"
curl -s -X POST "$API/api/journal?token=$T" -H "Content-Type: application/json" \
  -d '{"description":"Asiento tardio","date":"2026-03-20","lines":[{"account_id":1,"debit":50,"credit":0},{"account_id":2,"debit":0,"credit":50}]}' | head -c 220; echo ""
echo "  post into April (still open, should succeed):"
curl -s -X POST "$API/api/journal?token=$T" -H "Content-Type: application/json" \
  -d '{"description":"Asiento abril","date":"2026-04-05","lines":[{"account_id":1,"debit":70,"credit":0},{"account_id":2,"debit":0,"credit":70}]}' | head -c 160; echo ""
echo "  reopen March and retry (should succeed):"
curl -s -X POST "$API/api/periods/reopen?token=$T" -d "year=2026&month=3" | head -c 160; echo ""
curl -s -X POST "$API/api/journal?token=$T" -H "Content-Type: application/json" \
  -d '{"description":"Asiento reabierto","date":"2026-03-25","lines":[{"account_id":1,"debit":30,"credit":0},{"account_id":2,"debit":0,"credit":30}]}' | head -c 160; echo ""

echo ""
echo "=== F) Multicurrency and FX differences ==="
echo "  rate lookup (USD against the configured base):"
curl -s "$API/api/fx/rate?currency=USD&token=$T" | head -c 180; echo ""
echo "  convert 1000 USD to the base currency:"
curl -s "$API/api/fx/convert?amount=1000&from_currency=USD&to_currency=MXN&token=$T" | head -c 300; echo ""
echo "  stamp an invoice with currency + rate:"
curl -s -X POST "$API/api/facturas?token=$T" -d "cliente_id=1&total=10000" > /dev/null
curl -s -X POST "$API/api/fx/document-rate?token=$T" \
  -d "document_type=invoice&document_id=1&currency=USD&exchange_rate=17.50" | head -c 200; echo ""
echo "  settle at a higher rate -> realised GAIN (10000 x (18.10-17.50) = 6000):"
curl -s -X POST "$API/api/fx/differences?token=$T" -H "Content-Type: application/json" \
  -d '{"document_type":"invoice","document_id":1,"amount_currency":10000,"payment_rate":18.10}' | head -c 320; echo ""
echo "  settle at a lower rate -> realised LOSS:"
curl -s -X POST "$API/api/facturas?token=$T" -d "cliente_id=1&total=5000" > /dev/null
curl -s -X POST "$API/api/fx/document-rate?token=$T" \
  -d "document_type=invoice&document_id=2&currency=USD&exchange_rate=17.50" > /dev/null
curl -s -X POST "$API/api/fx/differences?token=$T" -H "Content-Type: application/json" \
  -d '{"document_type":"invoice","document_id":2,"amount_currency":5000,"payment_rate":17.00}' | head -c 280; echo ""
echo "  same rate -> nothing recorded:"
curl -s -X POST "$API/api/fx/differences?token=$T" -H "Content-Type: application/json" \
  -d '{"document_type":"invoice","document_id":1,"amount_currency":1000,"payment_rate":17.50}' | head -c 220; echo ""
echo "  differences report (net effect):"
curl -s "$API/api/fx/differences?token=$T" | head -c 200; echo ""
echo "  currency exposure:"
curl -s "$API/api/fx/exposure?token=$T" | head -c 300; echo ""
