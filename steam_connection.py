"""test module to learn about steam apis
"""

import os
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")


URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
params = {"key": STEAM_API_KEY, "include_games": "true", "max_results":"50000"}

apps = requests.get(
    url=URL, params=params, timeout=10
).json()["response"]["apps"]

print(len(apps))

for app in apps:
    if "assassin" in app['name'].lower() and "creed" in app['name'].lower():
        print(f"ID: {app["appid"]}, name: {app["name"]}")


URL2 = "https://store.steampowered.com/api/appdetails"
params2 = {"appids": "289650"}

app_details = requests.get(
    url=URL2, params=params2, timeout=10
).json()[params2["appids"]]["data"]

minimum_soup = BeautifulSoup(app_details['pc_requirements']['minimum'], 'html.parser')
minimum_requirements = minimum_soup.get_text()

print(f"Name: {app_details["name"]}\n\ndeteials: {app_details["detailed_description"]}\n\nrequirements: {minimum_requirements}")
