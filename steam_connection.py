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

description_soup = BeautifulSoup(app_details["detailed_description"], 'html.parser')
description = description_soup.get_text()

minimum_soup = BeautifulSoup(app_details['pc_requirements']['minimum'], 'html.parser')
minimum_requirements = minimum_soup.get_text()

recomended_soup = BeautifulSoup(app_details['pc_requirements']['recommended'], 'html.parser')
recomended_requirements = recomended_soup.get_text()

print(f"\nName: {app_details["name"]}\n\ndetails: {description}\n\nminimum requirements: {minimum_requirements}\n\nrecommended requierements: {recomended_requirements}")
