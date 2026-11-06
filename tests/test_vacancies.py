import pytest

from tests.helpers import account, company, vacancy


async def test_company_crud_search_sort_and_cascade(client):
    auth, _, _ = await account(client)
    c = await company(
        client,
        auth,
        name="Alpha",
        website_url="https://example.com",
        location="Moscow",
        industry="IT",
    )
    v = await vacancy(client, auth, company_id=c["id"])
    r = await client.get(
        "/api/v1/companies",
        headers=auth,
        params={
            "search": "alpha",
            "location": "Moscow",
            "industry": "IT",
            "sort": "name",
            "direction": "asc",
        },
    )
    assert r.json()["total"] == 1
    assert (await client.get("/api/v1/companies/" + c["id"], headers=auth)).status_code == 200
    r = await client.patch(
        "/api/v1/companies/" + c["id"],
        headers=auth,
        json={"description": "Note", "website_url": None},
    )
    assert r.status_code == 200
    assert r.json()["website_url"] is None
    for payload in [{"name": None}, {"website_url": "broken"}, {"unknown": True}]:
        assert (
            await client.patch("/api/v1/companies/" + c["id"], headers=auth, json=payload)
        ).status_code == 422
    assert (await client.delete("/api/v1/companies/" + c["id"], headers=auth)).status_code == 204
    assert (await client.get("/api/v1/vacancies/" + v["id"], headers=auth)).status_code == 404


async def test_vacancy_crud_skills_filters_and_pagination(client):
    auth, _, _ = await account(client)
    v = await vacancy(
        client,
        auth,
        salary_min=100,
        salary_max=200,
        currency="USD",
        skills=["Python", "python", "SQL"],
        work_format="remote",
        application_deadline="2030-01-01T00:00:00Z",
    )
    await vacancy(client, auth, title="Java", work_format="office", currency="EUR", salary_min=1000)
    r = await client.get(
        "/api/v1/vacancies",
        headers=auth,
        params={
            "skill": "PYTHON",
            "work_format": "remote",
            "salary_min": 150,
            "salary_max": 300,
            "currency": "USD",
            "company_id": v["company_id"],
            "company": v["company"]["name"],
            "search": "python",
            "application_deadline_before": "2031-01-01T00:00:00Z",
            "application_deadline_after": "2029-01-01T00:00:00Z",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    assert len(r.json()["items"][0]["skills"]) == 2
    assert (await client.get("/api/v1/skills", headers=auth)).json()
    assert len((await client.get("/api/v1/skills?search=python", headers=auth)).json()) == 1
    assert (
        await client.get(
            "/api/v1/vacancies?page=2&page_size=1&sort=title&direction=asc", headers=auth
        )
    ).json()["total"] == 2
    r = await client.patch(
        "/api/v1/vacancies/" + v["id"],
        headers=auth,
        json={"title": "Updated", "skills": ["Docker"], "description": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["skills"] == ["Docker"]
    assert r.json()["title"] == "Updated"
    assert (await client.delete("/api/v1/vacancies/" + v["id"], headers=auth)).status_code == 204
    assert (await client.get("/api/v1/vacancies/" + v["id"], headers=auth)).status_code == 404


@pytest.mark.parametrize(
    "patch",
    [
        {"salary_min": -1},
        {"salary_max": 50},
        {"salary_min": 300},
        {"title": None},
        {"skills": None},
        {"vacancy_url": "bad"},
        {"work_format": "space"},
        {"user_id": "injected"},
        {"application_deadline": "2030-01-01T00:00:00"},
        {"currency": None},
    ],
)
async def test_invalid_patch_rejected_atomically(client, patch):
    auth, _, _ = await account(client)
    v = await vacancy(client, auth, salary_min=100, salary_max=200, currency="USD")
    r = await client.patch("/api/v1/vacancies/" + v["id"], headers=auth, json=patch)
    assert r.status_code == 422, r.text
    assert (await client.get("/api/v1/vacancies/" + v["id"], headers=auth)).json()[
        "salary_min"
    ] == 100


@pytest.mark.parametrize(
    "params,code",
    [
        ({"salary_min": 1}, 400),
        ({"sort": "salary_min"}, 400),
        ({"sort": "password"}, 422),
        ({"page_size": 101}, 422),
        ({"direction": "sideways"}, 422),
        ({"salary_min": 20, "salary_max": 10, "currency": "USD"}, 422),
        (
            {
                "application_deadline_after": "2031-01-01T00:00:00Z",
                "application_deadline_before": "2030-01-01T00:00:00Z",
            },
            422,
        ),
    ],
)
async def test_invalid_filters(client, params, code):
    auth, _, _ = await account(client)
    assert (await client.get("/api/v1/vacancies", headers=auth, params=params)).status_code == code


async def test_skill_normalization_length_is_validated(client):
    auth, _, _ = await account(client)
    c = await company(client, auth)
    r = await client.post(
        "/api/v1/vacancies",
        headers=auth,
        json={"company_id": c["id"], "title": "Intern", "skills": ["ß" * 80]},
    )
    assert r.status_code == 422
