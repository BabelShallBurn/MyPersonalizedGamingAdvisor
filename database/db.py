"""Modul für Datenbankmodelle der Gaming-Advisor-Anwendung."""
from sqlmodel import Field, SQLModel



class User(SQLModel, table=True):
    """Repräsentiert einen Benutzer in der Datenbank mit persönlichen Informationen."""
    id: int | None = Field(default=None, primary_key=True)
    name: str
    mail: str
    language: str
    age: int
    platform: str

class Games(SQLModel, table=True):
    """Repräsentiert ein Spiel in der Datenbank mit Details wie Name, Beschreibung und Anforderungen."""
    id: int | None = Field(default=None, primary_key=True)
    game_name: str
    description: str
    genres: str
    usk: int
    price: float
    platforms: str
    min_requirements: str
    recommended_requirements: str | None

class UserGames(SQLModel, table=True):
    """Repräsentiert die Beziehung zwischen einem Benutzer und einem Spiel in der Datenbank."""
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    game_id: int = Field(foreign_key="games.id")
