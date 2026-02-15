from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# aiso-core/ papkasining yo'li (src/aiso_core/config.py -> 2 daraja yuqori -> aiso-core/)
_env_file = Path(__file__).resolve().parents[2] / ".env"


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
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    beta_access_enabled: bool = True
    beta_register_url: str = "http://localhost:5174/register"
    beta_token_expire_hours: int = 72

    # SMTP (beta invite email)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@aisu.local"
    smtp_use_tls: bool = True

    # CORS
    cors_origins: list[str] = ["http://localhost:5174", "http://localhost:4173"]

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
    container_ram_per_cpu: str = "1g"  # Har bir CPU uchun RAM
    container_pids_limit: int = 64
    container_network_rate: str = "5mbit"

    # Rate limiting
    rate_limit_backend: str = "memory"  # "memory" or "redis"
    rate_limit_redis_url: str = "redis://localhost:6379/0"
    rate_limit_window_seconds: int = 60
    rate_limit_username_info_per_minute: int = 5


settings = Settings()
