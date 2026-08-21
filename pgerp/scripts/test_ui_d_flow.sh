#!/usr/bin/env bash
# End-to-end through the D1/D2/D3 screens: every call the UI buttons make.
# Assumes a FRESH database.
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Central&code=CEN" > /dev/null
curl -s -X POST "$API/api/clientes?token=$T" -d "nombre=Cliente Flujo&email=f@x.com" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=FL-1&nombre=Vacuna&precio_unitario=500&cost=0" > /dev/null

echo "=== 1) Pantalla Valuación: capa de apertura + método ==="
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=100&unit_cost=200" | head -c 150; echo ""
curl -s -X POST "$API/api/valuation/method?token=$T" \
  -d "producto_id=1&method=average" | head -c 140; echo ""
echo "  valor del inventario:"
curl -s "$API/api/valuation/stock-value?token=$T" | head -c 200; echo ""

echo ""
echo "=== 2) Pantalla Trazabilidad: seguimiento + lote + FEFO ==="
curl -s -X POST "$API/api/lots/tracking?token=$T" \
  -d "producto_id=1&tracking=lot&shelf_life_days=180" | head -c 140; echo ""
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=60&lot_code=L-OCT&expiry_date=2026-10-15" | head -c 160; echo ""
curl -s -X POST "$API/api/lots/receive?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=40&lot_code=L-DIC&expiry_date=2026-12-31" | head -c 160; echo ""
echo "  lotes ordenados por caducidad (así los consume la UI):"
curl -s "$API/api/lots?producto_id=1&only_available=1&token=$T" | python3 -c "
import json,sys
for l in json.load(sys.stdin)['result']:
    print(f\"    {l['lot_code']:8} {l['expiry_date']} qty {l['quantity']} dias {l['days_to_expiry']}\")
" 2>/dev/null

echo ""
echo "=== 3) Pantalla Trazabilidad: reserva + regla de reorden ==="
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=1&warehouse_id=1&new_quantity=100&reason=seed" > /dev/null
echo "  reservar 70 para el pedido 99:"
curl -s -X POST "$API/api/reservations?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=70&document_type=sales_order&document_id=99" | head -c 200; echo ""
echo "  disponibilidad (100 fisico - 70 reservado):"
curl -s "$API/api/stock/availability?producto_id=1&warehouse_id=1&token=$T" | head -c 200; echo ""
echo "  regla min 50 / max 200:"
curl -s -X POST "$API/api/reorder/rules?token=$T" \
  -d "producto_id=1&warehouse_id=1&min_quantity=50&max_quantity=200&multiple_of=10" | head -c 200; echo ""
echo "  sugerencia (30 disponible < 50 minimo):"
curl -s "$API/api/reorder/suggestions?token=$T" | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
for s in d['suggestions']:
    print(f\"    {s['codigo']}: fisico {s['on_hand']} reservado {s['reserved']} disponible {s['available']} -> comprar {s['suggested_quantity']}\")
" 2>/dev/null
echo "  liberar la reserva desde la UI:"
curl -s -X POST "$API/api/reservations/release?token=$T" \
  -H "Content-Type: application/json" -d '{"document_type":"sales_order","document_id":99}' | head -c 160; echo ""

echo ""
echo "=== 4) Pantalla Devoluciones: pedido -> devolucion -> nota -> aplicar ==="
curl -s -X POST "$API/api/credit/limit?token=$T" -d "cliente_id=1&credit_limit=100000" > /dev/null
echo "  pedido de 20 con 10% de descuento:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":20,"price":500,"discount_pct":10}]}' | python3 -c "
import json,sys
r=json.load(sys.stdin)['result']
print(f\"    bruto {r['gross_subtotal']} descuento {r['discount_total']} subtotal {r['subtotal']} total {r['total']}\")
" 2>/dev/null
curl -s -X POST "$API/api/sales/orders/1/confirm?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' > /dev/null
echo "  entregar (consume lote y calcula cogs):"
curl -s -X POST "$API/api/sales/orders/1/deliver?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' | head -c 260; echo ""
echo "  devolver 5 de las 20:"
curl -s -X POST "$API/api/sales-returns?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"sales_order_id":1,"warehouse_id":1,"reason":"Cadena de frio","lines":[{"producto_id":1,"quantity":5}]}' | head -c 220; echo ""
echo "  recibir (stock y costo vuelven):"
curl -s -X POST "$API/api/sales-returns/receive?token=$T" -d "return_id=1" | head -c 240; echo ""
echo "  emitir nota de credito:"
curl -s -X POST "$API/api/sales-returns/credit?token=$T" -d "return_id=1" | head -c 200; echo ""
echo "  factura de 5000 y aplicar la nota:"
curl -s -X POST "$API/api/facturas?token=$T" -d "cliente_id=1&total=5000" > /dev/null
curl -s -X POST "$API/api/credit-notes/apply?token=$T" -H "Content-Type: application/json" \
  -d '{"credit_note_id":1,"invoice_id":1}' | head -c 260; echo ""

echo ""
echo "=== 5) Pantalla Devoluciones: bloqueo por credito ==="
curl -s -X POST "$API/api/credit/limit?token=$T" -d "cliente_id=1&credit_limit=1000" > /dev/null
echo "  pedido de 50000 con limite 1000:"
curl -s -X POST "$API/api/sales/orders?token=$T" -H "Content-Type: application/json" \
  -d '{"cliente_id":1,"items":[{"producto_id":1,"quantity":100,"price":500}]}' | head -c 260; echo ""
echo "  bitacora de bloqueos:"
curl -s "$API/api/credit/events?blocked_only=1&token=$T" | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
print(f\"    {d['count']} bloqueo(s)\")
for e in d['events'][:2]:
    print(f\"      {e['event_type']}: {e['notes']}\")
" 2>/dev/null

echo ""
echo "=== 6) Pantalla Valuación: cierre de periodo bloquea asientos ==="
curl -s -X POST "$API/api/periods/generate-year?token=$T" -d "year=2026" > /dev/null
curl -s -X POST "$API/api/periods/close?token=$T" -d "year=2026&month=3" | head -c 180; echo ""
echo "  verificar fecha cerrada desde la UI:"
curl -s "$API/api/periods/check?date=2026-03-15&token=$T" | head -c 220; echo ""
echo "  COGS neto tras la devolucion:"
curl -s "$API/api/valuation/cogs?token=$T" | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
print(f\"    bruto {d['gross_cogs']} devuelto {d['returned_cost']} neto {d['total_cogs']}\")
" 2>/dev/null
