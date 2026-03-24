"""Pydantic schemas used for LLM routing and parsing."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Routing decision returned by the LLM.

    Attributes:
        intent: Classified user intent.
        confidence: Confidence score between 0 and 1.
        followup_question: Optional clarification question when intent is unknown.
    """

    intent: Literal[
        "owned_games",
        "recommendation",
        "profile_update",
        "library_list",
        "library_query",
        "unknown",
    ]
    confidence: float = Field(ge=0, le=1)
    followup_question: str | None = None


class OwnedGame(BaseModel):
    """Normalized representation of a single owned game mention.

    Attributes:
        title: Game title provided by the user.
        platform: Optional platform the user referenced.
        status: Optional ownership status.
        rating: Optional 0-10 rating.
        playtime_hours: Optional playtime in hours.
    """

    title: str = Field(min_length=1)
    platform: str | None = None
    status: Literal["owned", "wishlist", "playing", "completed"] | None = None
    rating: int | None = Field(default=None, ge=0, le=10)
    playtime_hours: float | None = Field(default=None, ge=0)


class OwnedGamesRequest(BaseModel):
    """Container for parsed owned games."""

    games: list[OwnedGame] = Field(default_factory=list)


class LibraryQuery(BaseModel):
    """Request to query details about a specific library game.

    Attributes:
        title: Game title provided by the user.
        fields: Requested fields like rating, playtime, status.
    """

    title: str = Field(min_length=1)
    fields: list[Literal["rating", "playtime", "status"]] = Field(default_factory=list)


class LibraryUpdate(BaseModel):
    """Normalized representation of a library update request.

    Attributes:
        title: Game title provided by the user.
        action: Update or remove the game from the library.
        status: Optional ownership status update.
        rating: Optional 0-10 rating update.
        playtime_hours: Optional playtime update in hours.
    """

    title: str = Field(min_length=1)
    action: Literal["update", "remove"] = "update"
    status: Literal["owned", "wishlist", "playing", "completed"] | None = None
    rating: int | None = Field(default=None, ge=0, le=10)
    playtime_hours: float | None = Field(default=None, ge=0)


class ProfileUpdateRequest(BaseModel):
    """Container for profile and library updates.

    Attributes:
        name: Updated user display name (optional).
        email: Updated email address (optional).
        language: Updated language preference (optional).
        age: Updated age (optional).
        platform: Updated gaming platform (optional).
        library_updates: Library update requests.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    language: str | None = Field(default=None, min_length=1, max_length=50)
    age: int | None = Field(default=None, ge=0)
    platform: str | None = Field(default=None, min_length=1, max_length=80)
    library_updates: list[LibraryUpdate] = Field(default_factory=list)

    def has_updates(self) -> bool:
        """Return True if any update fields were provided."""
        if self.library_updates:
            return True
        return any(
            value is not None
            for value in (self.name, self.email, self.language, self.age, self.platform)
        )
