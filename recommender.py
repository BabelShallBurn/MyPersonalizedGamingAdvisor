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
import os
from collections import Counter
from hashlib import sha256
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from openai import OpenAI
import tiktoken

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlmodel import Session, select

from database.data_handling import engine
from database.db import GameEmbedding, Games, UserGames
from schemas.recommendations import (
    RecommendationItem,
    RecommendationRequest,
    RecommendationResponse,
)

_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
_EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "128"))
_EMBEDDING_MAX_TOKENS = int(os.getenv("EMBEDDING_MAX_TOKENS", "8000"))
_RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "200"))

_QUERY_GENRE_KEYWORDS = {
    "platformer": {"platformer", "platform", "jump and run", "jump'n'run", "jump n run"},
    "racing": {"racing", "racer", "race", "motorsport", "car race", "motorcycle"},
    "shooter": {"shooter", "fps", "third-person shooter", "gunplay"},
    "open world": {"open world", "open-world"},
    "roguelike": {"roguelike", "roguelite", "rogue-lite"},
    "strategy": {"strategy", "tactics", "tactical"},
    "rpg": {"rpg", "role-playing", "roleplaying"},
    "simulation": {"simulation", "sim"},
    "adventure": {"adventure"},
    "action": {"action", "action-adventure"},
    "sports": {"sports", "sport"},
}


def _get_openai_client() -> OpenAI:
    return OpenAI()


def _truncate_texts(texts: list[str], max_tokens: int) -> list[str]:
    if not texts:
        return []
    if max_tokens <= 0:
        return ["" for _ in texts]
    encoder = tiktoken.get_encoding("cl100k_base")
    truncated: list[str] = []
    for text in texts:
        tokens = encoder.encode(text)
        if len(tokens) > max_tokens:
            tokens = tokens[:max_tokens]
            truncated.append(encoder.decode(tokens))
        else:
            truncated.append(text)
    return truncated


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    normalized = [text.strip() for text in texts]
    if any(text == "" for text in normalized):
        raise ValueError("Embedding input contains empty strings.")
    normalized = _truncate_texts(normalized, _EMBEDDING_MAX_TOKENS)
    client = _get_openai_client()
    embeddings: list[list[float]] = []
    for start in range(0, len(normalized), _EMBEDDING_BATCH_SIZE):
        batch = normalized[start : start + _EMBEDDING_BATCH_SIZE]
        response = client.embeddings.create(
            model=_EMBEDDING_MODEL,
            input=batch,
            encoding_format="float",
        )
        data_sorted = sorted(response.data, key=lambda item: item.index)
        embeddings.extend([item.embedding for item in data_sorted])
    return embeddings


def _description_hash(text: str, model: str) -> str:
    payload = f"{model}::{text}".encode("utf-8")
    return sha256(payload).hexdigest()


def _get_candidate_embeddings(
    session: Session,
    candidates: list[Games],
    embedding_dim: int,
) -> np.ndarray:
    candidate_ids = [game.id for game in candidates if game.id is not None]
    if not candidate_ids:
        return np.zeros((len(candidates), embedding_dim), dtype=float)

    existing_rows = session.exec(
        select(GameEmbedding)
        .where(GameEmbedding.game_id.in_(candidate_ids))
        .where(GameEmbedding.model == _EMBEDDING_MODEL)
    ).all()
    existing_map = {row.game_id: row for row in existing_rows if row.game_id is not None}

    to_embed: list[tuple[Games, str, str]] = []
    for game in candidates:
        if game.id is None:
            continue
        description = (game.description or "").strip()
        if not description:
            continue
        desc_hash = _description_hash(description, _EMBEDDING_MODEL)
        row = existing_map.get(game.id)
        if row is None or row.description_hash != desc_hash:
            to_embed.append((game, description, desc_hash))

    if to_embed:
        texts = [item[1] for item in to_embed]
        embeddings = _embed_texts(texts)
        for (game, _description, desc_hash), embedding in zip(to_embed, embeddings):
            row = existing_map.get(game.id)
            if row is None:
                row = GameEmbedding(
                    game_id=game.id,
                    model=_EMBEDDING_MODEL,
                    embedding=embedding,
                    embedding_dim=len(embedding),
                    description_hash=desc_hash,
                )
                session.add(row)
                existing_map[game.id] = row
            else:
                row.embedding = embedding
                row.embedding_dim = len(embedding)
                row.description_hash = desc_hash
        session.commit()

    embeddings_out: list[list[float]] = []
    for game in candidates:
        if game.id is None:
            embeddings_out.append([0.0] * embedding_dim)
            continue
        row = existing_map.get(game.id)
        if row is None:
            embeddings_out.append([0.0] * embedding_dim)
        else:
            embeddings_out.append(row.embedding)
    return np.asarray(embeddings_out, dtype=float)

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

def _infer_query_genre_filters(query_text: str) -> set[str]:
    text = query_text.lower()
    inferred: set[str] = set()
    for genre, keywords in _QUERY_GENRE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            inferred.add(genre)
    return inferred


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

    if include_query_description:
        inferred_genres = _infer_query_genre_filters(normalized_query_text)
        if inferred_genres:
            filtered = [
                game
                for game in candidates
                if inferred_genres.intersection(_parse_genres(game.genres))
            ]
            if filtered:
                candidates = filtered

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

    # 3) Query text similarity to candidate descriptions (embeddings)
    if include_query_description:
        query_embedding = _embed_texts([normalized_query_text])[0]
        with Session(engine) as session:
            candidate_embeddings = _get_candidate_embeddings(
                session,
                candidates,
                len(query_embedding),
            )
        query_vector = np.asarray(query_embedding, dtype=float).reshape(1, -1)
        if candidate_embeddings.ndim != 2 or candidate_embeddings.shape[1] != query_vector.shape[1]:
            query_description_scores = [0.0] * len(candidates)
        else:
            query_description_scores = (
                cosine_similarity(candidate_embeddings, query_vector).ravel().tolist()
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
    if include_query_description and scored_games:
        rerank_size = min(len(scored_games), max(_RERANK_TOP_N, top_k * 20))
        rerank_pool = scored_games[:rerank_size]
        rerank_pool.sort(
            key=lambda item: (
                item.get("query_description_score", 0.0),
                item.get("total_score", 0.0),
            ),
            reverse=True,
        )
        scored_games = rerank_pool + scored_games[rerank_size:]
    return scored_games[: max(top_k, 0)]


def parse_recommendation_request(user_text: str, llm: Any) -> RecommendationRequest:
    """Parse free-form user text into a structured recommendation request."""
    parser = PydanticOutputParser(pydantic_object=RecommendationRequest)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Extract the user preferences as JSON."),
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


def recommend_for_user_request(
    user_id: int, request: RecommendationRequest, *, top_k: int | None = None
) -> RecommendationResponse:
    """Run the recommender for a parsed request and shape the response payload."""
    k = top_k or request.top_k or 10
    scored = recommend_games_for_user(
        user_id,
        top_k=k,
        preferred_genres=request.preferred_genres,
        query_text=request.query_text,
        weights=request.weights,
    )

    game_ids = [row["game_id"] for row in scored if row.get("game_id") is not None]
    game_map: dict[int, Games] = {}
    if engine is not None and game_ids:
        with Session(engine) as session:
            games = session.exec(select(Games).where(Games.id.in_(game_ids))).all()
            game_map = {game.id: game for game in games if game.id is not None}

    recommendations: list[RecommendationItem] = []
    for row in scored:
        game = game_map.get(row["game_id"])
        price = getattr(game, "price", None)
        recommendations.append(
            RecommendationItem(
                title=row["name"],
                platform=getattr(game, "platforms", None) if game else None,
                price_eur=float(price) if price is not None else None,
                total_score=row.get("total_score"),
                match_reasons=[],
            )
        )

    return RecommendationResponse(recommendations=recommendations)
