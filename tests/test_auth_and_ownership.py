import pytest


async def register(client, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-test-password", "full_name": "Test User"},
    )
    assert response.status_code == 201
    return response.json()


async def login(client, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "a-long-test-password"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_register_login_and_current_user(client):
    await register(client, "one@example.com")
    token = await login(client, "one@example.com")
    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "one@example.com"


@pytest.mark.asyncio
async def test_private_company_is_hidden_from_another_user(client):
    await register(client, "owner@example.com")
    await register(client, "visitor@example.com")
    owner_token = await login(client, "owner@example.com")
    visitor_token = await login(client, "visitor@example.com")
    created = await client.post(
        "/api/v1/companies",
        json={"name": "Private Co"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201
    response = await client.get(
        f"/api/v1/companies/{created.json()['id']}",
        headers={"Authorization": f"Bearer {visitor_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_protected_routes_reject_anonymous_requests(client):
    response = await client.get("/api/v1/companies")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_vacancy_application_history_and_analytics(client):
    await register(client, "tracker@example.com")
    token = await login(client, "tracker@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    company = await client.post("/api/v1/companies", json={"name": "Example Labs"}, headers=auth)
    assert company.status_code == 201
    vacancy = await client.post(
        "/api/v1/vacancies",
        json={
            "company_id": company.json()["id"],
            "title": "Python Intern",
            "skills": ["Python", "PostgreSQL"],
            "salary_min": 1000,
            "salary_max": 2000,
            "currency": "USD",
        },
        headers=auth,
    )
    assert vacancy.status_code == 201, vacancy.text
    assert set(vacancy.json()["skills"]) == {"Python", "PostgreSQL"}

    application = await client.post(
        "/api/v1/applications",
        json={"vacancy_id": vacancy.json()["id"], "status": "applied"},
        headers=auth,
    )
    assert application.status_code == 201, application.text
    app_id = application.json()["id"]
    transition = await client.patch(
        f"/api/v1/applications/{app_id}/status",
        json={"status": "interview", "comment": "Recruiter call"},
        headers=auth,
    )
    assert transition.status_code == 200, transition.text

    history = await client.get(f"/api/v1/applications/{app_id}/history", headers=auth)
    assert history.status_code == 200
    assert [entry["new_status"] for entry in history.json()] == ["applied", "interview"]

    overview = await client.get("/api/v1/analytics/overview", headers=auth)
    assert overview.status_code == 200
    assert overview.json()["total_applications"] == 1
    assert overview.json()["response_rate"] == 1

    skills = await client.get("/api/v1/analytics/skills", headers=auth)
    assert {item["skill"] for item in skills.json()} == {"Python", "PostgreSQL"}
