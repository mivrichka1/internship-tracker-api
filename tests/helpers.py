from uuid import uuid4


async def account(client):
    email = f"{uuid4().hex}@example.com"
    password = "a-long-password-123"
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert r.status_code == 201, r.text
    user = r.json()
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    tokens = r.json()
    return {"Authorization": "Bearer " + tokens["access_token"]}, user, tokens


async def company(client, auth, **kwargs):
    r = await client.post(
        "/api/v1/companies", headers=auth, json={"name": "Company " + uuid4().hex, **kwargs}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def vacancy(client, auth, **kwargs):
    cid = kwargs.pop("company_id", None) or (await company(client, auth))["id"]
    r = await client.post(
        "/api/v1/vacancies",
        headers=auth,
        json={"company_id": cid, "title": "Python Intern", **kwargs},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def application(client, auth, **kwargs):
    vid = kwargs.pop("vacancy_id", None) or (await vacancy(client, auth))["id"]
    r = await client.post("/api/v1/applications", headers=auth, json={"vacancy_id": vid, **kwargs})
    assert r.status_code == 201, r.text
    return r.json()
