from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    rabbitmq_url: str
    api_key: str = Field(min_length=16)
    webhook_signing_secret: str = Field(min_length=16)

    gateway_delay_min_seconds: float = Field(default=2.0, ge=0)
    gateway_delay_max_seconds: float = Field(default=5.0, ge=0)
    gateway_success_rate: float = Field(default=0.9, ge=0, le=1)
    webhook_timeout_seconds: float = Field(default=5.0, gt=0)
    outbox_poll_interval_seconds: float = Field(default=0.5, gt=0)

    @model_validator(mode="after")
    def validate_delay(self) -> "Settings":
        if self.gateway_delay_max_seconds < self.gateway_delay_min_seconds:
            raise ValueError("gateway max delay must be >= min delay")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
