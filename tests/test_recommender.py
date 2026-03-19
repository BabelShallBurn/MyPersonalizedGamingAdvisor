"""Unit tests for the game recommendation system.

Covers all branches in the recommender scorer including scoring, filtering,
normalization, and edge cases.
"""

from __future__ import annotations

import os
from collections import Counter
from decimal import Decimal

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite://")

from gaming_advisor.db.models import Games, User, UserGames
from gaming_advisor.recommender import scorer as recommender


EXPECTED_KEYS = {
    "game_id",
    "steam_appid",
    "name",
    "total_score",
    "genre_score",
    "preferred_genre_score",
    "description_score",
    "query_description_score",
    "recommendations_score",
    "recommendations",
    "genres",
}
SCORE_KEYS = {
    "total_score",
    "genre_score",
    "preferred_genre_score",
    "description_score",
    "query_description_score",
    "recommendations_score",
}


def _create_test_engine():
    """Create an in-memory SQLite engine for testing."""
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _add_user(session: Session, user_id: int = 1) -> None:
    """Add a test user to the database."""
    session.add(
        User(
            id=user_id,
            name="Test User",
            email=f"user{user_id}@example.com",
            language="de",
            age=30,
            platform="pc",
        )
    )


def _add_game(
    session: Session,
    *,
    game_id: int,
    appid: int,
    name: str,
    genres: str,
    description: str,
    recommendations: int,
) -> None:
    """Add a test game to the database."""
    session.add(
        Games(
            id=game_id,
            steam_appid=appid,
            game_name=name,
            release_date="2025-01-01",
            recommendations=recommendations,
            description=description,
            genres=genres,
            usk=12,
            price=Decimal("9.99"),
            platforms="pc",
        )
    )


def _add_owned(session: Session, user_id: int, game_id: int) -> None:
    session.add(UserGames(user_id=user_id, game_id=game_id, status="owned"))


def _seed_default_data(session: Session) -> None:
    """Seed a library with two owned games and three candidates."""
    _add_user(session, user_id=1)

    _add_game(
        session,
        game_id=1,
        appid=101,
        name="Owned RPG Action",
        genres="RPG, Action",
        description="fantasy adventure world quests combat",
        recommendations=300,
    )
    _add_game(
        session,
        game_id=2,
        appid=102,
        name="Owned RPG Strategy",
        genres="RPG, Strategy",
        description="turn based strategy fantasy kingdom quests",
        recommendations=250,
    )
    _add_game(
        session,
        game_id=3,
        appid=103,
        name="Candidate RPG Adventure",
        genres="RPG, Adventure",
        description="fantasy adventure quests in open world",
        recommendations=500,
    )
    _add_game(
        session,
        game_id=4,
        appid=104,
        name="Candidate Racing",
        genres="Racing, Sports",
        description="fast cars racing tracks championship speed",
        recommendations=1000,
    )
    _add_game(
        session,
        game_id=5,
        appid=105,
        name="Candidate RPG Strategy",
        genres="RPG, Strategy",
        description="fantasy strategy kingdom management quests",
        recommendations=200,
    )

    _add_owned(session, user_id=1, game_id=1)
    _add_owned(session, user_id=1, game_id=2)
    session.commit()


def _seed_all_owned(session: Session) -> None:
    """Seed data where the user owns every game (no candidates)."""
    _add_user(session, user_id=10)
    _add_game(
        session,
        game_id=10,
        appid=110,
        name="Only Game A",
        genres="RPG",
        description="shared term alpha",
        recommendations=10,
    )
    _add_game(
        session,
        game_id=11,
        appid=111,
        name="Only Game B",
        genres="Action",
        description="shared term beta",
        recommendations=20,
    )
    _add_owned(session, user_id=10, game_id=10)
    _add_owned(session, user_id=10, game_id=11)
    session.commit()


def _seed_no_genre_library(session: Session) -> None:
    """Seed data where library games have no genres, but candidates do."""
    _add_user(session, user_id=20)
    _add_game(
        session,
        game_id=20,
        appid=120,
        name="Owned No Genre A",
        genres="",
        description="shared term alpha",
        recommendations=10,
    )
    _add_game(
        session,
        game_id=21,
        appid=121,
        name="Owned No Genre B",
        genres="",
        description="shared term beta",
        recommendations=20,
    )
    _add_game(
        session,
        game_id=22,
        appid=122,
        name="Candidate With Genre",
        genres="RPG",
        description="shared term gamma",
        recommendations=30,
    )
    _add_owned(session, user_id=20, game_id=20)
    _add_owned(session, user_id=20, game_id=21)
    session.commit()


def _seed_candidate_no_genres(session: Session) -> None:
    """Seed data where a candidate has no genres but the library does."""
    _add_user(session, user_id=30)
    _add_game(
        session,
        game_id=30,
        appid=130,
        name="Owned With Genre",
        genres="RPG",
        description="shared term alpha",
        recommendations=10,
    )
    _add_game(
        session,
        game_id=31,
        appid=131,
        name="Owned With Genre 2",
        genres="Action",
        description="shared term beta",
        recommendations=20,
    )
    _add_game(
        session,
        game_id=32,
        appid=132,
        name="Candidate No Genre",
        genres="",
        description="shared term gamma",
        recommendations=30,
    )
    _add_owned(session, user_id=30, game_id=30)
    _add_owned(session, user_id=30, game_id=31)
    session.commit()


def _seed_zero_recommendations(session: Session) -> None:
    """Seed data where all candidates have zero recommendations."""
    _add_user(session, user_id=40)
    _add_game(
        session,
        game_id=40,
        appid=140,
        name="Owned A",
        genres="RPG",
        description="shared term alpha",
        recommendations=10,
    )
    _add_game(
        session,
        game_id=41,
        appid=141,
        name="Owned B",
        genres="Action",
        description="shared term beta",
        recommendations=20,
    )
    _add_game(
        session,
        game_id=42,
        appid=142,
        name="Candidate Zero Rec",
        genres="RPG",
        description="shared term gamma",
        recommendations=0,
    )
    _add_owned(session, user_id=40, game_id=40)
    _add_owned(session, user_id=40, game_id=41)
    session.commit()


@pytest.fixture
def patched_engine(monkeypatch):
    """Provide a fresh in-memory database for each test."""
    engine = _create_test_engine()
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(recommender, "engine", engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


def test_parse_genres_normalizes_and_filters() -> None:
    assert recommender._parse_genres(" RPG, Action ,,STRATEGY ") == [
        "rpg",
        "action",
        "strategy",
    ]
    assert recommender._parse_genres("") == []
    assert recommender._parse_genres(None) == []


def test_normalize_counter_empty_and_non_positive_totals() -> None:
    assert recommender._normalize_counter(Counter()) == {}
    assert recommender._normalize_counter(Counter({"rpg": -1, "action": 1})) == {}


def test_normalize_counter_positive_values() -> None:
    normalized = recommender._normalize_counter(Counter({"rpg": 2, "action": 1}))
    assert normalized["rpg"] == pytest.approx(2 / 3)
    assert normalized["action"] == pytest.approx(1 / 3)


def test_normalize_genre_preferences_empty_inputs() -> None:
    assert recommender._normalize_genre_preferences(None) == {}
    assert recommender._normalize_genre_preferences([]) == {}
    assert recommender._normalize_genre_preferences(["  ", ""]) == {}


def test_normalize_genre_preferences_deduplicates_case_and_whitespace() -> None:
    weights = recommender._normalize_genre_preferences([" RPG", "rpg", "Action "])
    assert weights["rpg"] == pytest.approx(2 / 3)
    assert weights["action"] == pytest.approx(1 / 3)


def test_recommend_games_returns_empty_when_engine_is_none(monkeypatch) -> None:
    monkeypatch.setattr(recommender, "engine", None)
    assert recommender.recommend_games_for_user(user_id=1) == []


def test_recommend_games_returns_empty_without_library(patched_engine) -> None:
    with Session(patched_engine) as session:
        _add_user(session, user_id=77)
        session.commit()
    assert recommender.recommend_games_for_user(user_id=77) == []


def test_recommend_games_returns_empty_without_candidates(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_all_owned(session)
    assert recommender.recommend_games_for_user(user_id=10) == []


def test_recommend_games_respects_top_k_and_excludes_owned(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(user_id=1, top_k=2)

    assert len(recs) == 2
    owned_ids = {1, 2}
    assert all(rec["game_id"] not in owned_ids for rec in recs)


def test_recommend_games_are_sorted_by_total_score_desc(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(user_id=1, top_k=3)
    scores = [rec["total_score"] for rec in recs]

    assert scores == sorted(scores, reverse=True)


def test_recommend_games_include_keys_and_rounding(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(user_id=1, top_k=3)
    assert recs

    for rec in recs:
        assert EXPECTED_KEYS.issubset(rec.keys())
        for key in SCORE_KEYS:
            assert rec[key] == round(rec[key], 6)
        assert rec["query_description_score"] == 0.0


def test_preferred_genres_affect_scoring_default_weights(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(
        user_id=1,
        top_k=3,
        preferred_genres=["rpg"],
    )

    target = next(rec for rec in recs if rec["name"] == "Candidate RPG Adventure")
    assert target["preferred_genre_score"] > 0
    assert all(rec["query_description_score"] == 0.0 for rec in recs)


def test_query_text_affects_scoring_default_weights(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(
        user_id=1,
        top_k=3,
        query_text="fast racing cars speed",
    )

    racing = next(rec for rec in recs if rec["name"] == "Candidate Racing")
    assert racing["query_description_score"] > 0
    assert racing["query_description_score"] == max(
        rec["query_description_score"] for rec in recs
    )


def test_preferred_and_query_text_both_influence(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(
        user_id=1,
        top_k=3,
        preferred_genres=["strategy"],
        query_text="strategy kingdom management",
    )

    target = next(rec for rec in recs if rec["name"] == "Candidate RPG Strategy")
    assert target["preferred_genre_score"] > 0
    assert target["query_description_score"] > 0


def test_preferred_genres_can_dominate_with_custom_weights(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(
        user_id=1,
        top_k=3,
        preferred_genres=["racing"],
        weights={
            "genre": 0.0,
            "preferred_genres": 1.0,
            "description": 0.0,
            "recommendations": 0.0,
        },
    )

    assert recs[0]["name"] == "Candidate Racing"
    assert recs[0]["preferred_genre_score"] > 0


def test_query_text_can_dominate_with_custom_weights(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(
        user_id=1,
        top_k=3,
        query_text="fast racing cars speed",
        weights={
            "genre": 0.0,
            "preferred_genres": 0.0,
            "description": 0.0,
            "query_description": 1.0,
            "recommendations": 0.0,
        },
    )

    assert recs[0]["name"] == "Candidate Racing"
    assert recs[0]["query_description_score"] > 0


def test_whitespace_query_text_is_ignored(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(user_id=1, top_k=3, query_text="   ")

    assert all(rec["query_description_score"] == 0.0 for rec in recs)


def test_negative_top_k_returns_empty_list(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(user_id=1, top_k=-5)

    assert recs == []


def test_zero_weight_sum_returns_empty(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(
        user_id=1,
        weights={"genre": 0.0, "description": 0.0, "recommendations": 0.0},
    )

    assert recs == []


def test_all_negative_weights_return_empty(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_default_data(session)

    recs = recommender.recommend_games_for_user(
        user_id=1,
        weights={"genre": -1.0, "description": -2.0, "recommendations": -3.0},
    )

    assert recs == []


def test_library_with_no_genres_yields_zero_genre_scores(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_no_genre_library(session)

    recs = recommender.recommend_games_for_user(user_id=20, top_k=3)

    assert recs
    assert all(rec["genre_score"] == 0.0 for rec in recs)


def test_candidate_with_no_genres_yields_zero_genre_scores(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_candidate_no_genres(session)

    recs = recommender.recommend_games_for_user(user_id=30, top_k=3)

    target = next(rec for rec in recs if rec["name"] == "Candidate No Genre")
    assert target["genre_score"] == 0.0
    assert target["preferred_genre_score"] == 0.0


def test_zero_recommendations_yield_zero_recommendation_score(patched_engine) -> None:
    with Session(patched_engine) as session:
        _seed_zero_recommendations(session)

    recs = recommender.recommend_games_for_user(user_id=40, top_k=3)

    target = next(rec for rec in recs if rec["name"] == "Candidate Zero Rec")
    assert target["recommendations_score"] == 0.0


def test_small_text_corpus_raises_value_error_due_to_min_df_2(patched_engine) -> None:
    with Session(patched_engine) as session:
        _add_user(session, user_id=9)
        _add_game(
            session,
            game_id=11,
            appid=201,
            name="Owned Tiny",
            genres="RPG",
            description="alpha",
            recommendations=10,
        )
        _add_game(
            session,
            game_id=12,
            appid=202,
            name="Candidate Tiny",
            genres="RPG",
            description="beta",
            recommendations=20,
        )
        _add_owned(session, user_id=9, game_id=11)
        session.commit()

    with pytest.raises(ValueError):
        recommender.recommend_games_for_user(user_id=9)
