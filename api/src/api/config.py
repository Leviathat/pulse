"""API configuration from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    es_url: str = "http://elasticsearch:9200"
    redis_url: str = "redis://redis:6379/0"
