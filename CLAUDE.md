# CLAUDE.md

Bu fayl Claude Code (claude.ai/code) ga ushbu repozitoriyada ishlashda ko'rsatma beradi.

## Loyiha haqida

Aisu Core — Aisu Web OS ning Python backend qismi. FastAPI framework asosida qurilgan. `src/aiso_core/` papkasida asosiy kod joylashgan. `migrations/` papkasida Alembic migratsiyalari, `tests/` papkasida testlar joylashgan.

## Buyruqlar

Barcha buyruqlar `aiso-core/` papkasidan ishga tushiriladi. `pip` emas, `uv` ishlatiladi.

```bash
cd aiso-core

# Virtual muhit yaratish va dependencylar o'rnatish
uv sync

# Development server (hot-reload)
uv run uvicorn aiso_core.main:app --reload --port 8890

# Testlar
uv run pytest

# Testlar (coverage bilan)
uv run pytest --cov=aiso_core

# Linting
uv run ruff check src/
uv run ruff format src/

# Type checking
uv run mypy src/

# Alembic migratsiya yaratish
uv run alembic revision --autogenerate -m "tavsif"

# Migratsiyalarni qo'llash
uv run alembic upgrade head

# Docker bilan ishga tushirish (PostgreSQL + API)
docker compose up -d
```

## Arxitektura

### Tech stack
- Python 3.12+ (strict typing)
- FastAPI (web framework, async)
- SQLAlchemy 2.0 (async ORM, `Mapped` sintaksis)
- Alembic (database migratsiyalari)
- Pydantic v2 (validatsiya va sozlamalar)
- PostgreSQL 16 (asyncpg driver)
- uv (paket menejeri)
- Ruff (linting va formatlash)

### Asosiy tuzilma (`src/aiso_core/`)

**Kirish nuqtasi:** `main.py` — FastAPI app factory, CORS middleware, lifespan (startup/shutdown).

**`config.py`** — Pydantic Settings. `.env` fayldan muhit o'zgaruvchilarini o'qiydi. `settings` singlton obyekti.

**`database.py`** — SQLAlchemy async engine va session factory. `get_db()` dependency.

**`dependencies.py`** — FastAPI dependency injection: `get_current_user` (JWT tekshiruv), `get_developer_user`, `get_admin_user` (rol tekshiruv).

**`models/`** — SQLAlchemy ORM modellari. `base.py` da `Base`, `UUIDMixin`, `TimestampMixin`. Har bir model alohida fayl: `user.py`, `app.py`, `app_version.py`, `app_install.py`, `app_permission.py`, `app_review.py`, `app_screenshot.py`. `__init__.py` barcha modellarni import qiladi (Alembic uchun).

**`schemas/`** — Pydantic v2 request/response sxemalari. `common.py` da umumiy sxemalar (pagination, error, health). Har bir domen uchun alohida fayl.

**`api/`** — Route qatlami. `router.py` barcha v1 route'larni birlashtiradi. `v1/` papkasida har bir endpoint guruhi alohida fayl. Route faqat HTTP qabul qilish/qaytarish bilan shug'ullanadi — biznes logika `services/` da.

**`services/`** — Biznes logika qatlami. `auth_service.py` (registratsiya, login, JWT), `app_service.py` (CRUD, qidiruv), `install_service.py` (o'rnatish, ruxsatlar), `review_service.py` (sharhlar), `admin_service.py` (tekshiruv pipeline).

**`utils/`** — Yordamchi funksiyalar. `security.py` (parol hash, JWT), `pagination.py` (sahifalash).

### API tuzilishi

Barcha endpointlar `/api/v1/` prefix bilan. Port: **8890**. Guruhlari:
- `/api/v1/health` — Sog'lik tekshiruvi
- `/api/v1/auth/` — Registratsiya, login, profil
- `/api/v1/market/` — Ommaviy market endpointlari (auth kerak emas)
- `/api/v1/user/` — Foydalanuvchi operatsiyalari (auth kerak)
- `/api/v1/developer/` — Dasturchi operatsiyalari (developer role kerak)
- `/api/v1/admin/` — Admin operatsiyalari (admin role kerak)

API spetsifikatsiyasi: `docs/APP_MARKET_ARCHITECTURE.md` — endpointlar, response formatlar, DB sxema.

### Konvensiyalar

- Papkalar va fayllar: `snake_case` (`auth_service.py`, `app_version.py`)
- ORM modellari: `PascalCase` sinf nomi, `snake_case` jadval nomi (`User` -> `users`)
- Pydantic sxemalari: `PascalCase` + suffix (`UserCreate`, `UserResponse`, `AppListResponse`)
- API route funksiyalari: `snake_case` (`get_apps`, `create_review`)
- Import tartibi: stdlib -> third-party -> local (Ruff avtomatik tartiblaydi)
- Type hintlar: har doim yozish **majburiy** (mypy strict mode)
- Async: barcha DB operatsiyalar `async/await` ishlatadi
- Service pattern: Route -> Service -> Model. Route'da biznes logika yozilMAYDI
- Error handling: `HTTPException` faqat route yoki service qatlamida

### Yangi endpoint qo'shish tartibi

1. `schemas/` da request/response sxema yaratish
2. `services/` da biznes logika yozish
3. `api/v1/` dagi tegishli route faylga endpoint qo'shish
4. `tests/` da test yozish

### Yangi model qo'shish tartibi

1. `models/` da yangi fayl yaratish (Base, mixinlardan meros)
2. `models/__init__.py` ga import qo'shish
3. `uv run alembic revision --autogenerate -m "add tablename table"` migratsiya yaratish
4. `uv run alembic upgrade head` migratsiyani qo'llash

### Docker

```bash
# Faqat PostgreSQL (lokal development uchun)
docker compose up -d db

# PostgreSQL + API (to'liq)
docker compose up -d

# Qayta build qilish
docker compose up --build
```

PostgreSQL: `aisu:aisu@localhost:5432/aisu`
