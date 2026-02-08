FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini .

EXPOSE 8890

CMD ["uv", "run", "uvicorn", "aiso_core.main:app", "--host", "0.0.0.0", "--port", "8890"]
