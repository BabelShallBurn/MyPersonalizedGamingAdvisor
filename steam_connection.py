"""test module to learn about steam apis
"""

import os
import logging
import time
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
    logger.error("STEAM_API_KEY Umgebungsvariable ist nicht gesetzt.")
    raise ValueError("STEAM_API_KEY Umgebungsvariable ist nicht gesetzt.")

STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
APP_INFO_URL = "https://store.steampowered.com/api/appdetails"

def retrieve_app_list(URL: str) -> list:
    params_app_list = {"key": STEAM_API_KEY, "include_games": "true", "max_results": "50000", "last_appid": "0"}
    app_list = []
    while True:
        try:
            response = requests.get(url=URL, params=params_app_list, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "response" not in data or "apps" not in data["response"]:
                logger.warning("Unerwartetes Antwortformat von Steam API: %s", data)
                break
            apps = data["response"]["apps"]
            app_list.extend(apps)
            if "have_more_results" not in data["response"]:
                break
            params_app_list["last_appid"] = data["response"].get("last_appid", "0")
        except requests.exceptions.RequestException as e:
            logger.error(f"Fehler beim Abrufen der App-Liste: {e}")
            break
        except Exception as e:
            logger.error(f"Unerwarteter Fehler beim Abrufen der App-Liste: {e}")
            break
    return app_list if app_list else []



def retrieve_app_details(app_id: int) -> dict | None:
    params_app_info = {"appids": str(app_id)}
    try:
        response = requests.get(url=APP_INFO_URL, params=params_app_info, timeout=10)
        response.raise_for_status()
        data = response.json()
        if str(app_id) not in data or not data[str(app_id)]["success"]:
            logger.warning(f"Keine Daten für AppID {app_id} erhalten.")
            return None
        response = data[str(app_id)]["data"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Abrufen der App-Details für AppID {app_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unerwarteter Fehler bei AppID {app_id}: {e}")
        return None

    app_info = {}

    try:
        if "appid" in response:
            app_info["appid"] = response["appid"]
        if "name" in response:
            app_info["name"] = response["name"]
        if "detailed_description" in response:
            description_soup = BeautifulSoup(response["detailed_description"], 'html.parser')
            description = description_soup.get_text()
            app_info["description"] = description
        if "pc_requirements" in response:
            if "minimum" in response["pc_requirements"]:
                minimum_soup = BeautifulSoup(response['pc_requirements']['minimum'], 'html.parser')
                minimum_requirements = minimum_soup.get_text()
                app_info["minimum_requirements"] = minimum_requirements
            if "recommended" in response["pc_requirements"]:
                recommended_soup = BeautifulSoup(response['pc_requirements']['recommended'], 'html.parser')
                recommended_requirements = recommended_soup.get_text()
                app_info["recommended_requirements"] = recommended_requirements
        if "genres" in response:
            genres = [genre["description"] for genre in response["genres"]]
            app_info["genres"] = ", ".join(genres)
        if "price_overview" in response:
            if "final" in response["price_overview"]:
                price = response["price_overview"]["final"] / 100
                app_info["price"] = price
        if "platforms" in response:
            platforms = [platform for platform, available in response["platforms"].items() if available]
            app_info["platforms"] = ", ".join(platforms)
        if "ratings" in response:
            if "usk" in response["ratings"]:
                app_info["usk"] = response["ratings"]["usk"].get("rating", 0)
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der App-Details für AppID {app_id}: {e}")
        return None

    return app_info if app_info else None




def main():
    logger.info("Starte das Abrufen der Steam-App-Liste...")
    apps = retrieve_app_list(STEAM_APP_LIST_URL)

    if len(apps) == 0:
        logger.error("Keine Apps von der Steam API erhalten.")
        return

    logger.info(f"{len(apps)} Apps gefunden. Starte das Abrufen der Details...")
    for app in apps:
        appid = app.get('appid')
        if not appid:
            logger.warning(f"App ohne gültige appid gefunden: {app}")
            continue
        game = retrieve_app_details(appid)
        if game:
            success = save_game_details(game)
            if success:
                logger.info(f"Gespeichert: {game.get('name', 'Unbekannt')}")
            else:
                logger.error(f"Fehler beim Speichern: {game.get('name', 'Unbekannt')}")
        else:
            logger.warning(f"Keine Details für AppID {appid} erhalten.")
        time.sleep(2.5)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Unerwarteter Fehler im Hauptprogramm: {e}")
