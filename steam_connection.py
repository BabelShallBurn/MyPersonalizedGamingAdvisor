"""Steam API integration and payload normalization.

This module only handles external Steam communication and data transformation.
It does not read from or write to the local database.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

LOG_FILE = Path(__file__).resolve().parent / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger(__name__)

load_dotenv()

STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
APP_INFO_URL = "https://store.steampowered.com/api/appdetails"


class SteamAPIError(RuntimeError):
    """Raised when Steam API calls fail or return invalid payloads."""


class SteamClient:
    """Thin Steam API client for catalog endpoints."""

    def __init__(self, api_key: str | None = None, timeout: int = 10) -> None:
        self.api_key = api_key or os.getenv("STEAM_API_KEY")
        if not self.api_key:
            raise ValueError("STEAM_API_KEY Umgebungsvariable ist nicht gesetzt.")

        self.timeout = timeout
        self.session = requests.Session()

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        all_params = {"key": self.api_key, **params}
        try:
            response = self.session.get(url=url, params=all_params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise SteamAPIError("Steam API lieferte kein valides JSON-Objekt.")
            return data
        except requests.RequestException as exc:
            raise SteamAPIError(f"Steam API Request fehlgeschlagen: {exc}") from exc
        except ValueError as exc:
            raise SteamAPIError("Steam API lieferte kein valides JSON.") from exc


_CLIENT: SteamClient | None = None


def _get_client() -> SteamClient:
    """Create and cache a client instance on first use."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = SteamClient()
    return _CLIENT


def _extract_clean_text(value: str | None) -> str:
    """Strip HTML markup and return normalized plain text."""
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def _extract_usk_rating(raw_data: dict[str, Any]) -> int:
    """Extract a valid USK age rating from raw Steam payload data."""
    ratings = raw_data.get("ratings")
    if not isinstance(ratings, dict):
        return 0

    usk_data = ratings.get("usk")
    if not isinstance(usk_data, dict):
        return 0

    raw_rating = str(usk_data.get("rating", "")).strip()
    digits = "".join(ch for ch in raw_rating if ch.isdigit())
    if not digits:
        return 0

    rating = int(digits)
    return rating if rating in {0, 6, 12, 16, 18} else 0


def _extract_platform_requirements(raw_data: dict[str, Any]) -> list[dict[str, str | None]]:
    """Extract normalized requirements grouped by supported platforms."""
    requirements: list[dict[str, str | None]] = []
    for platform in ("pc", "mac", "linux"):
        platform_data = raw_data.get(f"{platform}_requirements")
        if not isinstance(platform_data, dict):
            continue

        minimum = _extract_clean_text(platform_data.get("minimum", ""))
        recommended = _extract_clean_text(platform_data.get("recommended", ""))

        if not minimum and not recommended:
            continue

        requirements.append(
            {
                "platform": platform,
                "minimum": minimum,
                "recommended": recommended or None,
            }
        )
    return requirements


def _parse_release_date(release_date_payload: dict[str, Any] | None) -> str:
    """Parse Steam release date text to ISO date, fallback to original text."""
    if not isinstance(release_date_payload, dict):
        return ""

    raw_date = release_date_payload.get("date", "")
    if not isinstance(raw_date, str):
        return ""

    cleaned = raw_date.replace("\xa0", " ").strip()
    if not cleaned:
        return ""

    for fmt in ("%d %b, %Y", "%d %B, %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue

    return cleaned


def create_game_info_dict(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Map raw Steam app data to the internal game schema."""
    app_info: dict[str, Any] = {}

    app_info["appid"] = raw_data.get("steam_appid", raw_data.get("appid"))
    app_info["name"] = raw_data.get("name", "")

    description_html = raw_data.get("detailed_description") or raw_data.get("about_the_game") or ""
    app_info["description"] = _extract_clean_text(description_html)

    app_info["system_requirements"] = _extract_platform_requirements(raw_data)
    app_info["minimum_requirements"] = ""
    app_info["recommended_requirements"] = None

    genres = raw_data.get("genres")
    if isinstance(genres, list):
        app_info["genres"] = ", ".join(
            genre.get("description", "").strip()
            for genre in genres
            if isinstance(genre, dict) and genre.get("description")
        )
    else:
        app_info["genres"] = ""

    price_overview = raw_data.get("price_overview")
    if isinstance(price_overview, dict) and isinstance(price_overview.get("final"), int):
        app_info["price"] = price_overview["final"] / 100
    else:
        app_info["price"] = 0.0

    platforms = raw_data.get("platforms")
    if isinstance(platforms, dict):
        app_info["platforms"] = ", ".join(
            platform for platform, available in platforms.items() if available is True
        )
    else:
        app_info["platforms"] = ""

    app_info["usk"] = _extract_usk_rating(raw_data)
    app_info["release_date"] = _parse_release_date(raw_data.get("release_date"))

    recommendations = raw_data.get("recommendations")
    if isinstance(recommendations, dict):
        app_info["recommendations"] = recommendations.get("total", 0)
    else:
        app_info["recommendations"] = 0

    return app_info


def retrieve_app_list(url: str = STEAM_APP_LIST_URL) -> list[dict[str, Any]]:
    """Fetch the full Steam app list using paginated API requests."""
    params = {
        "include_games": "true",
        "max_results": "50000",
        "last_appid": "0",
    }
    app_list: list[dict[str, Any]] = []

    while True:
        try:
            payload = _get_client()._get_json(url, params)
        except SteamAPIError as exc:
            logger.error("Error retrieving app list: %s", exc)
            break

        response = payload.get("response")
        if not isinstance(response, dict):
            logger.warning("Unexpected response format from Steam API: %s", payload)
            break

        apps = response.get("apps", [])
        if isinstance(apps, list):
            app_list.extend([app for app in apps if isinstance(app, dict)])

        if "have_more_results" not in response:
            break

        params["last_appid"] = str(response.get("last_appid", "0"))

    return app_list


def retrieve_app_details(app_id: int) -> dict[str, Any] | None:
    """Fetch details for a Steam app ID and return normalized game data."""
    try:
        payload = _get_client()._get_json(APP_INFO_URL, {"appids": str(app_id)})
    except SteamAPIError as exc:
        logger.error("Error retrieving app details for AppID %s: %s", app_id, exc)
        return None

    app_payload = payload.get(str(app_id))
    if not isinstance(app_payload, dict) or not app_payload.get("success", False):
        logger.warning("No data received for AppID %s.", app_id)
        return None

    raw_data = app_payload.get("data")
    if not isinstance(raw_data, dict):
        logger.warning("Invalid data format for AppID %s.", app_id)
        return None

    app_info = create_game_info_dict(raw_data)
    if not app_info.get("name"):
        logger.warning("Empty or incomplete game information for AppID %s.", app_id)
        return None

    return app_info


if __name__ == "__main__":
    logger.info("Steam integration module loaded. No database side-effects are executed.")
