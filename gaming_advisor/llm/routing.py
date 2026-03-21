"""LLM routing and parsing helpers for user chat inputs."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
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


def route_user_text(user_text: str, llm: Any) -> RouteDecision:
    """Classify user text into a routing decision.

    Args:
        user_text: Raw user input.
        llm: LLM instance used for routing.

    Returns:
        Parsed routing decision.
    """
    parser = PydanticOutputParser(pydantic_object=RouteDecision)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a router for a gaming advisor chat. "
                "Choose the correct intent class: "
                "owned_games (user names games they own), "
                "recommendation (user asks for recommendations), "
                "profile_update (user wants to update their profile), "
                "library_list (user wants to list their library), "
                "library_query (user asks about a specific game in their library), "
                "unknown (unclear). "
                "If unclear, set intent='unknown' and ask a short follow-up question.\n\n"
                "Examples:\n"
                "- \"I own Hades and Hollow Knight.\" -> owned_games\n"
                "- \"I have 20 hours in Elden Ring.\" -> owned_games\n"
                "- \"Recommend a fast-paced racing game.\" -> recommendation\n"
                "- \"I'm looking for a cozy farming sim.\" -> recommendation\n"
                "- \"Change my platform to PC.\" -> profile_update\n"
                "- \"Update my age to 25.\" -> profile_update\n"
                "- \"Remove Hades from my library.\" -> profile_update\n"
                "- \"Delete Elden Ring from my games.\" -> profile_update\n"
                "- \"Update my rating for Hades to 9.\" -> profile_update\n"
                "- \"Set my playtime for Elden Ring to 50 hours.\" -> profile_update\n"
                "- \"What's my personal rating for Cyberpunk 2077?\" -> library_query\n"
                "- \"How many hours do I have in Hades?\" -> library_query\n"
                "- \"Do I own Hollow Knight?\" -> library_query\n"
                "- \"Show me my library.\" -> library_list\n"
                "- \"List my games.\" -> library_list\n",
            ),
            ("human", "{user_text}\n\n{format_instructions}"),
        ]
    )
    chain = prompt | llm | parser
    return chain.invoke(
        {
            "user_text": user_text,
            "format_instructions": parser.get_format_instructions(),
        }
    )


def parse_owned_games(user_text: str, llm: Any) -> OwnedGamesRequest:
    """Parse owned games from user text.

    Args:
        user_text: Raw user input containing game mentions.
        llm: LLM instance used for parsing.

    Returns:
        Structured owned games request.
    """
    parser = PydanticOutputParser(pydantic_object=OwnedGamesRequest)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Extract the mentioned games as JSON. "
                "Return a list with title and optional platform, status, rating, playtime_hours.",
            ),
            ("human", "{user_text}\n\n{format_instructions}"),
        ]
    )
    chain = prompt | llm | parser
    return chain.invoke(
        {
            "user_text": user_text,
            "format_instructions": parser.get_format_instructions(),
        }
    )


def parse_profile_update(user_text: str, llm: Any) -> ProfileUpdateRequest:
    """Parse profile update requests from user text.

    Args:
        user_text: Raw user input containing profile updates.
        llm: LLM instance used for parsing.

    Returns:
        Structured profile update request.
    """
    parser = PydanticOutputParser(pydantic_object=ProfileUpdateRequest)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Extract profile updates as JSON. "
                "User profile fields: name, email, language, age, platform. "
                "For library updates, return a list with title and action. "
                "Use action='remove' when the user wants to delete a game. "
                "Otherwise use action='update' and include rating/playtime_hours/status when provided. "
                "If a field is not mentioned, leave it null. "
                "If no updates are mentioned, return empty values.",
            ),
            ("human", "{user_text}\n\n{format_instructions}"),
        ]
    )
    chain = prompt | llm | parser
    return chain.invoke(
        {
            "user_text": user_text,
            "format_instructions": parser.get_format_instructions(),
        }
    )


def parse_library_query(user_text: str, llm: Any) -> LibraryQuery:
    """Parse library query requests from user text.

    Args:
        user_text: Raw user input containing a library question.
        llm: LLM instance used for parsing.

    Returns:
        Structured library query.
    """
    parser = PydanticOutputParser(pydantic_object=LibraryQuery)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Extract the game title and which info is requested. "
                "Possible fields: rating, playtime, status. "
                "If the user asks about hours or playtime, include playtime. "
                "If the user asks about rating, include rating. "
                "If the user asks whether they own a game or its state, include status. "
                "If unclear, return an empty fields list.",
            ),
            ("human", "{user_text}\n\n{format_instructions}"),
        ]
    )
    chain = prompt | llm | parser
    return chain.invoke(
        {
            "user_text": user_text,
            "format_instructions": parser.get_format_instructions(),
        }
    )
