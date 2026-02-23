"""Database helpers for persistence and CRUD operations."""

import os
import logging
from dotenv import load_dotenv
from pydantic import ValidationError
from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ArgumentError, SQLAlchemyError, IntegrityError
from database.db import Games, User
from database.schemas import GameIn, UserCreate, UserUpdate

logger = logging.getLogger(__name__)

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if DB_URL is None:
    raise ValueError("DATABASE_URL Umgebungsvariable ist nicht gesetzt.")

try:
    engine = create_engine(DB_URL, echo=True)
    with engine.connect() as conn:
        logger.info("Database connection established successfully.")
except OperationalError as e:
    logger.error("Error connecting to database: %s", e)
    engine = None
except (ArgumentError, SQLAlchemyError) as e:
    logger.error("Unexpected error creating database engine: %s", e)
    engine = None


def create_tables():
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
    """Store normalized Steam game details in the ``Games`` table.

    Args:
        app_details (dict): Dictionary containing normalized game fields.

    Returns:
        bool: ``True`` on successful save, otherwise ``False``.
    """
    if engine is None:
        logger.error("Engine could not be initialized.")
        return False

    try:
        game_in = GameIn.model_validate(app_details)

        game_kwargs = {
            "game_name": game_in.name,
            "description": game_in.description,
            "genres": game_in.genres,
            "usk": game_in.usk,
            "price": game_in.price,
            "platforms": game_in.platforms,
            "min_requirements": game_in.minimum_requirements,
            "recommended_requirements": game_in.recommended_requirements,
        }

        if hasattr(Games, "release_date"):
            game_kwargs["release_date"] = game_in.release_date
        if hasattr(Games, "steam_appid"):
            game_kwargs["steam_appid"] = game_in.appid

        game = Games(**game_kwargs)

        with Session(engine) as session:
            session.add(game)
            session.commit()
            logger.info("Game '%s' saved to database successfully.", game.game_name)
            return True

    except (OperationalError, SQLAlchemyError) as e:
        logger.error("Error saving game to database: %s", e)
        return False
    except ValidationError as e:
        logger.error("Validation failed for game payload: %s", e)
        return False


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


def reset_table(engine, table_name: str):
    """Truncate a table and reset its identity counter."""
    with engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")
        )

if __name__ == "__main__":
    reset_table(engine, "games")
