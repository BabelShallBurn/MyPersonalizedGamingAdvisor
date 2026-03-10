"""Simple recommendation scoring based on user library and optional preferences.

The scorer combines up to five signals:
1) genre affinity from a user-genre histogram
2) description similarity (TF-IDF cosine to a user text profile)
3) recommendation volume from the game catalog (log-normalized)
4) optional preferred-genre affinity passed at request time
5) optional query-description similarity from free-form user input
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlmodel import Session, select

from database.data_handling import engine
from database.db import Games, UserGames

def _parse_genres(raw_genres: str | None) -> list[str]:
    """Split CSV-like genres into normalized tokens."""
    if not raw_genres:
        return []
    return [genre.strip().lower() for genre in raw_genres.split(",") if genre.strip()]


def _normalize_counter(values: Counter[str]) -> dict[str, float]:
    """Normalize counter values to sum to 1.0."""
    total = sum(values.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in values.items()}

def _normalize_genre_preferences(preferred_genres: list[str] | None) -> dict[str, float]:
    """Normalize user-provided preferred genres to weights."""
    if not preferred_genres:
        return {}
    normalized = [genre.strip().lower() for genre in preferred_genres if genre.strip()]
    if not normalized:
        return {}
    return _normalize_counter(Counter(normalized))


def recommend_games_for_user(
    user_id: int,
    *,
    top_k: int = 10,
    preferred_genres: list[str] | None = None,
    query_text: str | None = None,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return top-k recommendations with explainable score components.

    Args:
        user_id: The user to score recommendations for.
        top_k: Number of recommendations to return.
        preferred_genres: Optional user-provided preferred genres.
        query_text: Optional free-form query text from the user.
        weights: Optional weights for signals. Keys:
            - genre
            - preferred_genres
            - description
            - query_description
            - recommendations
    """
    if engine is None:
        return []

    preferred_genre_weights = _normalize_genre_preferences(preferred_genres)
    include_preferred_genres = bool(preferred_genre_weights)
    normalized_query_text = (query_text or "").strip()
    include_query_description = bool(normalized_query_text)

    score_weights = {
        "genre": 0.40,
        "description": 0.35,
        "recommendations": 0.25,
    }
    if include_preferred_genres:
        score_weights["preferred_genres"] = 0.20
        score_weights["genre"] = 0.30
        score_weights["description"] = 0.30
        score_weights["recommendations"] = 0.20
    if include_query_description:
        score_weights["query_description"] = 0.25
        if include_preferred_genres:
            score_weights["genre"] = 0.25
            score_weights["preferred_genres"] = 0.15
            score_weights["description"] = 0.20
            score_weights["recommendations"] = 0.15
        else:
            score_weights["genre"] = 0.30
            score_weights["description"] = 0.25
            score_weights["recommendations"] = 0.20

    if weights:
        score_weights.update(weights)
    if not include_preferred_genres:
        score_weights.pop("preferred_genres", None)
    if not include_query_description:
        score_weights.pop("query_description", None)
    weight_sum = sum(max(value, 0.0) for value in score_weights.values())
    if weight_sum <= 0:
        return []
    score_weights = {
        key: max(value, 0.0) / weight_sum for key, value in score_weights.items()
    }

    with Session(engine) as session:
        library_rows = session.exec(
            select(UserGames, Games)
            .join(Games, UserGames.game_id == Games.id)
            .where(UserGames.user_id == user_id)
        ).all()
        all_games = session.exec(select(Games)).all()

    if not library_rows:
        return []

    owned_game_ids = {game.id for _, game in library_rows if game.id is not None}
    candidates = [game for game in all_games if game.id not in owned_game_ids]
    if not candidates:
        return []

    # 1) Genre profile (histogram -> normalized weights)
    genre_histogram: Counter[str] = Counter()
    for _, game in library_rows:
        genre_histogram.update(_parse_genres(game.genres))
    genre_weights = _normalize_counter(genre_histogram)

    # 2) Text profile from library descriptions (TF-IDF centroid)
    library_docs = [game.description or "" for _, game in library_rows]
    candidate_docs = [game.description or "" for game in candidates]
    all_docs = library_docs + candidate_docs

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2)
    tfidf_matrix = vectorizer.fit_transform(all_docs)
    library_matrix = tfidf_matrix[: len(library_docs)]
    candidate_matrix = tfidf_matrix[len(library_docs):]

    # sklearn>=1.6 rejects np.matrix; convert sparse mean result to ndarray.
    text_profile = np.asarray(library_matrix.mean(axis=0))
    description_scores = cosine_similarity(candidate_matrix, text_profile).ravel().tolist()

    # 3) Query text similarity to candidate descriptions
    if include_query_description:
        query_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        query_matrix = query_vectorizer.fit_transform(candidate_docs + [normalized_query_text])
        query_profile = query_matrix[-1]
        query_candidates_matrix = query_matrix[:-1]
        query_description_scores = (
            cosine_similarity(query_candidates_matrix, query_profile).ravel().tolist()
        )
    else:
        query_description_scores = [0.0] * len(candidates)

    # 4) Recommendation volume normalization
    max_recommendations = max(max(game.recommendations, 0) for game in candidates)
    max_log_recommendations = math.log1p(max_recommendations) if max_recommendations > 0 else 1.0

    scored_games: list[dict[str, Any]] = []
    for game, description_score, query_description_score in zip(
        candidates, description_scores, query_description_scores
    ):
        genres = _parse_genres(game.genres)

        if genres and genre_weights:
            genre_score = sum(genre_weights.get(genre, 0.0) for genre in genres) / len(genres)
        else:
            genre_score = 0.0

        if genres and preferred_genre_weights:
            preferred_genre_score = (
                sum(preferred_genre_weights.get(genre, 0.0) for genre in genres) / len(genres)
            )
        else:
            preferred_genre_score = 0.0

        recommendations_score = (
            math.log1p(max(game.recommendations, 0)) / max_log_recommendations
            if max_log_recommendations > 0
            else 0.0
        )

        total_score = (
            score_weights["genre"] * genre_score
            + score_weights.get("preferred_genres", 0.0) * preferred_genre_score
            + score_weights["description"] * description_score
            + score_weights.get("query_description", 0.0) * query_description_score
            + score_weights["recommendations"] * recommendations_score
        )

        scored_games.append(
            {
                "game_id": game.id,
                "steam_appid": game.steam_appid,
                "name": game.game_name,
                "total_score": round(total_score, 6),
                "genre_score": round(genre_score, 6),
                "preferred_genre_score": round(preferred_genre_score, 6),
                "description_score": round(description_score, 6),
                "query_description_score": round(query_description_score, 6),
                "recommendations_score": round(recommendations_score, 6),
                "recommendations": game.recommendations,
                "genres": game.genres,
            }
        )

    scored_games.sort(key=lambda item: item["total_score"], reverse=True)
    return scored_games[: max(top_k, 0)]
