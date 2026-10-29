import re

import pytest

from app.config import get_settings
from tests.conftest import register


def test_register_login_me(client):
    h = register(client, "ana", "password123", "Ana@Example.com")
    assert client.get("/api/auth/me", headers=h).json() == {
        "id": 1,
        "username": "ana",
        "email": "ana@example.com",
        "cash": 1000,
    }
    dupe_name = {"username": "ANA", "password": "password123", "email": "other@x.io"}
    assert client.post("/api/auth/register", json=dupe_name).status_code == 409
    dupe_email = {"username": "ana2", "password": "password123", "email": "ana@example.com"}
    assert client.post("/api/auth/register", json=dupe_email).status_code == 409
    bad_email = {"username": "bob", "password": "password123", "email": "nope"}
    assert client.post("/api/auth/register", json=bad_email).status_code == 422

    for ident in ("ana", "ANA@example.com"):  # username or email
        r = client.post("/api/auth/login", data={"username": ident, "password": "password123"})
        assert r.status_code == 200
    r = client.post("/api/auth/login", data={"username": "ana", "password": "wrong-pass"})
    assert r.status_code == 401


def test_password_reset_flow(client, caplog):
    old = register(client, "ana", "password123")
    caplog.set_level("INFO", logger="fomoshi.email")
    r = client.post("/api/auth/forgot-password", json={"email": "ana@x.io"})
    assert r.status_code == 202
    token = re.search(r"token=([\w-]+)", caplog.text).group(1)
    # unknown emails get the same answer
    assert client.post("/api/auth/forgot-password", json={"email": "who@x.io"}).status_code == 202

    r = client.post("/api/auth/reset-password", json={"token": token, "password": "brandnew123"})
    assert r.status_code == 200
    new = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=new).status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401  # old sessions revoked
    again = client.post("/api/auth/reset-password", json={"token": token, "password": "x" * 9})
    assert again.status_code == 400  # one use only
    login = client.post("/api/auth/login", data={"username": "ana", "password": "brandnew123"})
    assert login.status_code == 200


def test_change_password_and_delete_account(client):
    h = register(client, "ana", "password123")
    bad = {"current_password": "nope-nope", "new_password": "another123"}
    assert client.post("/api/auth/change-password", headers=h, json=bad).status_code == 400
    ok = {"current_password": "password123", "new_password": "another123"}
    r = client.post("/api/auth/change-password", headers=h, json=ok)
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}

    client.post("/api/leagues", headers=h2, json={"name": "Ana's league"})
    wrong = client.post("/api/auth/delete-account", headers=h2, json={"password": "password123"})
    assert wrong.status_code == 400
    r = client.post("/api/auth/delete-account", headers=h2, json={"password": "another123"})
    assert r.status_code == 204
    assert client.get("/api/auth/me", headers=h2).status_code == 401
    register(client, "ana", "password123")  # name is free again


def test_login_is_rate_limited(client, monkeypatch):
    import app.ratelimit

    # Pin the clock so all attempts land in the same one-minute window.
    monkeypatch.setattr(app.ratelimit, "_now", lambda: 1_800_000_030.0)
    register(client, "ana", "password123")
    codes = [
        client.post(
            "/api/auth/login", data={"username": "ana", "password": "bad-guess"}
        ).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]


def test_production_settings_are_checked(monkeypatch):
    from app.config import DEV_SECRET, Settings

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(environment="production", secret_key=DEV_SECRET, database_url="postgresql://x/y")
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(environment="production", secret_key="k" * 40, database_url="sqlite:///x.db")
    s = Settings(environment="production", secret_key="k" * 40, database_url="postgres://u@h/db")
    assert s.database_url == "postgresql+psycopg://u@h/db"
    assert get_settings().environment == "test"
