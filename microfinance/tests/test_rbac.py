"""Staff RBAC and institution isolation (cf. docs/architecture/08 §8.9)."""


async def _onboard(mf_client, run_onboarding_job, operator_headers, *, slug, region):
    resp = await mf_client.post(
        "/institutions",
        json={
            "name": slug,
            "slug": slug,
            "region_code": region,
            "currency": "XOF",
            "admin_email": f"admin@{slug}.example",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    await run_onboarding_job()

    login = await mf_client.post(
        f"/institutions/{slug}/auth/login",
        json={"email": f"admin@{slug}.example", "password": body["admin_password"]},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_staff_token_rejected_on_other_institution(
    mf_client, run_onboarding_job, platform_account, active_region, operator_headers
):
    headers_a = await _onboard(
        mf_client, run_onboarding_job, operator_headers, slug="inst-a", region=active_region
    )

    resp = await mf_client.post(
        "/institutions/inst-a/branches",
        json={"name": "Branch A", "code": "B01"},
        headers=headers_a,
    )
    assert resp.status_code == 201, resp.text

    headers_b = await _onboard(
        mf_client, run_onboarding_job, operator_headers, slug="inst-b", region=active_region
    )

    # inst-a's admin token must not work against inst-b's routes, even though
    # the role would otherwise be permitted (cf. §8.9 defense in depth).
    cross_resp = await mf_client.get("/institutions/inst-b/branches", headers=headers_a)
    assert cross_resp.status_code == 403

    same_resp = await mf_client.get("/institutions/inst-b/branches", headers=headers_b)
    assert same_resp.status_code == 200


async def test_teller_cannot_manage_branches(
    mf_client, run_onboarding_job, platform_account, active_region, operator_headers
):
    admin_headers = await _onboard(
        mf_client, run_onboarding_job, operator_headers, slug="inst-c", region=active_region
    )
    branch_resp = await mf_client.post(
        "/institutions/inst-c/branches",
        json={"name": "Main", "code": "M01"},
        headers=admin_headers,
    )
    branch_id = branch_resp.json()["id"]

    staff_resp = await mf_client.post(
        "/institutions/inst-c/staff",
        json={
            "full_name": "Teller One",
            "email": "teller@inst-c.example",
            "password": "tellerpass123",
            "role": "teller",
            "branch_id": branch_id,
        },
        headers=admin_headers,
    )
    assert staff_resp.status_code == 201, staff_resp.text

    teller_login = await mf_client.post(
        "/institutions/inst-c/auth/login",
        json={"email": "teller@inst-c.example", "password": "tellerpass123"},
    )
    teller_headers = {"Authorization": f"Bearer {teller_login.json()['access_token']}"}

    forbidden = await mf_client.post(
        "/institutions/inst-c/branches",
        json={"name": "Second", "code": "M02"},
        headers=teller_headers,
    )
    assert forbidden.status_code == 403

    allowed = await mf_client.get("/institutions/inst-c/branches", headers=teller_headers)
    assert allowed.status_code == 200


async def test_institution_admin_cannot_have_branch(
    mf_client, run_onboarding_job, platform_account, active_region, operator_headers
):
    admin_headers = await _onboard(
        mf_client, run_onboarding_job, operator_headers, slug="inst-d", region=active_region
    )
    branch_resp = await mf_client.post(
        "/institutions/inst-d/branches",
        json={"name": "Main", "code": "M01"},
        headers=admin_headers,
    )
    branch_id = branch_resp.json()["id"]

    resp = await mf_client.post(
        "/institutions/inst-d/staff",
        json={
            "full_name": "Second Admin",
            "email": "admin2@inst-d.example",
            "password": "adminpass123",
            "role": "institution_admin",
            "branch_id": branch_id,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400
