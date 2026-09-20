"""Proof that the trial balance is a real audit tool, not decoration: it must
stay balanced after every kind of transaction this phase can post (deposits,
withdrawals, loan disbursement, loan repayment) — cf. docs/architecture/08
§8.10, mf_app/services/reports.py."""

from decimal import Decimal


async def test_trial_balance_starts_balanced_and_empty(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    resp = await mf_client.get(f"/institutions/{slug}/reports/trial-balance", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balanced"] is True
    assert Decimal(body["total_debit_side"]) == Decimal("0")
    assert Decimal(body["total_credit_side"]) == Decimal("0")


async def test_trial_balance_stays_balanced_through_savings_and_loan_activity(
    mf_client, onboarded_institution
):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]

    branch = await mf_client.post(
        f"/institutions/{slug}/branches", json={"name": "B1", "code": "B1"}, headers=headers
    )
    branch_id = branch.json()["id"]

    savings_product = await mf_client.post(
        f"/institutions/{slug}/savings-products",
        json={
            "name": "Basic",
            "code": "SBASIC",
            "annual_interest_rate": "0",
            "min_opening_balance": "0",
        },
        headers=headers,
    )
    loan_product = await mf_client.post(
        f"/institutions/{slug}/loan-products",
        json={
            "name": "Micro",
            "code": "LMICRO",
            "amortization_method": "flat",
            "periodic_interest_rate": "0.01",
            "min_principal": "50.00",
            "max_principal": "2000.00",
            "min_term_months": 1,
            "max_term_months": 12,
        },
        headers=headers,
    )

    customer = await mf_client.post(
        f"/institutions/{slug}/customers",
        json={"branch_id": branch_id, "full_name": "Report Test Customer"},
        headers=headers,
    )
    customer_id = customer.json()["id"]
    await mf_client.patch(
        f"/institutions/{slug}/customers/{customer_id}/kyc",
        json={"kyc_status": "verified"},
        headers=headers,
    )

    account = await mf_client.post(
        f"/institutions/{slug}/customers/{customer_id}/savings-accounts",
        json={
            "product_id": savings_product.json()["id"],
            "opening_deposit": "200.00",
            "idempotency_key": "open-report",
        },
        headers=headers,
    )
    account_id = account.json()["id"]
    await mf_client.post(
        f"/institutions/{slug}/savings-accounts/{account_id}/withdraw",
        json={"amount": "50.00", "idempotency_key": "wd-report"},
        headers=headers,
    )

    loan_create = await mf_client.post(
        f"/institutions/{slug}/loans",
        json={
            "customer_id": customer_id,
            "product_id": loan_product.json()["id"],
            "principal": "400.00",
            "term_months": 2,
        },
        headers=headers,
    )
    loan_id = loan_create.json()["id"]
    await mf_client.post(f"/institutions/{slug}/loans/{loan_id}/submit", headers=headers)
    await mf_client.post(f"/institutions/{slug}/loans/{loan_id}/approve", headers=headers)
    await mf_client.post(
        f"/institutions/{slug}/loans/{loan_id}/disburse",
        json={"idempotency_key": "disb-report"},
        headers=headers,
    )

    schedule = (
        await mf_client.get(f"/institutions/{slug}/loans/{loan_id}/schedule", headers=headers)
    ).json()
    first = schedule[0]
    repay_amount = Decimal(first["principal_due"]) + Decimal(first["interest_due"])
    await mf_client.post(
        f"/institutions/{slug}/loans/{loan_id}/repay",
        json={"amount": str(repay_amount), "idempotency_key": "repay-report"},
        headers=headers,
    )

    resp = await mf_client.get(f"/institutions/{slug}/reports/trial-balance", headers=headers)
    body = resp.json()
    assert body["balanced"] is True
    assert Decimal(body["total_debit_side"]) == Decimal(body["total_credit_side"])

    portfolio = await mf_client.get(f"/institutions/{slug}/reports/loan-portfolio", headers=headers)
    assert portfolio.status_code == 200, portfolio.text
    portfolio_body = portfolio.json()
    assert portfolio_body["active_loan_count"] == 1
    assert Decimal(portfolio_body["total_principal_disbursed"]) == Decimal("400.00")
    assert Decimal(portfolio_body["total_outstanding_principal"]) < Decimal("400.00")


async def test_teller_cannot_read_reports(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    branch = await mf_client.post(
        f"/institutions/{slug}/branches", json={"name": "B2", "code": "B2"}, headers=headers
    )
    staff_resp = await mf_client.post(
        f"/institutions/{slug}/staff",
        json={
            "full_name": "Teller",
            "email": "teller@test-inst.example",
            "password": "tellerpass123",
            "role": "teller",
            "branch_id": branch.json()["id"],
        },
        headers=headers,
    )
    assert staff_resp.status_code == 201, staff_resp.text
    login = await mf_client.post(
        f"/institutions/{slug}/auth/login",
        json={"email": "teller@test-inst.example", "password": "tellerpass123"},
    )
    teller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await mf_client.get(
        f"/institutions/{slug}/reports/trial-balance", headers=teller_headers
    )
    assert resp.status_code == 403
