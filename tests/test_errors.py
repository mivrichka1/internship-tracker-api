from app.repository import Repository
from tests.helpers import account


async def test_health_docs_openapi_and_errors(client, monkeypatch):
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/redoc")).status_code == 200
    schema = (await client.get("/openapi.json")).json()
    assert (
        schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"][
            "tokenUrl"
        ]
        == "/api/v1/auth/login"
    )
    assert (await client.get("/missing")).json()["error"]["code"] == "HTTP_404"
    auth, _, _ = await account(client)
    assert (await client.get("/api/v1/companies?sort=invalid", headers=auth)).status_code == 422

    async def broken(self):
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(Repository, "health", broken)
    r = await client.get("/health")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private implementation detail" not in r.text
