import asyncio

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import account, application, vacancy


async def test_application_lifecycle_duplicate_terminal_reopen_and_crud(client):
    auth, _, _ = await account(client)
    v = await vacancy(client, auth)
    a = await application(client, auth, vacancy_id=v["id"])
    aid = a["id"]
    url = "/api/v1/applications/" + aid
    assert a["applied_at"] is None
    assert (
        await client.post("/api/v1/applications", headers=auth, json={"vacancy_id": v["id"]})
    ).status_code == 409
    for stage in ["applied", "interview", "offer"]:
        r = await client.patch(url + "/status", headers=auth, json={"status": stage})
        assert r.status_code == 200, r.text
    before = (await client.get(url + "/history", headers=auth)).json()
    assert (
        await client.patch(url + "/status", headers=auth, json={"status": "offer"})
    ).status_code == 200
    assert (await client.get(url + "/history", headers=auth)).json() == before
    for payload in [
        {"status": "interview"},
        {"status": "rejected", "reopen": True, "comment": "x"},
        {"status": "interview", "reopen": True},
    ]:
        assert (await client.patch(url + "/status", headers=auth, json=payload)).status_code == 409
    assert (
        await client.patch(
            url + "/status",
            headers=auth,
            json={"status": "interview", "reopen": True, "comment": "Company reopened"},
        )
    ).status_code == 200
    assert (
        await client.patch(url + "/status", headers=auth, json={"status": "saved"})
    ).status_code == 409
    assert (
        await client.patch(
            url, headers=auth, json={"notes": "prepare", "next_action_at": "2030-01-01T10:00:00Z"}
        )
    ).status_code == 200
    assert (
        await client.patch(url, headers=auth, json={"notes": None, "next_action_at": None})
    ).json()["notes"] is None
    assert (await client.patch(url, headers=auth, json={"status": "saved"})).status_code == 422
    r = await client.get(
        "/api/v1/applications",
        headers=auth,
        params={
            "status": "interview",
            "vacancy_id": v["id"],
            "search": "Python",
            "sort": "applied_at",
            "direction": "asc",
        },
    )
    assert r.status_code == 200 and r.json()["total"] == 1
    assert (await client.get("/api/v1/vacancies?status=interview", headers=auth)).json()[
        "total"
    ] == 1
    assert (await client.delete(url, headers=auth)).status_code == 204
    assert (await client.get(url, headers=auth)).status_code == 404


async def test_concurrent_status_change_writes_one_event(client):
    auth, _, _ = await account(client)
    a = await application(client, auth, status="applied")
    url = "/api/v1/applications/" + a["id"]
    responses = await asyncio.gather(
        *(
            client.patch(url + "/status", headers=auth, json={"status": "interview"})
            for _ in range(2)
        )
    )
    assert [r.status_code for r in responses] == [200, 200]
    history = (await client.get(url + "/history", headers=auth)).json()
    assert [h["new_status"] for h in history] == ["applied", "interview"]


async def test_status_and_history_rollback_after_flush_failure(client, monkeypatch):
    auth, _, _ = await account(client)
    a = await application(client, auth, status="applied")
    url = "/api/v1/applications/" + a["id"]
    before = (await client.get(url + "/history", headers=auth)).json()

    async def fail_commit(self):
        await self.flush()  # Both UPDATE and history INSERT have reached PostgreSQL.
        raise SQLAlchemyError("injected commit failure")

    with monkeypatch.context() as m:
        m.setattr(AsyncSession, "commit", fail_commit)
        r = await client.patch(url + "/status", headers=auth, json={"status": "interview"})
        assert r.status_code == 503
    assert (await client.get(url, headers=auth)).json()["status"] == "applied"
    assert (await client.get(url + "/history", headers=auth)).json() == before


async def test_saved_withdrawal_not_counted_as_submission(client):
    auth, _, _ = await account(client)
    a = await application(client, auth)
    r = await client.patch(
        "/api/v1/applications/" + a["id"] + "/status", headers=auth, json={"status": "withdrawn"}
    )
    assert r.status_code == 200 and r.json()["applied_at"] is None
    assert (await client.get("/api/v1/analytics/overview", headers=auth)).json()[
        "total_applications"
    ] == 0


async def test_direct_interview_records_submission_and_future_date_rejected(client):
    auth, _, _ = await account(client)
    a = await application(client, auth)
    url = "/api/v1/applications/" + a["id"]
    assert (
        await client.patch(url + "/status", headers=auth, json={"status": "interview"})
    ).status_code == 200
    states = [h["new_status"] for h in (await client.get(url + "/history", headers=auth)).json()]
    assert states == ["saved", "applied", "interview"]
    history = (await client.get(url + "/history", headers=auth)).json()
    assert [h["old_status"] for h in history] == [None, "saved", "applied"]
    v = await vacancy(client, auth)
    for payload in [
        {"status": "saved", "applied_at": "2020-01-01T00:00:00Z"},
        {"status": "applied", "applied_at": "2099-01-01T00:00:00Z"},
    ]:
        assert (
            await client.post(
                "/api/v1/applications", headers=auth, json={"vacancy_id": v["id"], **payload}
            )
        ).status_code == 422
