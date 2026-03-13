"""Central logging configuration for the project."""

from __future__ import annotations

import logging
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent / "app.log"


def configure_logging() -> None:
    """Configure root logging to write to the project log file only."""
    root_logger = logging.getLogger()

    # Remove any existing handlers (including stream handlers) to avoid terminal output.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.INFO)

    # Route SQLAlchemy engine logs through the root logger into app.log.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
