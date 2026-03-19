from __future__ import annotations

from sqlmodel import SQLModel

from gaming_advisor.db.engine import engine
from gaming_advisor.db.models import GameEmbedding


def main() -> None:
    if engine is None:
        print("No DB connection.")
        return
    SQLModel.metadata.create_all(engine, tables=[GameEmbedding.__table__])
    print("GameEmbedding table created.")


if __name__ == "__main__":
    main()
