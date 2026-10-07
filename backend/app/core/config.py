from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="HOUSE_", case_sensitive=False, extra="ignore"
    )

    app_name: str = "Autonomous House OS"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./house_os.db"
    database_auto_create: bool = True
    secret_key: str = "development-only-change-this-secret-key"
    access_token_minutes: int = 30
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_per_minute: int = 120

    mqtt_enabled: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False
    mqtt_keepalive: int = 60
    mqtt_client_id: str = "house-os-backend"
    command_timeout_seconds: float = 8.0
    command_max_retries: int = 2

    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_pin: str | None = None
    redis_url: str | None = None

    @field_validator("secret_key")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("secret_key must contain at least 32 characters")
        return value

    @field_validator("command_max_retries")
    @classmethod
    def retries_are_bounded(cls, value: int) -> int:
        if not 0 <= value <= 5:
            raise ValueError("command_max_retries must be between 0 and 5")
        return value

    @model_validator(mode="after")
    def production_security(self) -> "Settings":
        if self.environment == "production":
            if self.secret_key == "development-only-change-this-secret-key":
                raise ValueError("production requires a unique secret_key")
            if self.database_auto_create:
                raise ValueError("production must use Alembic; set database_auto_create=false")
            if self.mqtt_enabled and (not self.mqtt_username or not self.mqtt_password):
                raise ValueError("production MQTT requires username and password")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
