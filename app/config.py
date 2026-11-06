from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str = Field(min_length=32)
    access_token_minutes: int = Field(15, ge=1, le=1440)
    refresh_token_days: int = Field(30, ge=1, le=365)
    app_env: Literal["development", "test", "production"] = "development"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
