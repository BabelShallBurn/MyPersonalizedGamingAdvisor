"""Pydantic schemas for recommendation requests and responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, conint


class UserIntent(BaseModel):
    """Represents a user's raw query intent for recommendation parsing.
    
    Attributes:
        raw_query: The original user question or search text in any language.
    """


class RecommendationRequest(BaseModel):
    """Represents structured constraints for game recommendations.
    
    Contains user preferences and filters extracted from natural language queries
    or provided directly. All fields are optional.
    
    Attributes:
        platforms: List of desired gaming platforms (e.g., ["Windows", "Linux"]).
        genres: List of preferred game genres (e.g., ["RPG", "Adventure"]).
        age_rating_max: Maximum USK age rating (0-21, None = no limit).
        max_price_eur: Maximum price in EUR (None = no limit).
        coop: If True, only co-op games; False for single-player; None = any.
        playtime_hours_min: Minimum estimated playtime in hours.
        playtime_hours_max: Maximum estimated playtime in hours.
        query_text: Free-form text for semantic similarity search.
    """
    platforms: list[str] | None = Field(
        default=None, description="Gewuenschte Plattformen (z. B. Windows, Linux)"
    )
    genres: list[str] | None = Field(
        default=None, description="Bevorzugte Genres (z. B. RPG, Adventure)"
    )
    age_rating_max: conint(ge=0, le=21) | None = None
    max_price_eur: conint(ge=0) | None = None
    coop: bool | None = None
    playtime_hours_min: conint(ge=0) | None = None
    playtime_hours_max: conint(ge=0) | None = None
    query_text: str | None = Field(
        default=None, description="Optionaler Freitext fuer semantische Suche"
    )


class Recommendation(BaseModel):
    """Represents a single recommended game.
    
    Attributes:
        title: The name of the game.
        platform: Supported platform(s) for this game.
        price_eur: The game's price in EUR or None if free.
        reason: Optional explanation for the recommendation.
    """
    platform: str | None = None
    price_eur: float | None = None
    reason: str | None = None


class RecommendationResponse(BaseModel):
    """Response containing recommendations and the constraints that were applied.
    
    Attributes:
        recommendations: List of recommended games.
        constraints_used: The RecommendationRequest that was used to filter/score games.
    """
    constraints_used: RecommendationRequest


class ValidationReport(BaseModel):
    """Report on validation of recommendations against constraints.
    
    Attributes:
        valid: Whether all recommendations satisfy the constraints.
        issues: List of constraint violations or issues found (if any).
    """
    issues: list[str] = Field(default_factory=list)
