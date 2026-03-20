from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from langchain_openai import ChatOpenAI
from sqlmodel import Session, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gaming_advisor.config import OPENAI_API_KEY, TEST_USER_EMAIL
from gaming_advisor.db.engine import engine
from gaming_advisor.db.models import Games, User
from gaming_advisor.db.data_handling import get_user_library
from gaming_advisor.services.chat_service import handle_user_message


def _get_user_by_email(session: Session, email: str) -> User | None:
    """Fetch a user by email address.

    Args:
        session: Active database session.
        email: Email address to match.

    Returns:
        The matching user if found; otherwise None.
    """
    return session.exec(select(User).where(User.email == email)).first()


def _delete_user_by_email(email: str) -> bool:
    """Delete a user by email address.

    Args:
        email: Email address to delete.

    Returns:
        True if a user was deleted; otherwise False.
    """
    if engine is None:
        return False
    with Session(engine) as session:
        user = _get_user_by_email(session, email)
        if user is None:
            return False
        session.delete(user)
        session.commit()
        return True


def _prompt_non_empty(prompt: str, *, default: str | None = None) -> str:
    """Prompt until a non-empty response is provided.

    Args:
        prompt: Prompt text shown to the user.
        default: Optional default when the user presses Enter.

    Returns:
        The non-empty user response or the default.
    """
    while True:
        raw = input(prompt).strip()
        if raw:
            return raw
        if default is not None:
            return default
        print("Please enter a value.")


def _prompt_int(prompt: str, *, default: int | None = None, min_value: int | None = None) -> int:
    """Prompt for an integer value with optional constraints.

    Args:
        prompt: Prompt text shown to the user.
        default: Optional default when the user presses Enter.
        min_value: Optional minimum value (inclusive).

    Returns:
        The validated integer value.
    """
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


def _prompt_yes_no(prompt: str, *, default: bool = False) -> bool:
    """Prompt for a yes/no answer.

    Args:
        prompt: Prompt text shown to the user.
        default: Default value when the user presses Enter.

    Returns:
        True for yes, False for no.
    """
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        raw = input(prompt + suffix).strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes", "j", "ja"}:
            return True
        if raw in {"n", "no", "nein"}:
            return False
        print("Please answer yes or no.")


def _prompt_email(*, allow_delete: bool = False) -> str:
    """Prompt for an email address with optional env fallback.

    Returns:
        The entered email address.
    """
    default = TEST_USER_EMAIL
    prompt = "Please enter your email"
    if allow_delete:
        prompt += " (or type 'delete' to remove a user)"
    if default:
        prompt += f" (press Enter for {default})"
    prompt += ": "
    while True:
        raw = input(prompt).strip()
        if allow_delete and raw.lower() in {"delete", "del"}:
            return "delete"
        if raw:
            return raw
        if default:
            return default
        print("Email must not be empty.")


def _get_or_create_user(email: str) -> User | None:
    """Retrieve an existing user or create a new profile.

    Args:
        email: Email address for lookup and creation.

    Returns:
        The existing or newly created user, or None if unavailable.
    """
    if engine is None:
        return None
    with Session(engine) as session:
        current_email = email
        while True:
            user = _get_user_by_email(session, current_email)
            if user is not None:
                return user

            print(f"No user found for {current_email}.")
            should_create = _prompt_yes_no("Create a new profile?")
            if should_create:
                name = _prompt_non_empty("Name: ")
                language = _prompt_non_empty("Language (e.g. en): ", default="en")
                age = _prompt_int("Age: ", min_value=0)
                platform = _prompt_non_empty("Platform (e.g. PC): ", default="PC")

                user = User(
                    name=name,
                    email=current_email,
                    language=language,
                    age=age,
                    platform=platform,
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                return user

            current_email = _prompt_non_empty("Enter a different email: ")




def _find_game_candidates(session: Session, title: str, *, limit: int = 5) -> list[Games]:
    """Find candidate games by fuzzy title match.

    Args:
        session: Active database session.
        title: Title to search for.
        limit: Maximum number of candidates to return.

    Returns:
        Candidate games ordered by recommendation volume.
    """
    stmt = (
        select(Games)
        .where(Games.game_name.ilike(f"%{title}%"))
        .order_by(Games.recommendations.desc())
        .limit(limit)
    )
    return session.exec(stmt).all()


def _resolve_game(session: Session, title: str) -> Games | None:
    """Resolve a game title to a specific database record.

    Args:
        session: Active database session.
        title: Title to resolve.

    Returns:
        The selected game or None if skipped/unknown.
    """
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



def _print_recommendations(response: Any) -> None:
    """Print recommendation results to stdout.

    Args:
        response: Recommendation response payload.
    """
    if not response.recommendations:
        print("No recommendations found.")
        return
    print("Recommendations:")
    for rec in response.recommendations:
        price = f"{rec.price_eur:.2f} EUR" if rec.price_eur is not None else "Price unknown"
        platform = rec.platform or "-"
        print(f"- {rec.title} | {platform} | {price} | Score: {rec.total_score}")
        if rec.match_reasons:
            print("  Reasons:")
            for reason in rec.match_reasons:
                print(f"  - {reason}")


def _print_owned_games_result(saved_titles: list[str]) -> None:
    """Print saved owned-game titles to stdout.

    Args:
        saved_titles: Titles that were persisted.
    """
    if not saved_titles:
        print("No games saved.")
        return
    print("Saved:")
    for title in saved_titles:
        print(f"- {title}")


def _print_library(entries: list[dict[str, Any]]) -> None:
    """Print the user's library entries to stdout."""
    if not entries:
        print("Your library is empty.")
        return

    print("Your library:")
    for entry in entries:
        status = entry.get("status", "owned")
        rating = entry.get("rating")
        playtime = entry.get("playtime_hours")
        details = [status]
        if rating is not None:
            details.append(f"rating {rating}/10")
        if playtime is not None:
            details.append(f"{playtime:.1f}h")
        print(f"- {entry.get('name', 'Unknown')} ({', '.join(details)})")


def chat_session(user: User, llm: ChatOpenAI) -> None:
    """Run an interactive chat session for a single user.

    Args:
        user: Authenticated user profile.
        llm: LLM instance used for routing and parsing.
    """
    print("You can start now. Type 'exit' to quit.")
    while True:
        user_text = input("> ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit", "ende"}:
            print("Bye!")
            break
        if user_text.lower() in {"library", "/library", "list games", "list library"}:
            _print_library(get_user_library(user.id))
            continue

        result = handle_user_message(
            user.id,
            user_text,
            llm,
            resolve_game=_resolve_game,
            top_k=5,
        )

        if result.kind == "clarify":
            print(result.message or "Do you mean recommendations or owned games?")
            continue

        if result.kind == "owned_games_saved":
            _print_owned_games_result(result.saved_titles or [])
            continue

        if result.kind == "library_list":
            _print_library(result.library_entries or [])
            continue

        if result.kind == "recommendations":
            _print_recommendations(result.recommendations)
            continue

        if result.kind in {"error", "unknown"}:
            print(
                result.message
                or "I'm not sure. You can say for example: "
                "'I own Hades and Hollow Knight' or 'Recommend an RPG'."
            )


def main() -> None:
    """Entry point for the CLI chat demo."""
    if engine is None:
        print("No DB connection.")
        return

    while True:
        user_email = _prompt_email(allow_delete=True)
        if user_email.lower() in {"delete", "del"}:
            target_email = _prompt_non_empty("Email to delete: ")
            if _prompt_yes_no(f"Delete user {target_email}?"):
                if _delete_user_by_email(target_email):
                    print(f"Deleted user: {target_email}")
                else:
                    print(f"No user found: {target_email}")
            else:
                print("Deletion cancelled.")
            continue
        break
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
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY is missing.")
        raise SystemExit(1)
    main()
