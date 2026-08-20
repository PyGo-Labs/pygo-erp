#!/usr/bin/env bash
# UI-3 verification: HR and MRP pages plus the flows they drive
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "=== A) Pages serve real HTML ==="
for v in /rrhh /produccion; do
  read -r code ctype < <(curl -s -o /tmp/p3.html -w "%{http_code} %{content_type}\n" "$API$v")
  printf "  %-13s %s  %-26s %6sB  alpine:%s\n" "$v" "$code" "$ctype" \
    "$(wc -c < /tmp/p3.html)" "$(grep -c 'x-data=' /tmp/p3.html)"
done

echo ""
echo "=== B) HR: org, employees, contracts ==="
curl -s -X POST "$API/api/hr/departments?token=$T" -d "name=Ingenieria&code=ING" > /dev/null
curl -s -X POST "$API/api/hr/positions?token=$T" \
  -d "title=Desarrollador Senior&department_id=1&min_salary=30000&max_salary=60000" > /dev/null
echo "  employee create:"
curl -s -X POST "$API/api/hr/employees?token=$T" -H "Content-Type: application/json" \
  -d '{"first_name":"Ana","last_name":"Torres","email":"ana@demo.com","hire_date":"2026-02-01","department_id":1,"position_id":1}' | head -c 160; echo ""
echo "  contract monthly 45000:"
curl -s -X POST "$API/api/hr/contracts?token=$T" -H "Content-Type: application/json" \
  -d '{"employee_id":1,"wage":45000,"wage_period":"monthly","contract_type":"permanent","date_start":"2026-02-01"}' | head -c 200; echo ""
echo "  contract annual 600000 (must normalise to 50000/month):"
curl -s -X POST "$API/api/hr/employees?token=$T" -H "Content-Type: application/json" \
  -d '{"first_name":"Luis","last_name":"Ramos","hire_date":"2026-03-01","department_id":1}' > /dev/null
curl -s -X POST "$API/api/hr/contracts?token=$T" -H "Content-Type: application/json" \
  -d '{"employee_id":2,"wage":600000,"wage_period":"annual","contract_type":"fixed_term"}' | head -c 200; echo ""
echo "  headcount:"
curl -s "$API/api/hr/headcount?token=$T" | head -c 260; echo ""

echo ""
echo "=== C) HR: leave with real validation ==="
echo "  request 5 business days:"
curl -s -X POST "$API/api/hr/leave?token=$T" -H "Content-Type: application/json" \
  -d '{"employee_id":1,"leave_type_id":1,"date_from":"2026-09-07","date_to":"2026-09-11","reason":"Vacaciones"}' | head -c 180; echo ""
echo "  overlapping request must fail:"
curl -s -X POST "$API/api/hr/leave?token=$T" -H "Content-Type: application/json" \
  -d '{"employee_id":1,"leave_type_id":1,"date_from":"2026-09-09","date_to":"2026-09-12"}' | head -c 180; echo ""
echo "  approve:"
curl -s -X POST "$API/api/hr/leave/approve?token=$T" -d "request_id=1" | head -c 140; echo ""
echo "  balance (20 - 5 = 15 remaining):"
curl -s "$API/api/hr/leave/balance?employee_id=1&token=$T" | head -c 220; echo ""

echo ""
echo "=== D) HR: expense flow draft -> submitted -> approved -> paid ==="
curl -s -X POST "$API/api/hr/expenses?token=$T" -H "Content-Type: application/json" \
  -d '{"employee_id":1,"title":"Viaje cliente","lines":[{"expense_date":"2026-08-05","category":"travel","description":"Vuelo","amount":8500,"cost_center_id":6},{"expense_date":"2026-08-06","category":"meals","description":"Comidas","amount":1500,"cost_center_id":6}]}' | head -c 180; echo ""
for a in submit approve reimburse; do
  printf "  %-10s " "$a"
  curl -s -X POST "$API/api/hr/expenses/$a?token=$T" \
    -H "Content-Type: application/json" -d '{"report_id":1}' | head -c 160; echo ""
done

echo ""
echo "=== E) MRP: work center, routing, multi-level BOM ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=MESA&nombre=Mesa&precio_unitario=3500&cost=0" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=TABLERO&nombre=Tablero&precio_unitario=900&cost=0" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=MADERA&nombre=Madera&precio_unitario=200&cost=0" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=PATA&nombre=Pata&precio_unitario=150&cost=0" > /dev/null
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Planta&code=PLA" > /dev/null
echo "  work center:"
curl -s -X POST "$API/api/mrp/work-centers?token=$T" \
  -d "name=Linea Ensamble&code=ENS&cost_per_hour=450&efficiency_pct=100" | head -c 140; echo ""
echo "  routing (2 operations):"
curl -s -X POST "$API/api/mrp/routings?token=$T" -H "Content-Type: application/json" \
  -d '{"name":"Ensamble Mesa","code":"RT-MESA","operations":[{"sequence":10,"name":"Cortar","work_center_id":1,"setup_minutes":20,"minutes_per_unit":10},{"sequence":20,"name":"Ensamblar","work_center_id":1,"setup_minutes":10,"minutes_per_unit":15}]}' | head -c 160; echo ""
echo "  BOM level 2 (Tablero = 2 Madera):"
curl -s -X POST "$API/api/mrp/boms?token=$T" -H "Content-Type: application/json" \
  -d '{"producto_id":2,"quantity":1,"code":"BOM-TAB","lines":[{"component_id":3,"quantity":2}]}' | head -c 160; echo ""
echo "  BOM level 1 (Mesa = 1 Tablero + 4 Patas con 5% merma):"
curl -s -X POST "$API/api/mrp/boms?token=$T" -H "Content-Type: application/json" \
  -d '{"producto_id":1,"quantity":1,"code":"BOM-MESA","routing_id":1,"lines":[{"component_id":2,"quantity":1},{"component_id":4,"quantity":4,"scrap_pct":5}]}' | head -c 160; echo ""
echo "  explode 10 mesas (expect Madera 20, Pata 42):"
curl -s "$API/api/mrp/boms/explode?producto_id=1&quantity=10&token=$T" | head -c 420; echo ""
echo "  cost 10 mesas (material + labor):"
curl -s "$API/api/mrp/boms/cost?producto_id=1&quantity=10&token=$T" | head -c 300; echo ""

echo ""
echo "=== F) MRP: production order lifecycle ==="
echo "  create order for 10:"
curl -s -X POST "$API/api/mrp/production?token=$T" -H "Content-Type: application/json" \
  -d '{"producto_id":1,"quantity":10,"warehouse_id":1}' | head -c 240; echo ""
echo "  availability without stock (must be false):"
curl -s "$API/api/mrp/production/availability?order_id=1&token=$T" | head -c 260; echo ""
echo "  start without stock (must fail):"
curl -s -X POST "$API/api/mrp/production/start?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' | head -c 160; echo ""
echo "  stock the raw materials:"
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" -d "product_id=3&warehouse_id=1&new_quantity=30&reason=seed" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" -d "product_id=4&warehouse_id=1&new_quantity=60&reason=seed" > /dev/null
curl -s "$API/api/mrp/production/availability?order_id=1&token=$T" | head -c 160; echo ""
echo "  start:"
curl -s -X POST "$API/api/mrp/production/start?token=$T" \
  -H "Content-Type: application/json" -d '{"order_id":1}' | head -c 200; echo ""
echo "  complete 9 of 10 (90% yield):"
curl -s -X POST "$API/api/mrp/production/complete?token=$T" -H "Content-Type: application/json" \
  -d '{"order_id":1,"quantity_produced":9}' | head -c 260; echo ""
echo "  dashboard:"
curl -s "$API/api/mrp/dashboard?token=$T" | head -c 240; echo ""
echo "  stock after production (Mesa should be 9):"
curl -s "$API/api/inventory/stock?token=$T" | head -c 320; echo ""
