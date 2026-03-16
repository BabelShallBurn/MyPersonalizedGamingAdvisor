from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database.data_handling import engine
from database.db import Games, User, UserGames
from recommender import parse_recommendation_request, recommend_for_user_request


OWNED_GAME_KEYWORDS = (
    "ich habe",
    "ich besitze",
    "gehoert mir",
    "in meiner sammlung",
    "ich spiele",
)
RECOMMENDATION_KEYWORDS = (
    "empfehle",
    "empfehlung",
    "suche",
    "kannst du",
    "recommend",
)


class OwnedGame(BaseModel):
    title: str = Field(min_length=1)
    platform: str | None = None
    status: Literal["owned", "wishlist", "playing", "completed"] | None = None
    rating: int | None = Field(default=None, ge=0, le=10)
    playtime_hours: float | None = Field(default=None, ge=0)


class OwnedGamesRequest(BaseModel):
    games: list[OwnedGame] = Field(default_factory=list)


def _get_user_by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(User.email == email)).first()


def _prompt_non_empty(prompt: str, *, default: str | None = None) -> str:
    while True:
        raw = input(prompt).strip()
        if raw:
            return raw
        if default is not None:
            return default
        print("Bitte gib einen Wert ein.")


def _prompt_int(prompt: str, *, default: int | None = None, min_value: int | None = None) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Bitte eine ganze Zahl eingeben.")
            continue
        if min_value is not None and value < min_value:
            print(f"Bitte eine Zahl >= {min_value} eingeben.")
            continue
        return value


def _prompt_email() -> str:
    default = os.getenv("TEST_USER_EMAIL")
    prompt = "Bitte gib deine E-Mail ein"
    if default:
        prompt += f" (Enter fuer {default})"
    prompt += ": "
    while True:
        raw = input(prompt).strip()
        if raw:
            return raw
        if default:
            return default
        print("E-Mail darf nicht leer sein.")


def _get_or_create_user(email: str) -> User | None:
    if engine is None:
        return None
    with Session(engine) as session:
        user = _get_user_by_email(session, email)
        if user is not None:
            return user

        print("Kein User gefunden. Bitte Profil anlegen.")
        name = _prompt_non_empty("Name: ")
        language = _prompt_non_empty("Sprache (z.B. de): ", default="de")
        age = _prompt_int("Alter: ", min_value=0)
        platform = _prompt_non_empty("Plattform (z.B. PC): ", default="PC")

        user = User(
            name=name,
            email=email,
            language=language,
            age=age,
            platform=platform,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def classify_intent(user_text: str) -> str:
    text = user_text.lower()
    if any(keyword in text for keyword in OWNED_GAME_KEYWORDS):
        return "owned_games"
    if any(keyword in text for keyword in RECOMMENDATION_KEYWORDS):
        return "recommendation"
    return "unknown"


def parse_owned_games(user_text: str, llm: Any) -> OwnedGamesRequest:
    parser = PydanticOutputParser(pydantic_object=OwnedGamesRequest)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Extrahiere genannte Spiele als JSON. "
                "Gib eine Liste mit Titel und optional platform, status, rating, playtime_hours.",
            ),
            ("human", "{user_text}\n\n{format_instructions}"),
        ]
    )
    chain = prompt | llm | parser
    return chain.invoke(
        {
            "user_text": user_text,
            "format_instructions": parser.get_format_instructions(),
        }
    )


def _find_game_candidates(session: Session, title: str, *, limit: int = 5) -> list[Games]:
    stmt = (
        select(Games)
        .where(Games.game_name.ilike(f"%{title}%"))
        .order_by(Games.recommendations.desc())
        .limit(limit)
    )
    return session.exec(stmt).all()


def _resolve_game(session: Session, title: str) -> Games | None:
    candidates = _find_game_candidates(session, title)
    if not candidates:
        print(f"Kein Treffer fuer '{title}'.")
        return None
    if len(candidates) == 1:
        return candidates[0]

    print(f"Mehrere Treffer fuer '{title}':")
    for idx, game in enumerate(candidates, start=1):
        print(f"{idx}. {game.game_name}")
    print("0. Ueberspringen")

    while True:
        choice = _prompt_int("Auswahl: ", min_value=0)
        if choice == 0:
            return None
        if 1 <= choice <= len(candidates):
            return candidates[choice - 1]
        print("Ungueltige Auswahl.")


def _upsert_user_game(
    session: Session,
    user_id: int,
    game: Games,
    owned_game: OwnedGame,
) -> bool:
    if game.id is None:
        return False
    existing = session.exec(
        select(UserGames).where(
            UserGames.user_id == user_id,
            UserGames.game_id == game.id,
        )
    ).first()

    if existing:
        changed = False
        if owned_game.status:
            existing.status = owned_game.status
            changed = True
        if owned_game.rating is not None:
            existing.rating = owned_game.rating
            changed = True
        if owned_game.playtime_hours is not None:
            existing.playtime_hours = owned_game.playtime_hours
            changed = True
        return changed

    session.add(
        UserGames(
            user_id=user_id,
            game_id=game.id,
            status=owned_game.status or "owned",
            rating=owned_game.rating,
            playtime_hours=owned_game.playtime_hours or 0.0,
        )
    )
    return True


def _print_recommendations(response: Any) -> None:
    if not response.recommendations:
        print("Keine Empfehlungen gefunden.")
        return
    print("Empfehlungen:")
    for rec in response.recommendations:
        price = f"{rec.price_eur:.2f} EUR" if rec.price_eur is not None else "Preis unbekannt"
        platform = rec.platform or "-"
        print(f"- {rec.title} | {platform} | {price} | Score: {rec.total_score}")


def _print_owned_games_result(saved_titles: list[str]) -> None:
    if not saved_titles:
        print("Keine Spiele eingetragen.")
        return
    print("Eingetragen:")
    for title in saved_titles:
        print(f"- {title}")


def chat_session(user: User, llm: ChatOpenAI) -> None:
    print("Du kannst loslegen. Tippe 'exit' zum Beenden.")
    while True:
        user_text = input("> ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit", "ende"}:
            print("Tschuess!")
            break

        intent = classify_intent(user_text)

        if intent == "owned_games":
            try:
                owned_request = parse_owned_games(user_text, llm)
            except Exception:
                print("Konnte die Spiele nicht erkennen. Bitte liste sie klar auf.")
                continue
            if not owned_request.games:
                print("Keine Spiele erkannt. Bitte erneut versuchen.")
                continue

            saved_titles: list[str] = []
            with Session(engine) as session:
                for owned_game in owned_request.games:
                    game = _resolve_game(session, owned_game.title)
                    if game is None:
                        continue
                    if _upsert_user_game(session, user.id, game, owned_game):
                        saved_titles.append(game.game_name)
                session.commit()

            _print_owned_games_result(saved_titles)
            continue

        if intent == "recommendation":
            request = parse_recommendation_request(user_text, llm)
            response = recommend_for_user_request(user.id, request, top_k=5)
            _print_recommendations(response)
            continue

        print(
            "Ich bin mir nicht sicher. Du kannst z.B. sagen: "
            "'Ich besitze Hades und Hollow Knight' oder 'Empfiehl mir ein RPG'."
        )


def main() -> None:
    if engine is None:
        print("Keine DB-Verbindung.")
        return

    user_email = _prompt_email()
    user = _get_or_create_user(user_email)
    if user is None or user.id is None:
        print(f"Kein User gefunden: {user_email}")
        return

    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
    )

    chat_session(user, llm)


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY fehlt.")
        raise SystemExit(1)
    main()
