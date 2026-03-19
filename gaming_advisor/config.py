"""Centralized configuration sourced from environment variables."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


DATABASE_URL = os.getenv("DATABASE_URL")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_BATCH_SIZE = _get_int("EMBEDDING_BATCH_SIZE", 128)
EMBEDDING_MAX_TOKENS = _get_int("EMBEDDING_MAX_TOKENS", 8000)
RERANK_TOP_N = _get_int("RERANK_TOP_N", 200)
