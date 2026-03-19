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

    intent: Literal["owned_games", "recommendation", "profile_update", "library_list", "unknown"]
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
                "unknown (unclear). "
                "If unclear, set intent='unknown' and ask a short follow-up question.\n\n"
                "Examples:\n"
                "- \"I own Hades and Hollow Knight.\" -> owned_games\n"
                "- \"I have 20 hours in Elden Ring.\" -> owned_games\n"
                "- \"Recommend a fast-paced racing game.\" -> recommendation\n"
                "- \"I'm looking for a cozy farming sim.\" -> recommendation\n"
                "- \"Change my platform to PC.\" -> profile_update\n"
                "- \"Update my age to 25.\" -> profile_update\n"
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
