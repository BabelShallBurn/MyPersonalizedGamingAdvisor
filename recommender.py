"""Recommendation service built on persisted library and catalog data."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from database.data_handling import engine, get_top_library_genres
from database.db import Games, UserGames


@dataclass(slots=True)
class Recommendation:
    """Simple recommendation payload for API responses."""

    appid: int | None
    name: str
    score: float
    reason: str


def get_recommendations_for_user(
    user_id: int,
    limit: int = 10,
) -> list[Recommendation]:
    """Return recommendations based on dominant genres in user's library."""
    if engine is None or limit <= 0:
        return []

    top_genres = get_top_library_genres(user_id=user_id, limit=5)
    if not top_genres:
        return []

    with Session(engine) as session:
        owned_game_ids = set(
            session.exec(select(UserGames.game_id).where(UserGames.user_id == user_id)).all()
        )
        catalog_games = session.exec(select(Games)).all()

    recommendations: list[Recommendation] = []
    for game in catalog_games:
        if game.id is None or game.id in owned_game_ids:
            continue

        game_genres = {
            genre.strip().lower()
            for genre in str(game.genres or "").split(",")
            if genre.strip()
        }
        genre_matches = [genre for genre in top_genres if genre in game_genres]
        if not genre_matches:
            continue

        popularity = max(game.recommendations or 0, 0)
        score = float(len(genre_matches) * 100 + min(popularity, 50_000) / 1_000)
        reason = f"Genre-Match: {', '.join(genre_matches[:2])}"
        recommendations.append(
            Recommendation(
                appid=game.steam_appid,
                name=game.game_name,
                score=score,
                reason=reason,
            )
        )

    recommendations.sort(key=lambda rec: rec.score, reverse=True)
    return recommendations[:limit]
