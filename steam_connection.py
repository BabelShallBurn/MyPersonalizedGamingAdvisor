"""Steam API integration and transformation pipeline for game records."""

import os
import logging
import time
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from database.data_handling import engine, create_tables, save_game_details

# Setup logging
LOG_FILE = Path(__file__).resolve().parent / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger(__name__)

load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
if not STEAM_API_KEY:
    logger.error("STEAM_API_KEY environment variable is not set.")
    raise ValueError("STEAM_API_KEY Umgebungsvariable ist nicht gesetzt.")

STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
APP_INFO_URL = "https://store.steampowered.com/api/appdetails"


def _extract_clean_text(value: str | None) -> str:
    """Strip HTML markup and return normalized plain text."""
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def _extract_usk_rating(raw_data: dict) -> int:
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


def _extract_platform_requirements(raw_data: dict) -> list[dict]:
    """Extract normalized requirements grouped by supported platforms."""
    requirements: list[dict] = []
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


def _parse_release_date(release_date_payload: dict | None) -> str:
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


def create_game_info_dict(raw_data: dict) -> dict:
    """Map raw Steam app data to the internal game schema."""
    app_info: dict = {}

    app_info["appid"] = raw_data.get("steam_appid", raw_data.get("appid"))
    app_info["name"] = raw_data.get("name", "")

    description_html = raw_data.get("detailed_description") or raw_data.get("about_the_game") or ""
    app_info["description"] = _extract_clean_text(description_html)

    system_requirements = _extract_platform_requirements(raw_data)
    app_info["system_requirements"] = system_requirements

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

def retrieve_app_list(URL: str) -> list:
    """Fetch the full Steam app list using paginated API requests."""
    params_app_list = {"key": STEAM_API_KEY, "include_games": "true", "max_results": "50000", "last_appid": "0"}
    app_list = []
    while True:
        try:
            response = requests.get(url=URL, params=params_app_list, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "response" not in data or "apps" not in data["response"]:
                logger.warning("Unexpected response format from Steam API: %s", data)
                break
            apps = data["response"]["apps"]
            app_list.extend(apps)
            if "have_more_results" not in data["response"]:
                break
            params_app_list["last_appid"] = data["response"].get("last_appid", "0")
        except requests.exceptions.RequestException as e:
            logger.error("Error retrieving app list: %s", e)
            break
        except Exception as e:
            logger.error("Unexpected error retrieving app list: %s", e)
            break
    return app_list if app_list else []



def retrieve_app_details(app_id: int) -> dict | None:
    """Fetch details for a Steam app ID and return normalized game data."""
    params_app_info = {"appids": str(app_id)}
    try:
        response = requests.get(url=APP_INFO_URL, params=params_app_info, timeout=10)
        response.raise_for_status()
        payload = response.json()
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
    except requests.exceptions.RequestException as e:
        logger.error("Error retrieving app details for AppID %s: %s", app_id, e)
        return None
    except Exception as e:
        logger.error("Unexpected error for AppID %s: %s", app_id, e)
        return None




def process_and_save_apps(apps: list[dict]) -> None:
    """Process an app list, fetch details, and persist each game record."""
    for app in apps:
        appid = app.get("appid")
        if not appid:
            logger.warning("App without a valid appid found: %s", app)
            continue

        game = retrieve_app_details(appid)
        if game:
            success = save_game_details(game)
            if success:
                logger.info("Saved: %s", game.get("name", "Unknown"))
            else:
                logger.error("Error saving: %s", game.get("name", "Unknown"))
        else:
            logger.warning("No details received for AppID %s.", appid)
        time.sleep(2.5)


def main():
    """Run the end-to-end flow: fetch list, fetch details, save results."""
    logger.info("Starting Steam app list retrieval...")
    apps = retrieve_app_list(STEAM_APP_LIST_URL)

    if len(apps) == 0:
        logger.error("No apps received from the Steam API.")
        return

    logger.info("%s apps found. Starting detail retrieval...", len(apps))
    process_and_save_apps(apps)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical("Unexpected error in main program: %s", e)
