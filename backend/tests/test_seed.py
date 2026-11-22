import pytest

from app.models.enums import AgentRole
from scripts.seed import _agents_to_seed


def test_production_seed_requires_explicit_account(monkeypatch):
    monkeypatch.delenv("FRONTDESK_BOOTSTRAP_NAME", raising=False)
    monkeypatch.delenv("FRONTDESK_BOOTSTRAP_EMAIL", raising=False)
    monkeypatch.delenv("FRONTDESK_BOOTSTRAP_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="Production bootstrap requires"):
        _agents_to_seed("production")


def test_production_seed_uses_explicit_admin_credentials(monkeypatch):
    monkeypatch.setenv("FRONTDESK_BOOTSTRAP_NAME", "Deployment Admin")
    monkeypatch.setenv("FRONTDESK_BOOTSTRAP_EMAIL", "admin@example.test")
    monkeypatch.setenv("FRONTDESK_BOOTSTRAP_PASSWORD", "a-unique-secret-password")
    monkeypatch.setenv("FRONTDESK_BOOTSTRAP_ROLE", "admin")

    result = _agents_to_seed("production")

    assert len(result) == 1
    assert result[0]["email"] == "admin@example.test"
    assert result[0]["role"] == AgentRole.ADMIN
    assert result[0]["password"] == "a-unique-secret-password"
