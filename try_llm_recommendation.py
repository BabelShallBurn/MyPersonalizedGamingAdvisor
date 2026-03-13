from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from database.data_handling import engine, get_user_by_email
from recommender import parse_recommendation_request, recommend_for_user_request


def main() -> None:
    if engine is None:
        print("Keine DB-Verbindung.")
        return

    user_email = input("Bitte E-Mail eingeben (leer = TEST_USER_EMAIL): ").strip()
    if not user_email:
        user_email = os.getenv("TEST_USER_EMAIL", "eric@example.com")

    user = get_user_by_email(user_email)
    if user is None or user.id is None:
        print(f"Kein User gefunden: {user_email}")
        return
    user_id = user.id

    user_text = "Ich suche ein actiongeladenes Abenteuer mit RPG-Elementen."

    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
    )

    request = parse_recommendation_request(user_text, llm)
    response = recommend_for_user_request(user_id, request, top_k=5)

    print("Eingabe:", user_text)
    print("Extrahiert:", request.model_dump())
    print("Empfehlungen:")
    for rec in response.recommendations:
        price = f"{rec.price_eur:.2f} EUR" if rec.price_eur is not None else "Preis unbekannt"
        platform = rec.platform or "-"
        print(f"- {rec.title} | {platform} | {price} | Score: {rec.total_score}")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY fehlt.")
        raise SystemExit(1)
    main()
