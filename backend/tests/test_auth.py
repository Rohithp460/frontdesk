import pytest
from fastapi.testclient import TestClient


ADMIN_EMAIL = "admin@frontdesk.local"
ADMIN_PASSWORD = "Admin@1234"
AGENT_EMAIL = "alice@frontdesk.local"
AGENT_PASSWORD = "Agent@1234"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------

def test_login_success_admin(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert data["agent"]["email"] == ADMIN_EMAIL
    assert data["agent"]["role"] == "ADMIN"


def test_login_success_agent(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": AGENT_EMAIL, "password": AGENT_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["agent"]["role"] == "AGENT"


def test_login_wrong_password(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": "wrongpassword"},
    )
    assert resp.status_code == 401


def test_login_unknown_email(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@frontdesk.local", "password": "whatever"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/auth/me
# ---------------------------------------------------------------------------

def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)  # HTTPBearer raises 401 or 403 depending on version


def test_me_returns_profile(client: TestClient) -> None:
    # 1. Login to get a token
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    token = login_resp.json()["access_token"]

    # 2. Use token on /me
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200, me_resp.text
    data = me_resp.json()
    assert data["email"] == ADMIN_EMAIL
    assert data["role"] == "ADMIN"
    assert "hashed_password" not in data


def test_me_invalid_token(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
