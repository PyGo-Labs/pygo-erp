#!/usr/bin/env bash
# UI-2 verification: accounting + treasury pages and the flows they drive
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "=== A) Pages serve real HTML ==="
for v in /contabilidad /tesoreria; do
  read -r code ctype < <(curl -s -o /tmp/p2.html -w "%{http_code} %{content_type}\n" "$API$v")
  size=$(wc -c < /tmp/p2.html)
  printf "  %-15s %s  %-26s %6sB  alpine:%s\n" "$v" "$code" "$ctype" "$size" \
    "$(grep -c 'x-data=' /tmp/p2.html)"
done

echo ""
echo "=== B) Chart of accounts + journal (new routes) ==="
echo "  accounts list:"
curl -s "$API/api/accounts?token=$T" | head -c 200; echo ""
echo "  create account:"
curl -s -X POST "$API/api/accounts?token=$T" \
  -d "code=6100&name=Gastos de oficina&type=expense" | head -c 160; echo ""
echo "  balanced journal entry:"
curl -s -X POST "$API/api/journal?token=$T" -H "Content-Type: application/json" \
  -d '{"description":"Compra de papeleria","date":"2026-08-15","lines":[{"account_id":1,"debit":0,"credit":500},{"account_id":2,"debit":500,"credit":0}]}' | head -c 200; echo ""
echo "  UNBALANCED entry must be rejected:"
curl -s -X POST "$API/api/journal?token=$T" -H "Content-Type: application/json" \
  -d '{"description":"Mal asiento","lines":[{"account_id":1,"debit":100,"credit":0},{"account_id":2,"debit":0,"credit":50}]}' | head -c 160; echo ""
echo "  journal list:"
curl -s "$API/api/journal?token=$T" | head -c 180; echo ""

echo ""
echo "=== C) Financial statements ==="
for r in trial-balance income-statement balance-sheet; do
  printf "  %-18s " "$r"
  curl -s "$API/api/accounting/$r?token=$T" | head -c 180; echo ""
done

echo ""
echo "=== D) Cost centers + budgets ==="
echo "  allocate 8000:"
curl -s -X POST "$API/api/cost-centers/allocate?token=$T" \
  -d "cost_center_id=1&amount=8000&entry_date=2026-08-10&description=Renta" | head -c 160; echo ""
echo "  create budget:"
curl -s -X POST "$API/api/budgets?token=$T" -H "Content-Type: application/json" \
  -d '{"name":"Opex 2026","fiscal_year":"2026","date_from":"2026-01-01","date_to":"2026-12-31","lines":[{"cost_center_id":1,"planned_amount":40000},{"cost_center_id":2,"planned_amount":20000}]}' | head -c 160; echo ""
echo "  budget vs actual:"
curl -s "$API/api/budgets/vs-actual?budget_id=1&token=$T" | head -c 320; echo ""

echo ""
echo "=== E) Payments + aging ==="
curl -s -X POST "$API/api/clientes?token=$T" -d "nombre=Tesoreria Client&email=t@x.com" > /dev/null
curl -s -X POST "$API/api/facturas?token=$T" -d "cliente_id=1&total=23200" > /dev/null
echo "  register payment applied to invoice:"
curl -s -X POST "$API/api/payments?token=$T" -H "Content-Type: application/json" \
  -d '{"amount":9000,"payment_type":"inbound","partner_type":"customer","partner_id":1,"payment_date":"2026-08-14","allocations":[{"document_type":"invoice","document_id":1,"amount":9000}]}' | head -c 220; echo ""
echo "  AR aging:"
curl -s "$API/api/ar/aging?as_of=2026-08-20&token=$T" | head -c 300; echo ""
echo "  AP aging:"
curl -s "$API/api/ap/aging?token=$T" | head -c 180; echo ""

echo ""
echo "=== F) Banks + reconciliation ==="
echo "  create bank account:"
curl -s -X POST "$API/api/bank/accounts?token=$T" \
  -d "name=Cuenta Principal&bank_name=Banco Global&currency=MXN&opening_balance=25000" | head -c 160; echo ""
echo "  import 3 statement lines (as the textarea parser sends them):"
curl -s -X POST "$API/api/bank/statements/import?token=$T" -H "Content-Type: application/json" \
  -d '{"bank_account_id":1,"reference":"AGO-2026","lines":[{"line_date":"2026-08-14","description":"Pago cliente","amount":9000},{"line_date":"2026-08-16","description":"Deposito sin identificar","amount":1200},{"line_date":"2026-08-18","description":"Comision bancaria","amount":-180}]}' | head -c 180; echo ""
echo "  auto reconcile (should match the 9000 payment):"
curl -s -X POST "$API/api/bank/reconcile/auto?token=$T" -d "bank_account_id=1" | head -c 300; echo ""
echo "  reconciliation status:"
curl -s "$API/api/bank/reconcile/status?bank_account_id=1&token=$T" | head -c 320; echo ""

echo ""
echo "=== G) Fixed assets ==="
echo "  create asset (120000 / 48 months):"
curl -s -X POST "$API/api/assets?token=$T" \
  -d "name=Camioneta reparto&code=VEH-01&category=Vehiculos&acquisition_cost=120000&salvage_value=12000&useful_life_months=48&acquisition_date=2026-01-01&cost_center_id=3" | head -c 200; echo ""
echo "  schedule (first periods):"
curl -s "$API/api/assets/schedule?asset_id=1&token=$T" | head -c 280; echo ""
echo "  depreciate 2026-01 then repeat (must fail):"
curl -s -X POST "$API/api/assets/depreciate?token=$T" -d "asset_id=1&period=2026-01" | head -c 200; echo ""
curl -s -X POST "$API/api/assets/depreciate?token=$T" -d "asset_id=1&period=2026-01" | head -c 140; echo ""
echo "  summary:"
curl -s "$API/api/assets/summary?token=$T" | head -c 260; echo ""
