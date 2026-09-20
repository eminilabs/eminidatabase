"""HTTP-level proof of the savings flow: KYC gate, opening balance minimum,
deposit/withdraw through the real API (which goes through the ledger engine
under the hood, never touching balance_cached directly)."""


async def _create_branch_and_product(mf_client, slug, headers):
    branch = await mf_client.post(
        f"/institutions/{slug}/branches",
        json={"name": "Main Branch", "code": "MB01"},
        headers=headers,
    )
    assert branch.status_code == 201, branch.text
    product = await mf_client.post(
        f"/institutions/{slug}/savings-products",
        json={
            "name": "Basic Savings",
            "code": "BASIC",
            "annual_interest_rate": "0.02",
            "min_opening_balance": "10.00",
        },
        headers=headers,
    )
    assert product.status_code == 201, product.text
    return branch.json()["id"], product.json()["id"]


async def test_cannot_open_account_for_unverified_customer(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    branch_id, product_id = await _create_branch_and_product(mf_client, slug, headers)

    customer = await mf_client.post(
        f"/institutions/{slug}/customers",
        json={"branch_id": branch_id, "full_name": "Awa Diallo", "phone": "+22500000000"},
        headers=headers,
    )
    assert customer.status_code == 201, customer.text
    assert customer.json()["kyc_status"] == "pending"
    customer_id = customer.json()["id"]

    resp = await mf_client.post(
        f"/institutions/{slug}/customers/{customer_id}/savings-accounts",
        json={"product_id": product_id, "opening_deposit": "0"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


async def test_opening_deposit_below_minimum_is_rejected(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    branch_id, product_id = await _create_branch_and_product(mf_client, slug, headers)

    customer = await mf_client.post(
        f"/institutions/{slug}/customers",
        json={"branch_id": branch_id, "full_name": "Moussa Kone"},
        headers=headers,
    )
    customer_id = customer.json()["id"]
    await mf_client.patch(
        f"/institutions/{slug}/customers/{customer_id}/kyc",
        json={"kyc_status": "verified"},
        headers=headers,
    )

    resp = await mf_client.post(
        f"/institutions/{slug}/customers/{customer_id}/savings-accounts",
        json={"product_id": product_id, "opening_deposit": "5.00", "idempotency_key": "open-1"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


async def test_deposit_and_withdraw_full_flow(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    branch_id, product_id = await _create_branch_and_product(mf_client, slug, headers)

    customer = await mf_client.post(
        f"/institutions/{slug}/customers",
        json={"branch_id": branch_id, "full_name": "Fatou Sow"},
        headers=headers,
    )
    customer_id = customer.json()["id"]
    await mf_client.patch(
        f"/institutions/{slug}/customers/{customer_id}/kyc",
        json={"kyc_status": "verified"},
        headers=headers,
    )

    account_resp = await mf_client.post(
        f"/institutions/{slug}/customers/{customer_id}/savings-accounts",
        json={"product_id": product_id, "opening_deposit": "50.00", "idempotency_key": "open-2"},
        headers=headers,
    )
    assert account_resp.status_code == 201, account_resp.text
    account = account_resp.json()
    assert account["balance_cached"] == "50.00"
    account_id = account["id"]

    deposit_resp = await mf_client.post(
        f"/institutions/{slug}/savings-accounts/{account_id}/deposit",
        json={"amount": "25.50", "idempotency_key": "dep-a"},
        headers=headers,
    )
    assert deposit_resp.status_code == 200, deposit_resp.text

    get_resp = await mf_client.get(
        f"/institutions/{slug}/savings-accounts/{account_id}", headers=headers
    )
    assert get_resp.json()["balance_cached"] == "75.50"

    # Replaying the same idempotency key must not double-credit the account.
    replay_resp = await mf_client.post(
        f"/institutions/{slug}/savings-accounts/{account_id}/deposit",
        json={"amount": "25.50", "idempotency_key": "dep-a"},
        headers=headers,
    )
    assert replay_resp.status_code == 200
    get_after_replay = await mf_client.get(
        f"/institutions/{slug}/savings-accounts/{account_id}", headers=headers
    )
    assert get_after_replay.json()["balance_cached"] == "75.50"

    withdraw_resp = await mf_client.post(
        f"/institutions/{slug}/savings-accounts/{account_id}/withdraw",
        json={"amount": "1000.00", "idempotency_key": "wd-too-much"},
        headers=headers,
    )
    assert withdraw_resp.status_code == 409, withdraw_resp.text

    ok_withdraw = await mf_client.post(
        f"/institutions/{slug}/savings-accounts/{account_id}/withdraw",
        json={"amount": "20.00", "idempotency_key": "wd-a"},
        headers=headers,
    )
    assert ok_withdraw.status_code == 200, ok_withdraw.text

    final = await mf_client.get(
        f"/institutions/{slug}/savings-accounts/{account_id}", headers=headers
    )
    assert final.json()["balance_cached"] == "55.50"

    transactions = await mf_client.get(
        f"/institutions/{slug}/savings-accounts/{account_id}/transactions", headers=headers
    )
    assert transactions.status_code == 200
    # opening deposit, deposit, (replay is a no-op, not a new transaction), withdrawal
    assert len(transactions.json()) == 3


async def test_loan_officer_cannot_transact(mf_client, onboarded_institution):
    slug, headers = onboarded_institution["slug"], onboarded_institution["admin_headers"]
    branch_id, product_id = await _create_branch_and_product(mf_client, slug, headers)

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

    customer = await mf_client.post(
        f"/institutions/{slug}/customers",
        json={"branch_id": branch_id, "full_name": "Ibrahim Toure"},
        headers=officer_headers,  # loan officers CAN manage customers
    )
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()["id"]
    await mf_client.patch(
        f"/institutions/{slug}/customers/{customer_id}/kyc",
        json={"kyc_status": "verified"},
        headers=headers,
    )

    forbidden = await mf_client.post(
        f"/institutions/{slug}/customers/{customer_id}/savings-accounts",
        json={"product_id": product_id, "opening_deposit": "0"},
        headers=officer_headers,
    )
    assert forbidden.status_code == 403
