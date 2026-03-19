"""Service layer for chat orchestration logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from sqlmodel import Session, select

from gaming_advisor.db.engine import engine
from gaming_advisor.db.models import Games, UserGames
from gaming_advisor.llm.routing import (
    OwnedGame,
    OwnedGamesRequest,
    parse_owned_games,
    route_user_text,
)
from gaming_advisor.recommender import parse_recommendation_request, recommend_for_user_request
from gaming_advisor.schemas.recommendations import RecommendationResponse

GameResolver = Callable[[Session, str], Games | None]


@dataclass(slots=True)
class ChatResult:
    """Result payload for a processed chat message.

    Attributes:
        kind: The outcome type for the message.
        message: Optional message for the caller to display.
        saved_titles: Titles persisted during owned-game updates.
        recommendations: Recommendation response payload.
    """

    kind: Literal["clarify", "owned_games_saved", "recommendations", "error", "unknown"]
    message: str | None = None
    saved_titles: list[str] | None = None
    recommendations: RecommendationResponse | None = None


def handle_user_message(
    user_id: int,
    user_text: str,
    llm: Any,
    resolve_game: GameResolver,
    *,
    top_k: int = 5,
) -> ChatResult:
    """Route, parse, and fulfill a user message.

    Args:
        user_id: ID of the active user.
        user_text: Raw user message.
        llm: LLM instance used for routing and parsing.
        resolve_game: Callback that resolves a title to a game record.
        top_k: Maximum number of recommendations to return.

    Returns:
        A ChatResult describing how to respond.
    """
    decision = route_user_text(user_text, llm)
    intent = decision.intent
    needs_clarification = intent == "unknown" or decision.confidence < 0.6

    if needs_clarification:
        return ChatResult(
            kind="clarify",
            message=decision.followup_question or "Do you mean recommendations or owned games?",
        )

    if intent == "owned_games":
        try:
            owned_request = parse_owned_games(user_text, llm)
        except Exception:
            return ChatResult(
                kind="error",
                message="Couldn't parse the games. Please list them clearly.",
            )

        if not owned_request.games:
            return ChatResult(
                kind="error",
                message="No games recognized. Please try again.",
            )

        saved_titles = _save_owned_games(user_id, owned_request, resolve_game)
        return ChatResult(kind="owned_games_saved", saved_titles=saved_titles)

    if intent == "recommendation":
        request = parse_recommendation_request(user_text, llm)
        response = recommend_for_user_request(user_id, request, top_k=top_k)
        return ChatResult(kind="recommendations", recommendations=response)

    return ChatResult(
        kind="unknown",
        message=(
            "I'm not sure. You can say for example: "
            "'I own Hades and Hollow Knight' or 'Recommend an RPG'."
        ),
    )


def _save_owned_games(
    user_id: int,
    owned_request: OwnedGamesRequest,
    resolve_game: GameResolver,
) -> list[str]:
    if engine is None:
        return []

    saved_titles: list[str] = []
    with Session(engine) as session:
        for owned_game in owned_request.games:
            game = resolve_game(session, owned_game.title)
            if game is None:
                continue
            if _upsert_user_game(session, user_id, game, owned_game):
                saved_titles.append(game.game_name)
        session.commit()

    return saved_titles


def _upsert_user_game(
    session: Session,
    user_id: int,
    game: Games,
    owned_game: OwnedGame,
) -> bool:
    if game.id is None:
        return False
    existing = session.exec(
        select(UserGames).where(
            UserGames.user_id == user_id,
            UserGames.game_id == game.id,
        )
    ).first()

    if existing:
        changed = False
        if owned_game.status:
            existing.status = owned_game.status
            changed = True
        if owned_game.rating is not None:
            existing.rating = owned_game.rating
            changed = True
        if owned_game.playtime_hours is not None:
            existing.playtime_hours = owned_game.playtime_hours
            changed = True
        return changed

    session.add(
        UserGames(
            user_id=user_id,
            game_id=game.id,
            status=owned_game.status or "owned",
            rating=owned_game.rating,
            playtime_hours=owned_game.playtime_hours or 0.0,
        )
    )
    return True
