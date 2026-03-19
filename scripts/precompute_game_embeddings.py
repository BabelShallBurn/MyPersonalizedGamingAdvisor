"""Precompute and cache game description embeddings in the database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gaming_advisor.db.engine import engine
from gaming_advisor.db.models import GameEmbedding, Games
from gaming_advisor.config import EMBEDDING_MODEL
from gaming_advisor.recommender.scorer import _description_hash, _embed_texts


def _upsert_embeddings(
    session: Session,
    games: list[Games],
    model: str,
) -> tuple[int, int]:
    """Upsert embeddings for a batch of games.

    Args:
        session: Active database session.
        games: Batch of games to process.
        model: Embedding model identifier.

    Returns:
        Tuple of (upserted_count, skipped_empty_count).
    """
    game_ids = [game.id for game in games if game.id is not None]
    if not game_ids:
        return 0, 0

    existing_rows = session.exec(
        select(GameEmbedding)
        .where(GameEmbedding.game_id.in_(game_ids))
        .where(GameEmbedding.model == model)
    ).all()
    existing_map = {row.game_id: row for row in existing_rows if row.game_id is not None}

    to_embed: list[tuple[Games, str, str]] = []
    skipped_empty = 0
    for game in games:
        if game.id is None:
            continue
        description = (game.description or "").strip()
        if not description:
            skipped_empty += 1
            continue
        desc_hash = _description_hash(description, model)
        row = existing_map.get(game.id)
        if row is None or row.description_hash != desc_hash:
            to_embed.append((game, description, desc_hash))

    if not to_embed:
        return 0, skipped_empty

    embeddings = _embed_texts([item[1] for item in to_embed])
    for (game, _description, desc_hash), embedding in zip(to_embed, embeddings):
        row = existing_map.get(game.id)
        if row is None:
            session.add(
                GameEmbedding(
                    game_id=game.id,
                    model=model,
                    embedding=embedding,
                    embedding_dim=len(embedding),
                    description_hash=desc_hash,
                )
            )
        else:
            row.embedding = embedding
            row.embedding_dim = len(embedding)
            row.description_hash = desc_hash

    session.commit()
    return len(to_embed), skipped_empty


def main() -> None:
    """Run the embedding precompute CLI."""
    parser = argparse.ArgumentParser(description="Precompute game embeddings.")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    if engine is None:
        print("No DB connection.")
        return

    model = EMBEDDING_MODEL
    batch_size = max(args.batch_size, 1)

    total_embedded = 0
    total_skipped = 0
    last_id = 0

    with Session(engine) as session:
        while True:
            games = session.exec(
                select(Games)
                .where(Games.id > last_id)
                .order_by(Games.id)
                .limit(batch_size)
            ).all()
            if not games:
                break
            if games[-1].id is not None:
                last_id = games[-1].id

            embedded, skipped = _upsert_embeddings(session, games, model)
            total_embedded += embedded
            total_skipped += skipped
            print(
                f"Batch upserted={embedded} skipped_empty={skipped} "
                f"last_id={last_id} total_upserted={total_embedded}"
            )

    print(
        "Done. "
        f"total_upserted={total_embedded} total_skipped_empty={total_skipped}"
    )


if __name__ == "__main__":
    main()
