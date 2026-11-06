import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.security import encode_token
from tests.helpers import account


async def test_duplicate_email_and_wrong_password(client):
    auth, user, _ = await account(client)
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": user["email"].upper(),
            "password": "long-enough-password",
            "full_name": "Other",
        },
    )
    assert r.status_code == 409
    for email in [user["email"], "unknown@example.com"]:
        r = await client.post(
            "/api/v1/auth/login", data={"username": email, "password": "incorrect"}
        )
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
    assert (await client.get("/api/v1/users/me", headers=auth)).status_code == 200


async def test_expired_invalid_and_wrong_type_tokens(client):
    _, user, tokens = await account(client)
    expired = encode_token(UUID(user["id"]), "access", datetime.now(UTC) - timedelta(seconds=1))
    for token in [expired, "invalid", tokens["refresh_token"]]:
        r = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token})
        assert r.status_code == 401
    for token in ["bad", tokens["access_token"]]:
        assert (
            await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        ).status_code == 401


async def test_rotation_logout_and_replay(client):
    auth, _, tokens = await account(client)
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    newer = r.json()
    assert newer["refresh_token"] != tokens["refresh_token"]
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/logout", headers=auth, json={"refresh_token": newer["refresh_token"]}
        )
    ).status_code == 204
    assert (
        await client.post(
            "/api/v1/auth/logout", headers=auth, json={"refresh_token": newer["refresh_token"]}
        )
    ).status_code == 204
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": newer["refresh_token"]})
    ).status_code == 401


async def test_concurrent_refresh_only_one_rotation(client):
    _, _, tokens = await account(client)
    responses = await asyncio.gather(
        *(
            client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 401]


async def test_credentials_not_echoed_on_validation(client):
    secret = "secret"
    r = await client.post(
        "/api/v1/auth/register", json={"email": "bad", "password": secret, "full_name": "A"}
    )
    assert r.status_code == 422
    assert secret not in r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_refresh_database_expiry_and_unknown_user(client, db_sessions):
    from uuid import uuid4

    from sqlalchemy import update

    from app.models import RefreshToken

    _, _, tokens = await account(client)
    async with db_sessions() as db:
        await db.execute(
            update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(days=1))
        )
        await db.commit()
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401
    token = encode_token(uuid4(), "access", datetime.now(UTC) + timedelta(minutes=5))
    assert (
        await client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token})
    ).status_code == 401


async def test_argon2id_and_logout_ownership(client, db_sessions):
    from sqlalchemy import select

    from app.models import User

    auth, user, tokens = await account(client)
    other_auth, _, _ = await account(client)
    assert (
        await client.post(
            "/api/v1/auth/logout",
            headers=other_auth,
            json={"refresh_token": tokens["refresh_token"]},
        )
    ).status_code == 204
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 200
    async with db_sessions() as db:
        obj = await db.scalar(select(User).where(User.email == user["email"]))
        assert obj.hashed_password.startswith("$argon2id$")
        assert "a-long-password-123" not in obj.hashed_password
    assert (await client.get("/api/v1/users/me", headers=auth)).status_code == 200


async def test_full_name_matches_database_bounds(client):
    for name in [" " * 3, "a" * 121]:
        r = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid@example.com",
                "password": "long-enough-password",
                "full_name": name,
            },
        )
        assert r.status_code == 422
