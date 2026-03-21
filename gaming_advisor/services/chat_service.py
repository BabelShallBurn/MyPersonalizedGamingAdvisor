"""Service layer for chat orchestration logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from sqlmodel import Session, select

from gaming_advisor.db.engine import engine
from gaming_advisor.db.data_handling import get_user_library, update_user
from gaming_advisor.db.models import Games, UserGames
from gaming_advisor.llm.routing import (
    LibraryQuery,
    LibraryUpdate,
    OwnedGame,
    OwnedGamesRequest,
    ProfileUpdateRequest,
    parse_library_query,
    parse_owned_games,
    parse_profile_update,
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
        library_entries: Library entries with metadata.
    """

    kind: Literal[
        "clarify",
        "owned_games_saved",
        "profile_updated",
        "recommendations",
        "library_list",
        "library_query",
        "error",
        "unknown",
    ]
    message: str | None = None
    saved_titles: list[str] | None = None
    updated_fields: list[str] | None = None
    updated_games: list[str] | None = None
    removed_games: list[str] | None = None
    skipped_games: list[str] | None = None
    recommendations: RecommendationResponse | None = None
    library_entries: list[dict[str, Any]] | None = None
    library_query: dict[str, Any] | None = None


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

    if intent == "library_list":
        library_entries = get_user_library(user_id)
        return ChatResult(kind="library_list", library_entries=library_entries)

    if intent == "profile_update":
        try:
            profile_request = parse_profile_update(user_text, llm)
        except Exception:
            return ChatResult(
                kind="error",
                message="Couldn't parse the update request. Please be more specific.",
            )

        if not profile_request.has_updates():
            return ChatResult(
                kind="error",
                message="No updates recognized. Please specify what to change.",
            )

        result = _apply_profile_update(user_id, profile_request, resolve_game)
        return ChatResult(kind="profile_updated", **result)

    if intent == "library_query":
        try:
            library_query = parse_library_query(user_text, llm)
        except Exception:
            return ChatResult(
                kind="error",
                message="Couldn't parse the library question. Please be more specific.",
            )

        result = _handle_library_query(user_id, library_query, resolve_game)
        return ChatResult(kind="library_query", **result)

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


def _apply_profile_update(
    user_id: int,
    profile_request: ProfileUpdateRequest,
    resolve_game: GameResolver,
) -> dict[str, Any]:
    updated_fields: list[str] = []
    updated_games: list[str] = []
    removed_games: list[str] = []
    skipped_games: list[str] = []
    message: str | None = None

    user_updates = {
        key: value
        for key, value in {
            "name": profile_request.name,
            "email": profile_request.email,
            "language": profile_request.language,
            "age": profile_request.age,
            "platform": profile_request.platform,
        }.items()
        if value is not None
    }

    if user_updates:
        updated_user = update_user(user_id, **user_updates)
        if updated_user is None:
            message = "Profile update failed."
        else:
            updated_fields = list(user_updates.keys())

    if profile_request.library_updates:
        if engine is None:
            return {
                "message": "No database connection.",
                "updated_fields": updated_fields,
                "updated_games": updated_games,
                "removed_games": removed_games,
                "skipped_games": skipped_games,
            }
        with Session(engine) as session:
            for update in profile_request.library_updates:
                _apply_library_update(
                    session=session,
                    user_id=user_id,
                    update=update,
                    resolve_game=resolve_game,
                    updated_games=updated_games,
                    removed_games=removed_games,
                    skipped_games=skipped_games,
                )
            session.commit()

    return {
        "message": message,
        "updated_fields": updated_fields,
        "updated_games": updated_games,
        "removed_games": removed_games,
        "skipped_games": skipped_games,
    }


def _apply_library_update(
    *,
    session: Session,
    user_id: int,
    update: LibraryUpdate,
    resolve_game: GameResolver,
    updated_games: list[str],
    removed_games: list[str],
    skipped_games: list[str],
) -> None:
    game = resolve_game(session, update.title)
    if game is None or game.id is None:
        skipped_games.append(update.title)
        return

    relation = session.get(UserGames, (user_id, game.id))

    if update.action == "remove":
        if relation is None:
            skipped_games.append(game.game_name)
            return
        session.delete(relation)
        removed_games.append(game.game_name)
        return

    changed = False
    if relation is None:
        relation = UserGames(
            user_id=user_id,
            game_id=game.id,
            status=update.status or "owned",
            rating=update.rating,
            playtime_hours=update.playtime_hours or 0.0,
        )
        session.add(relation)
        updated_games.append(game.game_name)
        return

    if update.status:
        relation.status = update.status
        changed = True
    if update.rating is not None:
        relation.rating = update.rating
        changed = True
    if update.playtime_hours is not None:
        relation.playtime_hours = update.playtime_hours
        changed = True

    if changed:
        updated_games.append(game.game_name)
    else:
        skipped_games.append(game.game_name)


def _handle_library_query(
    user_id: int,
    library_query: LibraryQuery,
    resolve_game: GameResolver,
) -> dict[str, Any]:
    if engine is None:
        return {"message": "No database connection."}

    with Session(engine) as session:
        game = resolve_game(session, library_query.title)
        if game is None or game.id is None:
            return {"message": f"No match for '{library_query.title}' in your library."}

        relation = session.get(UserGames, (user_id, game.id))
        if relation is None:
            return {"message": f"{game.game_name} is not in your library."}

        fields = library_query.fields or ["status", "rating", "playtime"]
        response_parts: list[str] = []

        if "status" in fields:
            response_parts.append(f"Status: {relation.status}")
        if "rating" in fields:
            rating = relation.rating
            response_parts.append("Rating: not set" if rating is None else f"Rating: {rating}/10")
        if "playtime" in fields:
            response_parts.append(f"Playtime: {float(relation.playtime_hours):.1f}h")

        message = f"{game.game_name}: " + ", ".join(response_parts)
        return {
            "message": message,
            "library_query": {
                "name": game.game_name,
                "status": relation.status,
                "rating": relation.rating,
                "playtime_hours": float(relation.playtime_hours),
            },
        }
