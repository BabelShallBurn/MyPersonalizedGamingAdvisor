"""Pydantic input schemas for validation before database persistence."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_USK_RATINGS = {0, 6, 12, 16, 18}
VALID_SYSTEM_PLATFORMS = {"pc", "mac", "linux"}


class SystemRequirementIn(BaseModel):
    """Validated platform specific system requirement payload.
    
    Automatically normalizes platform names and strips whitespace.
    Ignores extra fields during validation.
    
    Attributes:
        platform: Platform name ("pc", "mac", or "linux" - case-insensitive).
        minimum: Minimum system requirements (free-form text).
        recommended: Recommended requirements or None.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    platform: str = Field(min_length=2, max_length=10)
    minimum: str = ""
    recommended: str | None = None

    @field_validator("platform", mode="before")
    @classmethod
    def normalize_platform(cls, value: Any) -> str:
        """Normalize platform names to supported values.
        
        Converts platform names to lowercase and validates against supported list.
        
        Args:
            value: The platform name to normalize.
        
        Returns:
            The normalized platform name ("pc", "mac", or "linux").
        
        Raises:
            ValueError: If platform is None, empty, or not in supported list.
        """
        if value is None:
            raise ValueError("platform is required")
        normalized = str(value).strip().lower()
        if normalized not in VALID_SYSTEM_PLATFORMS:
            raise ValueError(f"unsupported platform: {normalized}")
        return normalized


class GameIn(BaseModel):
    """Validated input payload for creating a game record.
    
    Automatically normalizes and validates game data from external sources (e.g., Steam).
    Invalid values are coerced to safe defaults rather than raising errors.
    Ignores extra fields during validation.
    
    Attributes:
        appid: Optional Steam application ID.
        name: Game title (required, min 1 character).
        description: Full game description.
        genres: Comma-separated genre list.
        usk: USK age rating - normalized to valid values (0, 6, 12, 16, 18).
        price: Price in EUR - validated as non-negative decimal.
        platforms: Comma-separated platform list.
        system_requirements: List of platform-specific requirements.
        release_date: Release date (ISO format or text).
        recommendations: Steam recommendation count - validated as non-negative.
    """

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
        """Normalize Steam age rating to known USK values.
        
        Converts invalid ratings to 0 (unrated).
        Valid ratings: 0, 6, 12, 16, 18.
        
        Args:
            value: The USK rating value to validate.
        
        Returns:
            A valid USK rating or 0 if invalid/missing.
        """
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
        """Convert and clamp price values to non-negative decimals.
        
        Args:
            value: The price value (int, float, string, Decimal, or None).
        
        Returns:
            A non-negative Decimal price or 0.00 if invalid/missing.
        """
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
        """Convert recommendation counts to a non-negative integer.
        
        Args:
            value: The recommendation count (int, string, or None).
        
        Returns:
            A non-negative integer count or 0 if invalid/missing.
        """
        if value in (None, ""):
            return 0
        try:
            recommendations = int(value)
        except (TypeError, ValueError):
            return 0
        return recommendations if recommendations >= 0 else 0


class UserCreate(BaseModel):
    """Validated input payload for user creation.
    
    Enforces strict validation - rejects extra fields and requires all fields.
    Automatically strips whitespace from string fields.
    
    Attributes:
        name: User's display name (1-120 characters).
        email: User's email address (3-254 characters, must be unique in database).
        language: User's preferred language (1-50 characters).
        age: User's age (must be >= 0).
        platform: User's primary gaming platform (1-80 characters).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    language: str = Field(min_length=1, max_length=50)
    age: int = Field(ge=0)
    platform: str = Field(min_length=1, max_length=80)


class UserUpdate(BaseModel):
    """Validated optional input payload for user updates.
    
    All fields are optional (None = no update). Allows partial updates.
    Enforces strict validation - rejects extra fields.
    Automatically strips whitespace from string fields.
    
    Attributes:
        name: Updated user display name (1-120 chars, optional).
        email: Updated email address (3-254 chars, optional, must be unique).
        language: Updated language preference (1-50 chars, optional).
        age: Updated age (>= 0, optional).
        platform: Updated gaming platform (1-80 chars, optional).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    language: str | None = Field(default=None, min_length=1, max_length=50)
    age: int | None = Field(default=None, ge=0)
    platform: str | None = Field(default=None, min_length=1, max_length=80)
