"""Database models for the gaming advisor application."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """Represents a user with personal profile information."""

    __table_args__ = (
        CheckConstraint("age >= 0", name="ck_user_age_non_negative"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(120), nullable=False))
    email: str = Field(
        sa_column=Column(String(254), unique=True, nullable=False, index=True)
    )
    language: str = Field(sa_column=Column(String(50), nullable=False))
    age: int = Field(nullable=False)
    platform: str = Field(sa_column=Column(String(80), nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    )


class Games(SQLModel, table=True):
    """Represents a game with metadata and system requirements."""

    __table_args__ = (
        CheckConstraint("usk IN (0, 6, 12, 16, 18)", name="ck_games_usk_valid"),
        CheckConstraint("price >= 0", name="ck_games_price_non_negative"),
        CheckConstraint("recommendations >= 0", name="ck_games_recommendations_non_negative"),
    )

    id: int | None = Field(default=None, primary_key=True)
    steam_appid: int | None = Field(default=None, nullable=True, index=True)
    game_name: str = Field(sa_column=Column(String(200), nullable=False, index=True))
    release_date: str = Field(sa_column=Column(String(40), nullable=False, default=""))
    recommendations: int = Field(default=0, nullable=False)
    description: str = Field(default="", nullable=False)
    genres: str = Field(default="", nullable=False)
    usk: int = Field(default=0, nullable=False)
    price: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(10, 2), nullable=False),
    )
    platforms: str = Field(default="", nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    )


class UserGames(SQLModel, table=True):
    """Represents the relation between a user and a game."""

    __table_args__ = (
        CheckConstraint(
            "status IN ('owned', 'wishlist', 'playing', 'completed')",
            name="ck_user_games_status_valid",
        ),
        CheckConstraint(
            "rating IS NULL OR (rating >= 0 AND rating <= 10)",
            name="ck_user_games_rating_range",
        ),
        CheckConstraint(
            "playtime_hours >= 0",
            name="ck_user_games_playtime_non_negative",
        ),
    )

    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    game_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("games.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    status: str = Field(
        default="owned",
        sa_column=Column(String(20), nullable=False, server_default=text("'owned'")),
    )
    rating: int | None = Field(default=None, nullable=True)
    playtime_hours: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=Column(Numeric(8, 1), nullable=False, server_default=text("0")),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    )


class GameSystemRequirement(SQLModel, table=True):
    """Represents platform specific system requirements for a game."""

    __table_args__ = (
        UniqueConstraint("game_id", "platform", name="uq_game_system_requirements_game_platform"),
        CheckConstraint("platform IN ('pc', 'mac', 'linux')", name="ck_system_requirements_platform_valid"),
    )

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    platform: str = Field(sa_column=Column(String(10), nullable=False))
    minimum: str = Field(default="", nullable=False)
    recommended: str | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    )

