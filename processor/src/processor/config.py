"""Runtime configuration, read from environment variables (Pydantic Settings)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    kafka_brokers: str = "kafka:9092"
    kafka_topic: str = "raw_articles"
    kafka_group_id: str = "pulse-processor"
    es_url: str = "http://elasticsearch:9200"
