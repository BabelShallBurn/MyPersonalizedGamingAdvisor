import os
import logging
from dotenv import load_dotenv
from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ArgumentError, SQLAlchemyError
from database.db import Games

logger = logging.getLogger(__name__)

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if DB_URL is None:
    raise ValueError("DATABASE_URL Umgebungsvariable ist nicht gesetzt.")

try:
    engine = create_engine(DB_URL, echo=True)
    with engine.connect() as conn:
        logger.info("Datenbankverbindung erfolgreich hergestellt.")
except OperationalError as e:
    logger.error("Fehler beim Verbinden zur Datenbank: %s", e)
    engine = None
except (ArgumentError, SQLAlchemyError) as e:
    logger.error("Unerwarteter Fehler beim Erstellen der Datenbank-Engine: %s", e)
    engine = None


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


def save_game_details(app_details: dict) -> bool:
    """Speichert die von retrieve_app_details zurückgegebenen Daten in die Games-Tabelle.
    
    Args:
        app_details (dict): Dictionary mit Spieldaten von retrieve_app_details()
        
    Returns:
        bool: True wenn erfolgreich, False bei Fehler
    """
    if engine is None:
        logger.error("Engine konnte nicht initialisiert werden.")
        return False
    
    try:
        # Konvertiere die Daten aus dem API-Format ins DB-Format
        game = Games(
            game_name=app_details.get("name", "Unknown"),
            description=app_details.get("description", ""),
            genres=app_details.get("genres", ""),
            usk=int(app_details.get("usk", 0)) if app_details.get("usk") else 0,
            price=float(app_details.get("price", 0.0)) if app_details.get("price") else 0.0,
            platforms=app_details.get("platforms", ""),
            min_requirements=app_details.get("minimum_requirements", ""),
            recommended_requirements=app_details.get("recommended_requirements", "")
        )
        
        with Session(engine) as session:
            session.add(game)
            session.commit()
            logger.info(f"Spiel '{game.game_name}' erfolgreich in die Datenbank gespeichert.")
            return True
            
    except (OperationalError, SQLAlchemyError) as e:
        logger.error(f"Fehler beim Speichern des Spiels in die Datenbank: {e}")
        return False
    except (ValueError, TypeError) as e:
        logger.error(f"Fehler bei der Datenkonvertierung: {e}")
        return False


def reset_table(engine, table_name: str):
    with engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")
        )

if __name__ == "__main__":
    reset_table(engine, "games")
