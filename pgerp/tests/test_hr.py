"""Tests for HR: contracts, leave validation, expense workflow."""
import pytest


class TestContractNormalisation:
    """Wages come in different periods but payroll cost must be comparable."""

    def test_monthly_wage_is_its_own_equivalent(self, make_employee):
        from core.hr_core import contracts_create
        eid = make_employee()
        r = contracts_create(employee_id=eid, wage=45000, wage_period="monthly")
        assert "error" not in r, r
        assert float(r["monthly_equivalent"]) == 45000.0

    def test_annual_wage_divided_by_twelve(self, make_employee):
        from core.hr_core import contracts_create
        eid = make_employee()
        r = contracts_create(employee_id=eid, wage=600000, wage_period="annual")
        assert float(r["monthly_equivalent"]) == 50000.0

    def test_requires_employee(self):
        from core.hr_core import contracts_create
        assert "error" in contracts_create(wage=1000)

    def test_new_contract_closes_the_previous_one(self, make_employee, db_conn):
        from core.hr_core import contracts_create
        eid = make_employee()
        contracts_create(employee_id=eid, wage=30000, wage_period="monthly")
        contracts_create(employee_id=eid, wage=35000, wage_period="monthly")

        active = db_conn.execute(
            "SELECT COUNT(*) FROM contracts "
            "WHERE employee_id = ? AND status = 'active'", (eid,)).fetchone()[0]
        assert active == 1, "only one contract may be active at a time"

    def test_headcount_sums_normalised_wages(self, make_employee):
        from core.hr_core import contracts_create, hr_headcount
        a, b = make_employee("Ana", "A"), make_employee("Luis", "B")
        contracts_create(employee_id=a, wage=45000, wage_period="monthly")
        contracts_create(employee_id=b, wage=600000, wage_period="annual")

        hc = hr_headcount()
        assert hc["active_employees"] == 2
        assert hc["with_active_contract"] == 2
        assert float(hc["monthly_payroll_cost"]) == 95000.0
        assert float(hc["annual_payroll_cost"]) == 1140000.0

    def test_termination_closes_contract_and_drops_payroll(self, make_employee):
        from core.hr_core import contracts_create, employees_terminate, hr_headcount
        a, b = make_employee("Ana", "A"), make_employee("Luis", "B")
        contracts_create(employee_id=a, wage=6000, wage_period="monthly")
        contracts_create(employee_id=b, wage=4000, wage_period="monthly")
        assert float(hr_headcount()["monthly_payroll_cost"]) == 10000.0

        r = employees_terminate(employee_id=b)
        assert "error" not in r, r
        hc = hr_headcount()
        assert hc["active_employees"] == 1
        assert float(hc["monthly_payroll_cost"]) == 6000.0


class TestLeaveValidation:
    def test_counts_business_days_only(self, seed_hr, make_employee):
        from core.hr_leave_expenses import leave_request
        eid = make_employee()
        # 2026-09-07 is a Monday, 2026-09-11 a Friday: 5 business days
        r = leave_request(employee_id=eid, leave_type_id=1,
                          date_from="2026-09-07", date_to="2026-09-11")
        assert "error" not in r, r
        assert r["days"] == 5

    def test_weekend_span_excludes_saturday_sunday(self, seed_hr, make_employee):
        from core.hr_leave_expenses import leave_request
        eid = make_employee()
        # Friday to Monday spans 4 calendar days but only 2 business days
        r = leave_request(employee_id=eid, leave_type_id=1,
                          date_from="2026-09-11", date_to="2026-09-14")
        assert r["days"] == 2

    def test_overlapping_request_rejected(self, seed_hr, make_employee):
        from core.hr_leave_expenses import leave_request
        eid = make_employee()
        leave_request(employee_id=eid, leave_type_id=1,
                      date_from="2026-09-07", date_to="2026-09-11")
        second = leave_request(employee_id=eid, leave_type_id=1,
                              date_from="2026-09-09", date_to="2026-09-14")
        assert "error" in second
        assert "overlap" in second["error"].lower()

    def test_balance_reflects_approved_days(self, seed_hr, make_employee):
        from core.hr_leave_expenses import leave_request, leave_approve, leave_balance
        eid = make_employee()
        r = leave_request(employee_id=eid, leave_type_id=1,
                          date_from="2026-09-07", date_to="2026-09-11")
        leave_approve(request_id=r["id"])

        balance = leave_balance(employee_id=eid)
        annual = next(b for b in balance["balances"] if b["code"] == "ANNUAL")
        assert float(annual["taken"]) == 5.0
        assert float(annual["remaining"]) == float(annual["allowance"]) - 5.0

    def test_request_beyond_allowance_rejected(self, seed_hr, make_employee):
        from core.hr_leave_expenses import leave_request
        eid = make_employee()
        # Far more business days than the annual allowance
        r = leave_request(employee_id=eid, leave_type_id=1,
                          date_from="2026-01-05", date_to="2026-04-30")
        assert "error" in r

    def test_rejected_request_does_not_consume_balance(self, seed_hr, make_employee):
        from core.hr_leave_expenses import (leave_request, leave_reject, leave_balance)
        eid = make_employee()
        r = leave_request(employee_id=eid, leave_type_id=1,
                          date_from="2026-09-07", date_to="2026-09-11")
        leave_reject(request_id=r["id"])
        balance = leave_balance(employee_id=eid)
        annual = next(b for b in balance["balances"] if b["code"] == "ANNUAL")
        assert float(annual["taken"]) == 0.0
        assert float(annual["pending"]) == 0.0


class TestExpenseWorkflow:
    def test_total_is_sum_of_lines(self, make_employee):
        from core.hr_leave_expenses import expenses_create
        eid = make_employee()
        r = expenses_create(employee_id=eid, title="Viaje", lines=[
            {"category": "travel", "amount": 8500},
            {"category": "meals", "amount": 1500},
        ])
        assert "error" not in r, r
        assert float(r["total"]) == 10000.0
        assert r["status"] == "draft"

    def test_cannot_approve_before_submitting(self, make_employee):
        from core.hr_leave_expenses import expenses_create, expenses_approve
        eid = make_employee()
        rep = expenses_create(employee_id=eid, lines=[{"amount": 100}])
        result = expenses_approve(report_id=rep["id"])
        assert "error" in result, "a draft report must be submitted before approval"

    def test_full_workflow_to_paid(self, seed_commercial, make_employee):
        from core.hr_leave_expenses import (expenses_create, expenses_submit,
                                            expenses_approve, expenses_reimburse)
        eid = make_employee()
        rep = expenses_create(employee_id=eid, lines=[{"amount": 2500}])
        assert expenses_submit(report_id=rep["id"])["status"] == "submitted"
        assert expenses_approve(report_id=rep["id"])["status"] == "approved"
        paid = expenses_reimburse(report_id=rep["id"])
        assert paid["status"] == "paid"
        assert paid.get("payment_id"), "reimbursement must create a payment"

    def test_expense_flows_to_cost_center_on_approval(self, seed_accounting, make_employee):
        """The analytic line is created when the report is APPROVED, not at draft."""
        from core.hr_leave_expenses import (expenses_create, expenses_submit,
                                            expenses_approve)
        from core.accounting_analytic import cost_centers_report
        eid = make_employee()
        rep = expenses_create(employee_id=eid, lines=[
            {"category": "travel", "amount": 1500, "cost_center_id": 1}])

        # Nothing allocated while it is still a draft
        before = next(c for c in cost_centers_report()["cost_centers"] if c["id"] == 1)
        assert float(before["total"]) == 0.0

        expenses_submit(report_id=rep["id"])
        expenses_approve(report_id=rep["id"])

        after = next(c for c in cost_centers_report()["cost_centers"] if c["id"] == 1)
        assert float(after["total"]) == 1500.0
