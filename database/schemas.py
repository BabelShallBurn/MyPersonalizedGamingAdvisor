"""Pydantic input schemas for validation before database persistence."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_USK_RATINGS = {0, 6, 12, 16, 18}
VALID_SYSTEM_PLATFORMS = {"pc", "mac", "linux"}


class SystemRequirementIn(BaseModel):
    """Validated platform specific system requirement payload."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    platform: str = Field(min_length=2, max_length=10)
    minimum: str = ""
    recommended: str | None = None

    @field_validator("platform", mode="before")
    @classmethod
    def normalize_platform(cls, value: Any) -> str:
        """Normalize platform names to supported values."""
        if value is None:
            raise ValueError("platform is required")
        normalized = str(value).strip().lower()
        if normalized not in VALID_SYSTEM_PLATFORMS:
            raise ValueError(f"unsupported platform: {normalized}")
        return normalized


class GameIn(BaseModel):
    """Validated input payload for creating a game record."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    appid: int | None = None
    name: str = Field(min_length=1)
    description: str = ""
    genres: str = ""
    usk: int = 0
    price: Decimal = Decimal("0.00")
    platforms: str = ""
    minimum_requirements: str = ""
    recommended_requirements: str | None = None
    system_requirements: list[SystemRequirementIn] = Field(default_factory=list)
    release_date: str = ""
    recommendations: int = 0

    @field_validator("usk", mode="before")
    @classmethod
    def normalize_usk(cls, value: Any) -> int:
        """Normalize Steam age rating to known USK values."""
        if value in (None, ""):
            return 0
        try:
            rating = int(value)
        except (TypeError, ValueError):
            return 0
        return rating if rating in VALID_USK_RATINGS else 0

    @field_validator("price", mode="before")
    @classmethod
    def normalize_price(cls, value: object) -> Decimal:
        """Convert and clamp price values to non-negative decimals."""
        if value in (None, ""):
            return Decimal("0.00")
        try:
            price = Decimal(str(value))
        except Exception:  # Decimal conversion errors vary by input type.
            return Decimal("0.00")
        return price if price >= 0 else Decimal("0.00")

    @field_validator("recommendations", mode="before")
    @classmethod
    def normalize_recommendations(cls, value: Any) -> int:
        """Convert recommendation counts to a non-negative integer."""
        if value in (None, ""):
            return 0
        try:
            recommendations = int(value)
        except (TypeError, ValueError):
            return 0
        return recommendations if recommendations >= 0 else 0


class UserCreate(BaseModel):
    """Validated input payload for user creation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    language: str = Field(min_length=1, max_length=50)
    age: int = Field(ge=0)
    platform: str = Field(min_length=1, max_length=80)


class UserUpdate(BaseModel):
    """Validated optional input payload for user updates."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    language: str | None = Field(default=None, min_length=1, max_length=50)
    age: int | None = Field(default=None, ge=0)
    platform: str | None = Field(default=None, min_length=1, max_length=80)
