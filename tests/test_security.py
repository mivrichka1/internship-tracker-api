from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Application, Vacancy
from tests.helpers import account, application, company, vacancy


async def test_all_private_resources_are_isolated(client):
    owner, _, _ = await account(client)
    visitor, _, _ = await account(client)
    c = await company(client, owner)
    v = await vacancy(client, owner, company_id=c["id"], skills=["PrivateSkill"])
    a = await application(client, owner, vacancy_id=v["id"], status="offer")
    for resource, item in [("companies", c), ("vacancies", v), ("applications", a)]:
        url = "/api/v1/" + resource + "/" + item["id"]
        for method in ["get", "patch", "delete"]:
            kwargs = {"json": {}} if method == "patch" else {}
            assert (
                await getattr(client, method)(url, headers=visitor, **kwargs)
            ).status_code == 404
    url = "/api/v1/applications/" + a["id"]
    assert (await client.get(url + "/history", headers=visitor)).status_code == 404
    assert (
        await client.patch(url + "/status", headers=visitor, json={"status": "interview"})
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/vacancies", headers=visitor, json={"company_id": c["id"], "title": "Steal"}
        )
    ).status_code == 404
    assert (
        await client.post("/api/v1/applications", headers=visitor, json={"vacancy_id": v["id"]})
    ).status_code == 404
    mine = await vacancy(client, visitor)
    assert (
        await client.patch(
            "/api/v1/vacancies/" + mine["id"], headers=visitor, json={"company_id": c["id"]}
        )
    ).status_code == 404
    overview = (await client.get("/api/v1/analytics/overview", headers=visitor)).json()
    assert overview["offers"] == overview["total_applications"] == 0
    for endpoint in ["skills", "timeline"]:
        assert (await client.get("/api/v1/analytics/" + endpoint, headers=visitor)).json() == []
    assert all(
        s["count"] == 0
        for s in (await client.get("/api/v1/analytics/funnel", headers=visitor)).json()
    )
    assert (await client.get("/api/v1/skills", headers=visitor)).json() == []


async def test_database_rejects_cross_owner_foreign_keys(client, db_sessions):
    a_auth, a_user, _ = await account(client)
    _, b_user, _ = await account(client)
    v = await vacancy(client, a_auth)
    async with db_sessions() as db:
        db.add(
            Vacancy(user_id=UUID(b_user["id"]), company_id=UUID(v["company_id"]), title="invalid")
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        db.add(Application(user_id=UUID(b_user["id"]), vacancy_id=UUID(v["id"])))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    assert a_user["id"] != b_user["id"]
