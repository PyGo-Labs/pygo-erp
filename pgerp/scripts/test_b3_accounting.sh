#!/usr/bin/env bash
# B3 accounting smoke test: cost centers, budgets, assets, payments, aging, banking
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "1) Cost centers (seeded)"
curl -s "$API/api/cost-centers?token=$T" | head -c 220; echo ""

echo "2) Allocate 12000 to cost center 1"
curl -s -X POST "$API/api/cost-centers/allocate?token=$T" \
  -d "cost_center_id=1&amount=12000&entry_date=2026-08-05&description=Office rent"; echo ""

echo "3) Cost center report"
curl -s "$API/api/cost-centers/report?token=$T" | head -c 300; echo ""

echo "4) Create budget with 2 lines"
curl -s -X POST "$API/api/budgets?token=$T" -H "Content-Type: application/json" \
  -d '{"name":"FY2026 Opex","fiscal_year":"2026","date_from":"2026-01-01","date_to":"2026-12-31","lines":[{"cost_center_id":1,"planned_amount":50000},{"cost_center_id":2,"planned_amount":30000}]}'; echo ""

echo "5) Budget vs actual"
curl -s "$API/api/budgets/vs-actual?budget_id=1&token=$T"; echo ""

echo "6) Create fixed asset (60000, 60 months, straight line)"
curl -s -X POST "$API/api/assets?token=$T" \
  -d "name=Delivery Van&code=VAN-01&category=Vehicles&acquisition_cost=60000&salvage_value=6000&useful_life_months=60&acquisition_date=2026-01-01&cost_center_id=3"; echo ""

echo "7) Depreciation schedule (first 3 periods)"
curl -s "$API/api/assets/schedule?asset_id=1&token=$T" | head -c 420; echo ""

echo "8) Post depreciation for 2026-01 and 2026-02"
curl -s -X POST "$API/api/assets/depreciate?token=$T" -d "asset_id=1&period=2026-01"; echo ""
curl -s -X POST "$API/api/assets/depreciate?token=$T" -d "asset_id=1&period=2026-02"; echo ""

echo "9) Duplicate period must fail"
curl -s -X POST "$API/api/assets/depreciate?token=$T" -d "asset_id=1&period=2026-02"; echo ""

echo "10) Assets summary"
curl -s "$API/api/assets/summary?token=$T"; echo ""

echo "11) Create invoice 11600 due 2026-06-01 then pay 5000"
curl -s -X POST "$API/api/facturas?token=$T" -d "cliente_id=1&total=11600" > /dev/null
curl -s -X POST "$API/api/payments?token=$T" -H "Content-Type: application/json" \
  -d '{"amount":5000,"partner_type":"customer","partner_id":1,"payment_type":"inbound","payment_date":"2026-08-10","allocations":[{"document_type":"invoice","document_id":1,"amount":5000}]}'; echo ""

echo "12) AR aging"
curl -s "$API/api/ar/aging?as_of=2026-08-20&token=$T" | head -c 400; echo ""

echo "13) AP aging"
curl -s "$API/api/ap/aging?as_of=2026-08-20&token=$T" | head -c 300; echo ""

echo "14) Bank account + import 3 lines"
curl -s -X POST "$API/api/bank/accounts?token=$T" -d "name=Main Checking&bank_name=Global Bank&currency=USD&opening_balance=10000" > /dev/null
curl -s -X POST "$API/api/bank/statements/import?token=$T" -H "Content-Type: application/json" \
  -d '{"bank_account_id":1,"reference":"AUG-2026","lines":[{"line_date":"2026-08-10","description":"Customer payment","amount":5000},{"line_date":"2026-08-12","description":"Unknown deposit","amount":777},{"line_date":"2026-08-15","description":"Bank fee","amount":-25}]}'; echo ""

echo "15) Auto reconcile (should match the 5000 payment)"
curl -s -X POST "$API/api/bank/reconcile/auto?token=$T" -d "bank_account_id=1"; echo ""

echo "16) Reconciliation status"
curl -s "$API/api/bank/reconcile/status?bank_account_id=1&token=$T" | head -c 400; echo ""
