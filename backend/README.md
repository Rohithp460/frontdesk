# Frontdesk Backend

FastAPI backend with SQLAlchemy 2.0, Alembic migrations, MySQL 8 driver, and JWT authentication.

## Setup

```bash
# 1. Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env

# 4. Start local development server
uvicorn app.main:app --reload --port 8000
```

## Running Tests

```bash
pytest
```

## Database Migrations

```bash
# Generate a new migration
alembic revision --autogenerate -m "create initial tables"

# Apply migrations
alembic upgrade head
```
