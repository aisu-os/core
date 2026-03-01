# Aisu Core — Backend API

The Python backend for Aisu Web OS. Built with FastAPI, async SQLAlchemy, and PostgreSQL.

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12+ | Runtime (strict typing) |
| FastAPI | 0.115+ | Async web framework |
| SQLAlchemy | 2.0+ | Async ORM (`Mapped` syntax) |
| PostgreSQL | 16 | Database (via asyncpg) |
| Alembic | 1.14+ | Database migrations |
| Pydantic | 2.10+ | Validation and settings |
| Redis | 5.0+ | Caching and rate limiting |
| Docker | 7.0+ | Container management |
| Sentry | 2.53+ | Error tracking |

## Getting Started

```bash
cd aiso-core

# Install dependencies (uv, not pip!)
uv sync

# Configure environment
cp .env.example .env
# Generate a secret key:
# python -c "import secrets; print(secrets.token_urlsafe(64))"

# Create Docker network (first time only)
docker network create aisu-net

# Start PostgreSQL and Redis
docker compose up -d db redis caddy

# Run database migrations
uv run alembic upgrade head

# Start the development server (http://localhost:8890)
uv run uvicorn aiso_core.main:app --reload --port 8890
```

### Commands

```bash
# Server
uv run uvicorn aiso_core.main:app --reload --port 8890

# Testing
uv run pytest                    # Run tests
uv run pytest --cov=aiso_core    # Run tests with coverage

# Code quality
uv run ruff check src/           # Lint
uv run ruff format src/          # Format
uv run mypy src/                 # Type check (strict mode)

# Database migrations
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head

# Docker
docker compose up -d             # Start all services
docker compose up -d db          # PostgreSQL only (local dev)
docker compose up --build        # Rebuild and start
```

### Environment Variables

```bash
# Application
DEBUG=true
ENVIRONMENT=development

# Database
DATABASE_URL=postgresql+asyncpg://aisu:aisu@localhost:5432/aisu

# Authentication (REQUIRED: generate a secure key for production)
SECRET_KEY=                              # python -c "import secrets; print(secrets.token_urlsafe(64))"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# CORS
CORS_ORIGINS=["http://localhost:5173","http://localhost:4173"]

# Server
HOST=0.0.0.0
PORT=8890

# Port Forwarding / Caddy
CADDY_ADMIN_URL=http://localhost:2019
PORT_FORWARD_DOMAIN=t.localhost
PORT_FORWARD_SCHEME=http
```

## Architecture

### Project Structure

```
src/aiso_core/
├── main.py             # FastAPI app factory, CORS, lifespan
├── config.py           # Pydantic Settings (reads from .env)
├── database.py         # Async SQLAlchemy engine & session factory
├── dependencies.py     # FastAPI DI: get_current_user, role checks
│
├── models/             # SQLAlchemy ORM models
│   ├── base.py         #   Base, UUIDMixin, TimestampMixin
│   ├── user.py         #   User model
│   ├── user_session.py #   Session management
│   ├── file_system_node.py  # Virtual file system
│   ├── app.py          #   App metadata
│   ├── app_version.py  #   App versions
│   ├── app_install.py  #   User app installations
│   ├── app_permission.py    # Permission records
│   ├── port_forward.py #   Port forwarding rules
│   └── ...             #   Other domain models
│
├── schemas/            # Pydantic v2 request/response models
│   ├── common.py       #   HealthResponse, PaginationResponse, ErrorResponse
│   ├── user.py         #   UserCreate, UserResponse, TokenResponse
│   ├── file_system.py  #   FileNodeResponse, DirectoryListResponse
│   └── ...             #   Other domain schemas
│
├── api/                # Route layer
│   ├── router.py       #   Aggregates all v1 routes
│   └── v1/             #   Endpoint groups
│       ├── health.py   #     GET /health
│       ├── auth.py     #     POST /register, /login, GET /me
│       ├── session.py  #     Session CRUD
│       ├── file_system.py  # File operations
│       ├── terminal.py #     WebSocket terminal
│       ├── container.py    # Container lifecycle
│       ├── port_forward.py # Port forwarding CRUD
│       ├── settings.py #     App user settings
│       └── beta.py     #     Beta access requests
│
├── services/           # Business logic layer
│   ├── auth_service.py       # Registration, login, JWT
│   ├── session_service.py    # Session lifecycle
│   ├── file_system_service.py# File operations
│   ├── container_service.py  # Container management
│   ├── terminal_service.py   # Terminal sessions
│   ├── docker_client.py      # Docker API wrapper
│   ├── caddy_service.py      # Caddy reverse proxy
│   └── ...
│
├── utils/              # Helpers
│   ├── security.py     #   Password hashing, JWT tokens
│   ├── pagination.py   #   Pagination utilities
│   └── rate_limiter.py #   Rate limiting
│
└── data/               # Static data
    └── system_apps.py  #   Pre-defined system apps
```

### API Endpoints

All endpoints are prefixed with `/api/v1/`. The API runs on port **8890**.

| Group | Prefix | Description |
|-------|--------|-------------|
| Health | `/health` | Health check with DB status |
| Auth | `/auth/` | Registration, login, profile |
| Session | `/session/` | Session CRUD |
| File System | `/filesystem/` | File and directory operations |
| Terminal | `/terminal/` | WebSocket terminal emulation |
| Container | `/container/` | Container lifecycle management |
| Port Forward | `/port-forward/` | Port forwarding rules |
| Settings | `/settings/` | Per-app user settings |
| Beta | `/beta/` | Beta access requests |

### Design Patterns

- **Service Pattern** — Routes handle HTTP only; business logic lives in `services/`. Never put business logic in route handlers.
- **Async Everything** — All database operations use `async/await`.
- **Dependency Injection** — `get_db()` for sessions, `get_current_user` for auth, role-based guards for authorization.
- **Optimistic Responses** — File system operations return expected state immediately.

## Adding New Features

### New Endpoint

1. Create request/response schemas in `schemas/`
2. Write business logic in `services/`
3. Add the route in the appropriate `api/v1/` file
4. Write tests in `tests/`

### New Database Model

1. Create a model file in `models/` (inherit from `Base` and mixins)
2. Import it in `models/__init__.py`
3. Generate a migration: `uv run alembic revision --autogenerate -m "add tablename table"`
4. Apply the migration: `uv run alembic upgrade head`

## Conventions

| Rule | Example |
|------|---------|
| Files & directories | `snake_case` — `auth_service.py`, `app_version.py` |
| ORM models | `PascalCase` class, `snake_case` table — `User` → `users` |
| Pydantic schemas | `PascalCase` + suffix — `UserCreate`, `UserResponse` |
| Route functions | `snake_case` — `get_apps`, `create_review` |
| Type hints | Required everywhere (mypy strict mode) |
| Import order | stdlib → third-party → local (Ruff auto-sorts) |

## Docker

```bash
# Full stack (PostgreSQL + Redis + Caddy + API)
docker compose up -d

# PostgreSQL only (local development)
docker compose up -d db

# Rebuild
docker compose up --build
```

**Services:**

| Service | Port | Image |
|---------|------|-------|
| PostgreSQL | 5432 | `postgres:16-alpine` |
| Redis | 6379 | `redis:7-alpine` |
| Caddy | 80, 2019 | `caddy:2-alpine` |
| API | 8890 | Custom (Python 3.12 slim) |

Default database credentials: `aisu:aisu@localhost:5432/aisu`

## License

MIT
