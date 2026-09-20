"""HTTP-level proof of the Phase 9 exit criterion: cycle complet demande de
crédit → décaissement → échéancier → remboursement → clôture, avec ledger
cohérent et auditable (docs/architecture/09-plan-de-phases.md, Phase 9)."""

from decimal import Decimal


async def _setup_branch_product_customer(mf_client, slug, headers):
    branch = await mf_client.post(
        f"/institutions/{slug}/branches",
        json={"name": "Main Branch", "code": "MB01"},
        headers=headers,
    )
    assert branch.status_code == 201, branch.text

    product = await mf_client.post(
        f"/institutions/{slug}/loan-products",
        json={
            "name": "Micro Credit",
            "code": "MICRO",
            "amortization_method": "declining_balance",
            "periodic_interest_rate": "0.02",
            "min_principal": "100.00",
            "max_principal": "5000.00",
            "min_term_months": 1,
            "max_term_months": 24,
        },
        headers=headers,
    )
    assert product.status_code == 201, product.text

    customer = await mf_client.post(
        f"/institutions/{slug}/customers",
        json={"branch_id": branch.json()["id"], "full_name": "Aminata Traore"},
        headers=headers,
    )
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()["id"]
    await mf_client.patch(
        f"/institutions/{slug}/customers/{customer_id}/kyc",
        json={"kyc_status": "verified"},
        headers=headers,
    )
    return product.json()["id"], customer_id


async def test_full_loan_lifecycle_request_to_closure(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    product_id, customer_id = await _setup_branch_product_customer(mf_client, slug, headers)

    create = await mf_client.post(
        f"/institutions/{slug}/loans",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "principal": "600.00",
            "term_months": 3,
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    loan = create.json()
    assert loan["status"] == "draft"
    loan_id = loan["id"]

    submit = await mf_client.post(f"/institutions/{slug}/loans/{loan_id}/submit", headers=headers)
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == "pending_approval"

    approve = await mf_client.post(
        f"/institutions/{slug}/loans/{loan_id}/approve", headers=headers
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"

    disburse = await mf_client.post(
        f"/institutions/{slug}/loans/{loan_id}/disburse",
        json={"idempotency_key": "disb-1"},
        headers=headers,
    )
    assert disburse.status_code == 200, disburse.text
    disbursed = disburse.json()
    assert disbursed["status"] == "active"
    assert Decimal(disbursed["outstanding_principal"]) == Decimal("600.00")

    schedule_resp = await mf_client.get(
        f"/institutions/{slug}/loans/{loan_id}/schedule", headers=headers
    )
    assert schedule_resp.status_code == 200
    schedule = schedule_resp.json()
    assert len(schedule) == 3
    assert sum(Decimal(line["principal_due"]) for line in schedule) == Decimal("600.00")

    # Pay every installment in full, in order — the loan must close itself
    # automatically once the last one is settled.
    for i, line in enumerate(schedule, start=1):
        amount = Decimal(line["principal_due"]) + Decimal(line["interest_due"])
        repay = await mf_client.post(
            f"/institutions/{slug}/loans/{loan_id}/repay",
            json={"amount": str(amount), "idempotency_key": f"repay-{i}"},
            headers=headers,
        )
        assert repay.status_code == 200, repay.text

    final = await mf_client.get(f"/institutions/{slug}/loans/{loan_id}", headers=headers)
    assert final.json()["status"] == "closed"
    assert Decimal(final.json()["outstanding_principal"]) == Decimal("0.00")
    assert final.json()["closed_at"] is not None


async def test_overpayment_on_installment_is_rejected(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    product_id, customer_id = await _setup_branch_product_customer(mf_client, slug, headers)

    create = await mf_client.post(
        f"/institutions/{slug}/loans",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "principal": "300.00",
            "term_months": 2,
        },
        headers=headers,
    )
    loan_id = create.json()["id"]
    await mf_client.post(f"/institutions/{slug}/loans/{loan_id}/submit", headers=headers)
    await mf_client.post(f"/institutions/{slug}/loans/{loan_id}/approve", headers=headers)
    await mf_client.post(
        f"/institutions/{slug}/loans/{loan_id}/disburse",
        json={"idempotency_key": "disb-2"},
        headers=headers,
    )

    resp = await mf_client.post(
        f"/institutions/{slug}/loans/{loan_id}/repay",
        json={"amount": "999999.00", "idempotency_key": "too-much"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


async def test_principal_outside_product_bounds_is_rejected(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    product_id, customer_id = await _setup_branch_product_customer(mf_client, slug, headers)

    resp = await mf_client.post(
        f"/institutions/{slug}/loans",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "principal": "1000000.00",
            "term_months": 3,
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


async def test_loan_officer_cannot_approve_own_loan(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    branch = await mf_client.post(
        f"/institutions/{slug}/branches",
        json={"name": "Branch B", "code": "BB01"},
        headers=headers,
    )
    branch_id = branch.json()["id"]

    staff_resp = await mf_client.post(
        f"/institutions/{slug}/staff",
        json={
            "full_name": "Loan Officer",
            "email": "officer@test-inst.example",
            "password": "officerpass123",
            "role": "loan_officer",
            "branch_id": branch_id,
        },
        headers=headers,
    )
    assert staff_resp.status_code == 201, staff_resp.text
    officer_login = await mf_client.post(
        f"/institutions/{slug}/auth/login",
        json={"email": "officer@test-inst.example", "password": "officerpass123"},
    )
    officer_headers = {"Authorization": f"Bearer {officer_login.json()['access_token']}"}

    product = await mf_client.post(
        f"/institutions/{slug}/loan-products",
        json={
            "name": "Micro Credit",
            "code": "MICRO2",
            "amortization_method": "flat",
            "periodic_interest_rate": "0.01",
            "min_principal": "100.00",
            "max_principal": "1000.00",
            "min_term_months": 1,
            "max_term_months": 12,
        },
        headers=headers,
    )
    product_id = product.json()["id"]

    customer = await mf_client.post(
        f"/institutions/{slug}/customers",
        json={"branch_id": branch_id, "full_name": "Client Test"},
        headers=officer_headers,
    )
    customer_id = customer.json()["id"]
    await mf_client.patch(
        f"/institutions/{slug}/customers/{customer_id}/kyc",
        json={"kyc_status": "verified"},
        headers=headers,
    )

    create = await mf_client.post(
        f"/institutions/{slug}/loans",
        json={
            "customer_id": customer_id,
            "product_id": product_id,
            "principal": "200.00",
            "term_months": 4,
        },
        headers=officer_headers,
    )
    assert create.status_code == 201, create.text
    loan_id = create.json()["id"]
    await mf_client.post(f"/institutions/{slug}/loans/{loan_id}/submit", headers=officer_headers)

    forbidden = await mf_client.post(
        f"/institutions/{slug}/loans/{loan_id}/approve", headers=officer_headers
    )
    assert forbidden.status_code == 403
