#!/usr/bin/env bash
# B4 HR smoke test: departments, employees, contracts, leave, expenses
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "1) Department + position"
curl -s -X POST "$API/api/hr/departments?token=$T" -d "name=Engineering&code=ENG&cost_center_id=6"; echo ""
curl -s -X POST "$API/api/hr/positions?token=$T" -d "title=Senior Developer&department_id=1&min_salary=4000&max_salary=8000"; echo ""

echo "2) Employees"
curl -s -X POST "$API/api/hr/employees?token=$T" \
  -d "first_name=Ana&last_name=Torres&email=ana@demo.com&hire_date=2026-01-15&department_id=1&position_id=1&cost_center_id=6"; echo ""
curl -s -X POST "$API/api/hr/employees?token=$T" \
  -d "first_name=Luis&last_name=Ramos&email=luis@demo.com&hire_date=2026-03-01&department_id=1&manager_id=1"; echo ""

echo "3) Contracts (monthly 6000 and annual 84000)"
curl -s -X POST "$API/api/hr/contracts?token=$T" \
  -d "employee_id=1&wage=6000&wage_period=monthly&contract_type=permanent&date_start=2026-01-15"; echo ""
curl -s -X POST "$API/api/hr/contracts?token=$T" \
  -d "employee_id=2&wage=84000&wage_period=annual&contract_type=fixed_term&date_start=2026-03-01&date_end=2027-03-01"; echo ""

echo "4) Headcount + payroll cost"
curl -s "$API/api/hr/headcount?token=$T"; echo ""

echo "5) Leave types (seeded)"
curl -s "$API/api/hr/leave-types?token=$T" | head -c 250; echo ""

echo "6) Request annual leave 2026-09-07..2026-09-11 (5 business days)"
curl -s -X POST "$API/api/hr/leave?token=$T" \
  -d "employee_id=1&leave_type_id=1&date_from=2026-09-07&date_to=2026-09-11&reason=Vacation"; echo ""

echo "7) Overlapping request must fail"
curl -s -X POST "$API/api/hr/leave?token=$T" \
  -d "employee_id=1&leave_type_id=1&date_from=2026-09-09&date_to=2026-09-12"; echo ""

echo "8) Approve leave 1"
curl -s -X POST "$API/api/hr/leave/approve?token=$T" -d "request_id=1&approved_by=1"; echo ""

echo "9) Leave balance (annual should show 5 taken, 15 remaining)"
curl -s "$API/api/hr/leave/balance?employee_id=1&year=2026&token=$T" | head -c 400; echo ""

echo "10) Over-allowance request must fail (25 days)"
curl -s -X POST "$API/api/hr/leave?token=$T" \
  -d "employee_id=1&leave_type_id=1&date_from=2026-10-01&date_to=2026-11-10"; echo ""

echo "11) Expense report (travel 1200 + meals 300)"
curl -s -X POST "$API/api/hr/expenses?token=$T" -H "Content-Type: application/json" \
  -d '{"employee_id":1,"title":"Client visit Madrid","lines":[{"expense_date":"2026-08-05","category":"travel","description":"Flight","amount":1200,"cost_center_id":6},{"expense_date":"2026-08-06","category":"meals","description":"Meals","amount":300,"cost_center_id":6}]}'; echo ""

echo "12) Approve before submit must fail"
curl -s -X POST "$API/api/hr/expenses/approve?token=$T" -d "report_id=1&approved_by=1"; echo ""

echo "13) Submit -> approve -> reimburse"
curl -s -X POST "$API/api/hr/expenses/submit?token=$T" -d "report_id=1"; echo ""
curl -s -X POST "$API/api/hr/expenses/approve?token=$T" -d "report_id=1&approved_by=1"; echo ""
curl -s -X POST "$API/api/hr/expenses/reimburse?token=$T" -d "report_id=1&payment_date=2026-08-20"; echo ""

echo "14) Cost center report (should include the 1500 expense)"
curl -s "$API/api/cost-centers/report?token=$T" | head -c 300; echo ""

echo "15) Terminate employee 2"
curl -s -X POST "$API/api/hr/employees/terminate?token=$T" -d "employee_id=2&termination_date=2026-08-31"; echo ""

echo "16) Headcount after termination"
curl -s "$API/api/hr/headcount?token=$T"; echo ""
