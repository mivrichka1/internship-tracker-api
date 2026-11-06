from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete

from app.models import Application, ApplicationHistory, Status
from tests.helpers import account, application, vacancy


async def test_empty_analytics(client):
    auth, _, _ = await account(client)
    r = (await client.get("/api/v1/analytics/overview", headers=auth)).json()
    assert r["total_applications"] == r["response_rate"] == r["offer_rate"] == 0
    assert r["average_response_hours"] is None
    assert all(
        x["count"] == x["conversion_from_previous"] == 0
        for x in (await client.get("/api/v1/analytics/funnel", headers=auth)).json()
    )
    assert (await client.get("/api/v1/analytics/skills", headers=auth)).json() == []


async def test_known_funnel_revisits_skips_and_response_times(client, db_sessions):
    auth, _, _ = await account(client)
    sequences = [
        [
            ("applied", "2024-01-01"),
            ("screening", "2024-01-02"),
            ("interview", "2024-01-04"),
            ("offer", "2024-01-05"),
        ],
        [("applied", "2024-01-08"), ("interview", "2024-01-09"), ("rejected", "2024-01-10")],
        [
            ("applied", "2024-02-01"),
            ("screening", "2024-02-02"),
            ("assessment", "2024-02-03"),
            ("interview", "2024-02-04"),
            ("screening", "2024-02-05"),
            ("offer", "2024-02-06"),
        ],
        [("applied", "2024-02-10"), ("withdrawn", "2024-02-11")],
    ]
    for sequence in sequences:
        a = await application(
            client, auth, status="applied", applied_at=sequence[0][1] + "T00:00:00Z"
        )
        async with db_sessions() as db:
            obj = await db.get(Application, UUID(a["id"]))
            obj.status = Status(sequence[-1][0])
            await db.execute(
                delete(ApplicationHistory).where(ApplicationHistory.application_id == obj.id)
            )
            old = None
            for state, day in sequence:
                db.add(
                    ApplicationHistory(
                        application_id=obj.id,
                        old_status=old,
                        new_status=Status(state),
                        changed_at=datetime.fromisoformat(day).replace(tzinfo=UTC),
                    )
                )
                old = Status(state)
            await db.commit()
    await application(client, auth)  # A saved vacancy must not enter conversion denominators.
    r = (await client.get("/api/v1/analytics/overview", headers=auth)).json()
    assert r == {
        "total_vacancies": 5,
        "total_applications": 4,
        "active_applications": 0,
        "rejected": 1,
        "offers": 2,
        "response_rate": 0.75,
        "offer_rate": 0.5,
        "average_response_hours": 24,
    }
    f = (await client.get("/api/v1/analytics/funnel", headers=auth)).json()
    assert [s["count"] for s in f] == [4, 2, 1, 3, 2]
    assert [s["conversion_from_applied"] for s in f] == [1, 0.5, 0.25, 0.75, 0.5]
    assert [s["conversion_from_previous"] for s in f] == pytest.approx([1, 0.5, 0.5, 1, 2 / 3])
    months = (await client.get("/api/v1/analytics/timeline?granularity=month", headers=auth)).json()
    assert [x["count"] for x in months] == [2, 2]
    assert [x["period"][:10] for x in months] == ["2024-01-01", "2024-02-01"]
    for granularity in ["day", "week"]:
        rows = (
            await client.get(
                "/api/v1/analytics/timeline", headers=auth, params={"granularity": granularity}
            )
        ).json()
        assert sum(x["count"] for x in rows) == 4
    assert (
        await client.get("/api/v1/analytics/timeline?granularity=year", headers=auth)
    ).status_code == 422


async def test_skills_count_once_per_vacancy_and_active_count(client):
    auth, _, _ = await account(client)
    await vacancy(client, auth, skills=["Python", "python", "SQL"])
    v = await vacancy(client, auth, skills=["PYTHON"])
    await application(client, auth, vacancy_id=v["id"], status="screening")
    rows = (await client.get("/api/v1/analytics/skills", headers=auth)).json()
    assert {x["skill"].casefold(): x["vacancy_count"] for x in rows} == {"python": 2, "sql": 1}
    assert (await client.get("/api/v1/analytics/overview", headers=auth)).json()[
        "active_applications"
    ] == 1


async def test_response_remains_after_withdrawal_and_reopen(client):
    auth, _, _ = await account(client)
    a = await application(client, auth, status="interview")
    url = "/api/v1/applications/" + a["id"] + "/status"
    assert (await client.patch(url, headers=auth, json={"status": "withdrawn"})).status_code == 200
    assert (await client.get("/api/v1/analytics/overview", headers=auth)).json()[
        "response_rate"
    ] == 1
    assert (
        await client.patch(
            url, headers=auth, json={"status": "applied", "reopen": True, "comment": "Reopened"}
        )
    ).status_code == 200
    r = (await client.get("/api/v1/analytics/overview", headers=auth)).json()
    assert r["response_rate"] == r["active_applications"] == r["total_applications"] == 1
