#!/usr/bin/env bash
# B5 MRP smoke test: multi-level BOM, work centers, routing, production order lifecycle
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "0) Products: 1=Bicycle(final) 2=Wheel(subassembly) 3=Rim 4=Spoke 5=Frame"
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=BIKE&nombre=Bicycle&precio=800" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=WHEEL&nombre=Wheel&precio=90" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=RIM&nombre=Rim&precio=40" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=SPOKE&nombre=Spoke&precio=1" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=FRAME&nombre=Frame&precio=200" > /dev/null
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Factory&code=FACT" > /dev/null
echo "   products created"

echo "1) Work center + routing"
curl -s -X POST "$API/api/mrp/work-centers?token=$T" \
  -d "name=Assembly Line&code=ASM&cost_per_hour=60&efficiency_pct=100&cost_center_id=4"; echo ""
curl -s -X POST "$API/api/mrp/routings?token=$T" -H "Content-Type: application/json" \
  -d '{"name":"Bicycle Assembly","code":"RT-BIKE","operations":[{"sequence":10,"name":"Assemble wheels","work_center_id":1,"setup_minutes":30,"minutes_per_unit":15},{"sequence":20,"name":"Final assembly","work_center_id":1,"setup_minutes":15,"minutes_per_unit":25}]}'; echo ""

echo "2) BOM level 2: Wheel = 1 Rim + 32 Spokes"
curl -s -X POST "$API/api/mrp/boms?token=$T" -H "Content-Type: application/json" \
  -d '{"producto_id":2,"quantity":1,"code":"BOM-WHEEL","lines":[{"component_id":3,"quantity":1},{"component_id":4,"quantity":32,"scrap_pct":5}]}'; echo ""

echo "3) BOM level 1: Bicycle = 2 Wheels + 1 Frame (routing 1)"
curl -s -X POST "$API/api/mrp/boms?token=$T" -H "Content-Type: application/json" \
  -d '{"producto_id":1,"quantity":1,"code":"BOM-BIKE","routing_id":1,"lines":[{"component_id":2,"quantity":2},{"component_id":5,"quantity":1}]}'; echo ""

echo "4) Self-component must fail"
curl -s -X POST "$API/api/mrp/boms?token=$T" -H "Content-Type: application/json" \
  -d '{"producto_id":1,"lines":[{"component_id":1,"quantity":1}]}'; echo ""

echo "5) Explode 10 bicycles (expect Rim 20, Spoke 672, Frame 10)"
curl -s "$API/api/mrp/boms/explode?producto_id=1&quantity=10&token=$T" | head -c 700; echo ""

echo "6) Full cost for 10 bicycles (materials + labor)"
curl -s "$API/api/mrp/boms/cost?producto_id=1&quantity=10&token=$T" | head -c 600; echo ""

echo "7) Production order for 10 bicycles"
curl -s -X POST "$API/api/mrp/production?token=$T" \
  -d "producto_id=1&quantity=10&warehouse_id=1&cost_center_id=4"; echo ""

echo "8) Availability check (no stock yet -> cannot produce)"
curl -s "$API/api/mrp/production/availability?order_id=1&token=$T" | head -c 500; echo ""

echo "9) Start without stock must fail"
curl -s -X POST "$API/api/mrp/production/start?token=$T" -d "order_id=1" | head -c 300; echo ""

echo "10) Stock the raw materials"
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" -d "product_id=3&warehouse_id=1&new_quantity=20&reason=initial" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" -d "product_id=4&warehouse_id=1&new_quantity=700&reason=initial" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" -d "product_id=5&warehouse_id=1&new_quantity=10&reason=initial" > /dev/null
curl -s "$API/api/mrp/production/availability?order_id=1&token=$T" | head -c 200; echo ""

echo "11) Start production (consumes materials)"
curl -s -X POST "$API/api/mrp/production/start?token=$T" -d "order_id=1"; echo ""

echo "12) Stock after consumption (Rim/Spoke/Frame should drop)"
curl -s "$API/api/inventory/stock?token=$T" | head -c 500; echo ""

echo "13) Complete production (9 of 10 -> 90% yield)"
curl -s -X POST "$API/api/mrp/production/complete?token=$T" -d "order_id=1&quantity_produced=9"; echo ""

echo "14) Stock after output (Bicycle = 9)"
curl -s "$API/api/inventory/stock?token=$T" | head -c 400; echo ""

echo "15) MRP dashboard"
curl -s "$API/api/mrp/dashboard?token=$T"; echo ""

echo "16) Cancel a fresh order and verify material return"
curl -s -X POST "$API/api/mrp/production?token=$T" -d "producto_id=2&quantity=1&warehouse_id=1" > /dev/null
curl -s -X POST "$API/api/mrp/production/start?token=$T" -d "order_id=2" > /dev/null
curl -s -X POST "$API/api/mrp/production/cancel?token=$T" -d "order_id=2"; echo ""
