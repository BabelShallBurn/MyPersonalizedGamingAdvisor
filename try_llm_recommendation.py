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


class RouteDecision(BaseModel):
    intent: Literal["owned_games", "recommendation", "profile_update", "unknown"]
    confidence: float = Field(ge=0, le=1)
    followup_question: str | None = None


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
        print("Please enter a value.")


def _prompt_int(prompt: str, *, default: int | None = None, min_value: int | None = None) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Please enter an integer.")
            continue
        if min_value is not None and value < min_value:
            print(f"Please enter a number >= {min_value}.")
            continue
        return value


def _prompt_email() -> str:
    default = os.getenv("TEST_USER_EMAIL")
    prompt = "Please enter your email"
    if default:
        prompt += f" (press Enter for {default})"
    prompt += ": "
    while True:
        raw = input(prompt).strip()
        if raw:
            return raw
        if default:
            return default
        print("Email must not be empty.")


def _get_or_create_user(email: str) -> User | None:
    if engine is None:
        return None
    with Session(engine) as session:
        user = _get_user_by_email(session, email)
        if user is not None:
            return user

        print("No user found. Let's create your profile.")
        name = _prompt_non_empty("Name: ")
        language = _prompt_non_empty("Language (e.g. en): ", default="en")
        age = _prompt_int("Age: ", min_value=0)
        platform = _prompt_non_empty("Platform (e.g. PC): ", default="PC")

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


def route_user_text(user_text: str, llm: Any) -> RouteDecision:
    parser = PydanticOutputParser(pydantic_object=RouteDecision)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a router for a gaming advisor chat. "
                "Choose the correct intent class: "
                "owned_games (user names games they own), "
                "recommendation (user asks for recommendations), "
                "profile_update (user wants to update their profile), "
                "unknown (unclear). "
                "If unclear, set intent='unknown' and ask a short follow-up question.\n\n"
                "Examples:\n"
                "- \"I own Hades and Hollow Knight.\" -> owned_games\n"
                "- \"I have 20 hours in Elden Ring.\" -> owned_games\n"
                "- \"Recommend a fast-paced racing game.\" -> recommendation\n"
                "- \"I'm looking for a cozy farming sim.\" -> recommendation\n"
                "- \"Change my platform to PC.\" -> profile_update\n"
                "- \"Update my age to 25.\" -> profile_update\n",
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


def parse_owned_games(user_text: str, llm: Any) -> OwnedGamesRequest:
    parser = PydanticOutputParser(pydantic_object=OwnedGamesRequest)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Extract the mentioned games as JSON. "
                "Return a list with title and optional platform, status, rating, playtime_hours.",
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
        print(f"No match for '{title}'.")
        return None
    if len(candidates) == 1:
        return candidates[0]

    print(f"Multiple matches for '{title}':")
    for idx, game in enumerate(candidates, start=1):
        print(f"{idx}. {game.game_name}")
    print("0. Skip")

    while True:
        choice = _prompt_int("Select: ", min_value=0)
        if choice == 0:
            return None
        if 1 <= choice <= len(candidates):
            return candidates[choice - 1]
        print("Invalid selection.")


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
        print("No recommendations found.")
        return
    print("Recommendations:")
    for rec in response.recommendations:
        price = f"{rec.price_eur:.2f} EUR" if rec.price_eur is not None else "Price unknown"
        platform = rec.platform or "-"
        print(f"- {rec.title} | {platform} | {price} | Score: {rec.total_score}")


def _print_owned_games_result(saved_titles: list[str]) -> None:
    if not saved_titles:
        print("No games saved.")
        return
    print("Saved:")
    for title in saved_titles:
        print(f"- {title}")


def chat_session(user: User, llm: ChatOpenAI) -> None:
    print("You can start now. Type 'exit' to quit.")
    while True:
        user_text = input("> ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit", "ende"}:
            print("Bye!")
            break

        decision = route_user_text(user_text, llm)
        intent = decision.intent
        needs_clarification = intent == "unknown" or decision.confidence < 0.6

        if needs_clarification:
            print(
                decision.followup_question
                or "Do you mean recommendations or owned games?"
            )
            continue

        if intent == "owned_games":
            try:
                owned_request = parse_owned_games(user_text, llm)
            except Exception:
                print("Couldn't parse the games. Please list them clearly.")
                continue
            if not owned_request.games:
                print("No games recognized. Please try again.")
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
            "I'm not sure. You can say for example: "
            "'I own Hades and Hollow Knight' or 'Recommend an RPG'."
        )


def main() -> None:
    if engine is None:
        print("No DB connection.")
        return

    user_email = _prompt_email()
    user = _get_or_create_user(user_email)
    if user is None or user.id is None:
        print(f"No user found: {user_email}")
        return

    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
    )

    chat_session(user, llm)


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is missing.")
        raise SystemExit(1)
    main()
