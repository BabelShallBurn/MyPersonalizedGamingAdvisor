"""Pydantic models for game recommendation request and response schemas.

This module defines the API schema for the gaming recommendation system,
including request validation and response formatting.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    """Validates input parameters for game recommendation queries.
    
    Attributes:
        query_text: User's search or preference description (required).
        preferred_genres: List of preferred game genres to filter results.
        max_release_age_years: Optional maximum age of the game in years.
        top_k: Maximum number of recommendations to return (1-50).
        weights: Optional custom weights for scoring recommendations.
    """
    query_text: str = Field(min_length=1)
    preferred_genres: list[str] = Field(default_factory=list)
    max_release_age_years: int | None = Field(default=None, ge=0, le=100)
    top_k: int | None = Field(default=None, ge=1, le=50)
    weights: dict[str, float] | None = None


class RecommendationItem(BaseModel):
    """Represents a single game recommendation with metadata.
    
    Attributes:
        title: Name of the recommended game.
        platform: Gaming platform(s) where the game is available.
        price_eur: Price in Euros, if applicable.
        total_score: Recommendation match score.
        match_reasons: List of reasons explaining why this game was recommended.
    """
    title: str
    platform: str | None = None
    price_eur: float | None = None
    total_score: float | None = None
    match_reasons: list[str] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    """Wraps a list of game recommendations for API responses.
    
    Attributes:
        recommendations: List of RecommendationItem objects returned to the user.
    """
    recommendations: list[RecommendationItem]
