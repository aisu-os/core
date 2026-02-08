# Aisu Core

Aisu Web OS — backend API. FastAPI + PostgreSQL + SQLAlchemy 2.0.

## Ishga tushirish

```bash
# Dependencylar
uv sync

# PostgreSQL (Docker)
docker compose up -d db

# Migratsiyalar
uv run alembic upgrade head

# Dev server
uv run uvicorn aiso_core.main:app --reload --port 8890
```

API docs: http://localhost:8890/docs
