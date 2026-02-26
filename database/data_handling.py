"""Database helpers for persistence and CRUD operations."""

from __future__ import annotations

import logging
import os
from collections import Counter
from decimal import Decimal

from dotenv import load_dotenv
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import ArgumentError, IntegrityError, OperationalError, SQLAlchemyError
from sqlmodel import SQLModel, Session, create_engine, select

from database.db import GameSystemRequirement, Games, User, UserGames
from database.schemas import GameIn, UserCreate, UserUpdate

logger = logging.getLogger(__name__)

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if DB_URL is None:
    raise ValueError("DATABASE_URL Umgebungsvariable ist nicht gesetzt.")

try:
    engine = create_engine(DB_URL, echo=True)
    with engine.connect():
        logger.info("Database connection established successfully.")
except OperationalError as e:
    logger.error("Error connecting to database: %s", e)
    engine = None
except (ArgumentError, SQLAlchemyError) as e:
    logger.error("Unexpected error creating database engine: %s", e)
    engine = None


def create_tables() -> None:
    """Create all tables registered in SQLModel metadata."""
    if engine is not None:
        try:
            SQLModel.metadata.create_all(engine)
            logger.info("Tables created successfully.")
        except (OperationalError, SQLAlchemyError) as e:
            logger.error("Error creating tables: %s", e)
    else:
        logger.error("Engine could not be created; tables cannot be created.")


def drop_all_tables() -> bool:
    """Drop all tables registered in SQLModel metadata."""
    if engine is None:
        logger.error("Engine could not be created; tables cannot be dropped.")
        return False
    try:
        SQLModel.metadata.drop_all(engine)
        logger.info("All tables dropped successfully.")
        return True
    except (OperationalError, SQLAlchemyError) as e:
        logger.error("Error dropping tables: %s", e)
        return False


def save_game_details(app_details: dict) -> bool:
    """Store normalized Steam game details in the ``Games`` table."""
    if engine is None:
        logger.error("Engine could not be initialized.")
        return False

    try:
        game_in = GameIn.model_validate(app_details)
        requirements_to_persist = game_in.system_requirements.copy()

        normalized_requirements = {}
        for req in requirements_to_persist:
            normalized_requirements[req.platform] = req

        game_kwargs = {
            "game_name": game_in.name,
            "description": game_in.description,
            "genres": game_in.genres,
            "usk": game_in.usk,
            "price": game_in.price,
            "platforms": game_in.platforms,
            "recommendations": game_in.recommendations,
        }

        if hasattr(Games, "release_date"):
            game_kwargs["release_date"] = game_in.release_date
        if hasattr(Games, "steam_appid"):
            game_kwargs["steam_appid"] = game_in.appid

        with Session(engine) as session:
            game = Games(**game_kwargs)
            session.add(game)
            session.flush()
            if game.id is None:
                raise ValueError("Game ID was not generated after flush.")
            game_id = game.id

            for req in normalized_requirements.values():
                requirement = GameSystemRequirement(
                    game_id=game_id,
                    platform=req.platform,
                    minimum=req.minimum,
                    recommended=req.recommended,
                )
                session.add(requirement)

            session.commit()
            logger.info("Game '%s' saved to database successfully.", game.game_name)
            return True

    except (OperationalError, SQLAlchemyError) as e:
        logger.error("Error saving game to database: %s", e)
        return False
    except ValidationError as e:
        logger.error("Validation failed for game payload: %s", e)
        return False


def add_game_to_user_library(
    user_id: int,
    game_id: int,
    *,
    status: str = "owned",
    rating: int | None = None,
    playtime_hours: Decimal | float | int = Decimal("0.0"),
) -> bool:
    """Add a game to a user's library, or update existing relation."""
    if engine is None:
        logger.error("Engine not available.")
        return False

    try:
        playtime = Decimal(str(playtime_hours))
        if playtime < 0:
            playtime = Decimal("0.0")
    except Exception:
        playtime = Decimal("0.0")

    try:
        with Session(engine) as session:
            user = session.get(User, user_id)
            game = session.get(Games, game_id)
            if user is None or game is None:
                return False

            relation = session.get(UserGames, (user_id, game_id))
            if relation is None:
                relation = UserGames(
                    user_id=user_id,
                    game_id=game_id,
                    status=status,
                    rating=rating,
                    playtime_hours=playtime,
                )
            else:
                relation.status = status
                relation.rating = rating
                relation.playtime_hours = playtime

            session.add(relation)
            session.commit()
            return True
    except (IntegrityError, OperationalError, SQLAlchemyError) as e:
        logger.error("Error adding game to user library: %s", e)
        return False


def remove_game_from_user_library(user_id: int, game_id: int) -> bool:
    """Remove a game from a user's library."""
    if engine is None:
        logger.error("Engine not available.")
        return False

    try:
        with Session(engine) as session:
            relation = session.get(UserGames, (user_id, game_id))
            if relation is None:
                return False
            session.delete(relation)
            session.commit()
            return True
    except SQLAlchemyError as e:
        logger.error("Error removing game from user library: %s", e)
        return False


def get_user_library(user_id: int) -> list[dict]:
    """Return a user's manually maintained library with game metadata."""
    if engine is None:
        logger.error("Engine not available.")
        return []

    with Session(engine) as session:
        query = (
            select(UserGames, Games)
            .join(Games, UserGames.game_id == Games.id)
            .where(UserGames.user_id == user_id)
        )
        rows = session.exec(query).all()

    return [
        {
            "user_id": relation.user_id,
            "game_id": game.id,
            "appid": game.steam_appid,
            "name": game.game_name,
            "genres": game.genres,
            "recommendations": game.recommendations,
            "status": relation.status,
            "rating": relation.rating,
            "playtime_hours": float(relation.playtime_hours),
        }
        for relation, game in rows
    ]


def get_top_library_genres(user_id: int, limit: int = 5) -> list[str]:
    """Derive dominant genres from a user's manually maintained library."""
    library_rows = get_user_library(user_id)
    genre_counts: Counter[str] = Counter()

    for row in library_rows:
        raw_genres = row.get("genres") or ""
        for genre in str(raw_genres).split(","):
            normalized = genre.strip().lower()
            if normalized:
                genre_counts[normalized] += 1

    return [genre for genre, _ in genre_counts.most_common(max(limit, 0))]


def create_user(name: str, email: str, language: str, age: int, platform: str) -> User | None:
    """Create a new user and return the persisted record."""
    if engine is None:
        logger.error("Engine not available.")
        return None
    try:
        validated = UserCreate.model_validate(
            {
                "name": name,
                "email": email,
                "language": language,
                "age": age,
                "platform": platform,
            }
        )
        user = User(**validated.model_dump())
        with Session(engine) as session:
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
    except ValidationError as e:
        logger.error("Validation failed for user creation payload: %s", e)
        return None
    except IntegrityError:
        logger.error("User with email '%s' already exists.", email)
        return None
    except SQLAlchemyError as e:
        logger.error("Error creating user: %s", e)
        return None


def update_user(user_id: int, **updates) -> User | None:
    """Update allowed user fields by user ID."""
    if engine is None:
        logger.error("Engine not available.")
        return None
    try:
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user is None:
                return None

            validated = UserUpdate.model_validate(updates)
            for key, value in validated.model_dump(exclude_none=True).items():
                setattr(user, key, value)

            session.add(user)
            session.commit()
            session.refresh(user)
            return user
    except ValidationError as e:
        logger.error("Validation failed for user update payload: %s", e)
        return None
    except IntegrityError as e:
        logger.error("Error updating user: email must be unique: %s", e)
        return None
    except SQLAlchemyError as e:
        logger.error("Error updating user: %s", e)
        return None


def delete_user(user_id: int) -> bool:
    """Delete a user by ID."""
    if engine is None:
        logger.error("Engine not available.")
        return False
    try:
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user is None:
                return False
            session.delete(user)
            session.commit()
            return True
    except SQLAlchemyError as e:
        logger.error("Error deleting user: %s", e)
        return False


def reset_table(engine, table_name: str) -> None:
    """Truncate a table and reset its identity counter."""
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))


if __name__ == "__main__":
    reset_table(engine, "games")
