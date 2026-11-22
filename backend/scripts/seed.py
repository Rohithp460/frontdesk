"""
Seed script: creates one admin and two agents in the database.

Usage (from backend/ directory, with venv active):
    python scripts/seed.py

Safe to run multiple times — skips existing emails.
"""

import sys
import os

# Allow running from the backend/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.agent import Agent
from app.models.enums import AgentRole
from app.core.security import get_password_hash
from app.core.config import settings

SEED_AGENTS = [
    {
        "name": "Meera Krishnan",
        "email": "meera@arvo.example",
        "password": "Admin@1234",
        "role": AgentRole.ADMIN,
    },
    {
        "name": "Priya Menon",
        "email": "priya@arvo.example",
        "password": "Agent@1234",
        "role": AgentRole.AGENT,
    },
    {
        "name": "Arjun Nair",
        "email": "arjun@arvo.example",
        "password": "Agent@1234",
        "role": AgentRole.AGENT,
    },
]


def _agents_to_seed(environment: str = settings.ENVIRONMENT) -> list[dict]:
    if environment.lower() != "production":
        return SEED_AGENTS

    required = {
        "name": os.getenv("FRONTDESK_BOOTSTRAP_NAME"),
        "email": os.getenv("FRONTDESK_BOOTSTRAP_EMAIL"),
        "password": os.getenv("FRONTDESK_BOOTSTRAP_PASSWORD"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Production bootstrap requires FRONTDESK_BOOTSTRAP_NAME, "
            "FRONTDESK_BOOTSTRAP_EMAIL, and FRONTDESK_BOOTSTRAP_PASSWORD"
        )

    try:
        role = AgentRole(os.getenv("FRONTDESK_BOOTSTRAP_ROLE", "ADMIN").upper())
    except ValueError as exc:
        raise ValueError("FRONTDESK_BOOTSTRAP_ROLE must be ADMIN or AGENT") from exc

    return [{**required, "role": role}]


def seed() -> None:
    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for data in _agents_to_seed():
            existing = db.query(Agent).filter(Agent.email == data["email"]).first()
            if existing:
                print(f"  skip  {data['email']}  (already exists, role={existing.role})")
                skipped += 1
                continue

            agent = Agent(
                name=data["name"],
                email=data["email"],
                hashed_password=get_password_hash(data["password"]),
                role=data["role"],
            )
            db.add(agent)
            db.flush()
            print(f"  create {data['email']}  role={data['role'].value}  id={agent.id}")
            created += 1

        db.commit()
        print(f"\nDone — {created} created, {skipped} skipped.")
    except Exception as exc:
        db.rollback()
        print(f"\nSeed failed: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding agents…")
    seed()
