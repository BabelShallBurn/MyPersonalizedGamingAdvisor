import os
import logging
from dotenv import load_dotenv
from sqlmodel import create_engine, SQLModel
from sqlalchemy.exc import OperationalError, ArgumentError, SQLAlchemyError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if DB_URL is None:
    raise ValueError("DATABASE_URL Umgebungsvariable ist nicht gesetzt.")

# Create engine for PostgreSQL
try:
    engine = create_engine(DB_URL, echo=True)
    # Test the connection
    with engine.connect() as conn:
        logger.info("Datenbankverbindung erfolgreich hergestellt.")
except OperationalError as e:
    logger.error("Fehler beim Verbinden zur Datenbank: %s", e)
    engine = None
except (ArgumentError, SQLAlchemyError) as e:
    logger.error("Unerwarteter Fehler beim Erstellen der Datenbank-Engine: %s", e)
    engine = None

# Create tables
def create_tables():
    """erstelle Tabellen, die in db.py definiert sind
    """
    if engine is not None:
        try:
            SQLModel.metadata.create_all(engine)
            logger.info("Tabellen erfolgreich erstellt.")
        except (OperationalError, SQLAlchemyError) as e:
            logger.error("Fehler beim Erstellen der Tabellen: %s", e)
    else:
        logger.error("Engine konnte nicht erstellt werden, Tabellen können nicht erstellt werden.")

if __name__ == "__main__":
    create_tables()
