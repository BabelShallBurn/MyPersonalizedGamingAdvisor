"""Database engine initialization and access."""

from __future__ import annotations

import logging

from sqlalchemy.exc import ArgumentError, OperationalError, SQLAlchemyError
from sqlmodel import create_engine

from gaming_advisor.config import DATABASE_URL
from gaming_advisor.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

if DATABASE_URL is None:
    raise ValueError("DATABASE_URL Umgebungsvariable ist nicht gesetzt.")

try:
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect():
        logger.info("Database connection established successfully.")
except OperationalError as e:
    logger.error("Error connecting to database: %s", e)
    engine = None
except (ArgumentError, SQLAlchemyError) as e:
    logger.error("Unexpected error creating database engine: %s", e)
    engine = None
