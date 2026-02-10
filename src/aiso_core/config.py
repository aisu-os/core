from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    # Database
    database_url: str = "postgresql+asyncpg://aisu:aisu@localhost:5432/aisu"

    # Auth / JWT
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    # File storage
    upload_dir: str = "./uploads"

    # User defaults
    default_user_cpu: int = 2
    default_user_disk: int = 5120  # MB (5GB)
    default_user_wallpaper: str = "https://images.aisu.run/wallpaper_image.jpg"


settings = Settings()
