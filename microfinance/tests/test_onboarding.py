"""End-to-end proof of docs/architecture/08 §8.3-8.5: onboarding an institution
really provisions a project+database through the real backend (real routing,
real job/worker, real Alembic tenant migration subprocess), not a hand-rolled
mock of what that would look like.
"""


async def test_onboard_institution_end_to_end(
    mf_client,
    run_onboarding_job,
    platform_account,
    active_region,
    operator_headers,
):
    resp = await mf_client.post(
        "/institutions",
        json={
            "name": "Coopérative Test",
            "slug": "coop-test",
            "region_code": active_region,
            "currency": "XOF",
            "admin_email": "admin@coop-test.example",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["institution"]["status"] == "provisioning"
    admin_password = body["admin_password"]

    assert await run_onboarding_job() is True

    list_resp = await mf_client.get("/institutions", headers=operator_headers)
    institution = next(i for i in list_resp.json() if i["slug"] == "coop-test")
    assert institution["status"] == "active"

    login_resp = await mf_client.post(
        "/institutions/coop-test/auth/login",
        json={"email": "admin@coop-test.example", "password": admin_password},
    )
    assert login_resp.status_code == 200, login_resp.text
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    me_resp = await mf_client.get("/institutions/coop-test/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "institution_admin"

    branch_resp = await mf_client.post(
        "/institutions/coop-test/branches",
        json={"name": "Agence Centrale", "code": "AC01"},
        headers=headers,
    )
    assert branch_resp.status_code == 201, branch_resp.text
    branch_id = branch_resp.json()["id"]

    staff_resp = await mf_client.post(
        "/institutions/coop-test/staff",
        json={
            "full_name": "Jean Teller",
            "email": "jean@coop-test.example",
            "password": "tellerpass123",
            "role": "teller",
            "branch_id": branch_id,
        },
        headers=headers,
    )
    assert staff_resp.status_code == 201, staff_resp.text

    branches = await mf_client.get("/institutions/coop-test/branches", headers=headers)
    assert len(branches.json()) == 1

    staff_login = await mf_client.post(
        "/institutions/coop-test/auth/login",
        json={"email": "jean@coop-test.example", "password": "tellerpass123"},
    )
    assert staff_login.status_code == 200, staff_login.text


async def test_wrong_slug_login_returns_404(mf_client):
    resp = await mf_client.post(
        "/institutions/does-not-exist/auth/login",
        json={"email": "a@b.example", "password": "whatever"},
    )
    assert resp.status_code == 404


async def test_non_operator_cannot_onboard(mf_client):
    resp = await mf_client.post(
        "/institutions",
        json={
            "name": "X",
            "slug": "x",
            "region_code": "eu-mf",
            "currency": "XOF",
            "admin_email": "a@b.example",
        },
        headers={"Authorization": "Bearer not-the-operator-token"},
    )
    assert resp.status_code == 401
