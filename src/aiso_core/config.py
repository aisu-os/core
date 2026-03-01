import secrets
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to aiso-core/ directory (src/aiso_core/config.py -> 2 levels up -> aiso-core/)
_env_file = Path(__file__).resolve().parents[2] / ".env"

_INSECURE_DEFAULT_KEY = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_env_file),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Aisu Core"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8890
    app_url: str = "http://localhost:8890"

    # Database
    database_url: str = "postgresql+asyncpg://aisu:aisu@localhost:5432/aisu"

    # Auth / JWT
    secret_key: str = _INSECURE_DEFAULT_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if self.environment == "production" and self.secret_key == _INSECURE_DEFAULT_KEY:
            raise ValueError(
                "SECRET_KEY must be set to a secure value in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return self
    beta_access_enabled: bool = True
    beta_register_url: str = "https://app.aisu.run"
    beta_token_expire_hours: int = 72

    # SMTP (beta invite email)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@aisu.local"
    smtp_use_tls: bool = True
    smtp_ssl: bool = False  # True = SMTP_SSL (port 465), False = STARTTLS (port 587)

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5174",
        "http://localhost:4173",
        "http://localhost:3000",
    ]

    # File storage
    upload_dir: str = "./uploads"

    # User defaults
    default_user_cpu: int = 2
    default_user_disk: int = 5120  # MB (5GB)
    default_user_wallpaper: str = "https://images.aisu.run/aisu_wallpaper_1080p.png"

    # Container
    docker_base_url: str = "unix:///var/run/docker.sock"
    container_image: str = "aisu-user:latest"
    container_runtime: str = "sysbox-runc"
    container_network: str = "aisu-net"
    user_data_base_path: str = "/data/users"
    container_enabled: bool = True  # macOS dev: False
    container_cpu_period: int = 100_000  # Docker CPU period (microseconds)
    container_ram_per_cpu: str = "1g"  # RAM per CPU
    container_pids_limit: int = 64
    container_network_rate: str = "5mbit"

    # Port Forward / Caddy
    caddy_admin_url: str = ""  # Empty = Caddy disabled
    caddy_api_domain: str = ""  # API domain for Caddy reverse proxy (e.g. api.aisu.run)
    caddy_api_upstream: str = "localhost:8890"  # API upstream (Docker: api:8890)
    port_forward_domain: str = "t.localhost"  # prod: t.aisu.run
    port_forward_scheme: str = "http"  # prod: https
    caddy_tls_cert: str = ""  # Container path to TLS cert (e.g. /etc/caddy/certs/origin.pem)
    caddy_tls_key: str = ""  # Container path to TLS key (e.g. /etc/caddy/certs/origin-key.pem)

    # Sentry
    sentry_dsn: str = ""

    # Rate limiting
    rate_limit_backend: str = "memory"  # "memory" or "redis"
    rate_limit_redis_url: str = "redis://localhost:6379/0"
    rate_limit_window_seconds: int = 60
    rate_limit_username_info_per_minute: int = 5
    rate_limit_auth_per_minute: int = 5


settings = Settings()
