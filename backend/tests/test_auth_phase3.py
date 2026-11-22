from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.config import Settings
from app.core.security import create_access_token, get_password_hash, verify_password, verify_token


def test_password_hash_round_trip():
    hashed = get_password_hash("Agent@1234")
    assert hashed != "Agent@1234"
    assert verify_password("Agent@1234", hashed)
    assert not verify_password("wrong-password", hashed)


def test_jwt_contains_subject_and_verifies():
    token = create_access_token(subject=42)
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "42"


def test_expired_jwt_is_rejected():
    token = create_access_token(subject=42, expires_delta=timedelta(seconds=-1))
    assert verify_token(token) is None


def test_invalid_jwt_is_rejected():
    assert verify_token("not-a-valid-jwt") is None


def test_production_settings_reject_missing_or_insecure_jwt_secret():
    with pytest.raises(ValueError):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=None,
            DATABASE_URL="mysql+pymysql://frontdesk:secret@db.railway.internal:3306/frontdesk",
            CORS_ORIGINS=["https://frontdesk.example"],
        )
    with pytest.raises(ValueError):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="a" * 64,
            DATABASE_URL="mysql+pymysql://frontdesk:secret@db.railway.internal:3306/frontdesk",
            CORS_ORIGINS=["https://frontdesk.example"],
        )
    configured = Settings(
        ENVIRONMENT="production",
        JWT_SECRET="e8d1352f4d0ca3bfed3f0189759ab1bd035d4889417811d929c8897cfbaf8a4c",
        DATABASE_URL="mysql://frontdesk:secure-password@db.railway.internal:3306/frontdesk",
        CORS_ORIGINS=["https://frontdesk.example"],
    )
    assert configured.jwt_secret.startswith("e8d")
    assert configured.sync_database_url.startswith("mysql+pymysql://")


def test_production_settings_reject_missing_or_insecure_database_and_cors():
    common = {
        "ENVIRONMENT": "production",
        "JWT_SECRET": "e8d1352f4d0ca3bfed3f0189759ab1bd035d4889417811d929c8897cfbaf8a4c",
        "CORS_ORIGINS": ["https://frontdesk.example"],
    }
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        Settings(**common)
    with pytest.raises(ValueError, match="remote MySQL host"):
        Settings(**common, DATABASE_URL="mysql+pymysql://frontdesk:frontdesk_password@db.railway.internal/frontdesk")
    with pytest.raises(ValueError, match="remote MySQL host"):
        Settings(**common, DATABASE_URL="mysql+pymysql://frontdesk:secret@localhost/frontdesk")
    with pytest.raises(ValueError, match="HTTPS origins"):
        Settings(
            **{**common, "CORS_ORIGINS": ["http://localhost:5173"]},
            DATABASE_URL="mysql+pymysql://frontdesk:secret@db.railway.internal/frontdesk",
        )
