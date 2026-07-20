"""API request/response models."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MonitorCreate(BaseModel):
    """Payload for creating a monitor."""

    name: str = Field(min_length=1, max_length=200)
    keywords: list[str] = Field(min_length=1)

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [k.strip() for k in value if k.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty keyword is required")
        return cleaned


class Monitor(MonitorCreate):
    """A stored monitor."""

    id: str
    created_at: datetime
