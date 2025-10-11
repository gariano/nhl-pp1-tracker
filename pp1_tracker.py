import asyncio
import aiohttp
from bs4 import BeautifulSoup
import requests

# Discord Webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1425577584955232468/maRYwPZb_U-lKKgnb31hV-z2t2xgtGhKHdGBEQztdaFu0dkle0HcFk7msLchWXk_93TI"

# --- Config ---
POLL_INTERVAL = 3600  # 60 minutes

# NHL teams (with Utah Mammoth replacement)
teams = {
    "Anaheim Ducks": "anaheim-ducks",
    "Utah Mammoth": "utah-mammoth",
    "Boston Bruins": "boston-bruins",
    "Buffalo Sabres": "buffalo-sabres",
    "Calgary Flames": "calgary-flames",
    "Carolina Hurricanes": "carolina-hurricanes",
    "Chicago Blackhawks": "chicago-blackhawks",
    "Colorado Avalanche": "colorado-avalanche",
    "Columbus Blue Jackets": "columbus-blue-jackets",
    "Dallas Stars": "dallas-stars",
    "Detroit Red Wings": "detroit-red-wings",
    "Edmonton Oilers": "edmonton-oilers",
    "Florida Panthers": "florida-panthers",
    "Los Angeles Kings": "los-angeles-kings",
    "Minnesota Wild": "minnesota-wild",
    "Montreal Canadiens": "montreal-canadiens",
    "Nashville Predators": "nashville-predators",
    "New Jersey Devils": "new-jersey-devils",
    "New York Islanders": "new-york-islanders",
    "New York Rangers": "new-york-rangers",
    "Ottawa Senators": "ottawa-senators",
    "Philadelphia Flyers": "philadelphia-flyers",
    "Pittsburgh Penguins": "pittsburgh-penguins",
    "San Jose Sharks": "san-jose-sharks",
    "Seattle Kraken": "seattle-kraken",
    "St. Louis Blues": "st-louis-blues",
    "Tampa Bay Lightning": "tampa-bay-lightning",
    "Toronto Maple Leafs": "toronto-maple-leafs",
    "Vancouver Canucks": "vancouver-canucks",
    "Vegas Golden Knights": "vegas-golden-knights",
    "Washington Capitals": "washington-capitals",
    "Winnipeg Jets": "winnipeg-jets"
}

BASE_URL = "https://www.dailyfaceoff.com/teams/{team}/line-combinations"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/114.0.0.0 Safari/537.36"
}

previous_pp1 = {}  # track old PP1 for change detection

# --- Async fetch ---
async def fetch_team(session, team_name, team_path):
    url = BASE_URL.format(team=team_path)
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status != 200:
                return team_name, None
            text = await response.text()
            return team_name, BeautifulSoup(text, "lxml")
    except:
        return team_name, None

def extract_section_players(soup, header_text, num_players=None):
    header = soup.find(string=lambda t: t and header_text.lower() in t.lower())
    if not header:
        return []

    section = header.find_parent("div")
    name_spans = section.find_all_next("span", class_="text-xs font-bold uppercase xl:text-base")

    players = []
    for span in name_spans:
        text = span.get_text(strip=True)
        if any(x in text.lower() for x in ["forwards", "defense", "powerplay", "penalty"]):
            break
        if text and text not in players:
            players.append(text)
        if num_players and len(players) >= num_players:
            break
    return players

def extract_first_forward_line(soup):
    forward_section = soup.find("span", string="Forwards")
    if not forward_section:
        return []
    all_forward_names = [
        span.get_text(strip=True)
        for span in soup.select("div.flex.flex-row.justify-center span.text-xs.font-bold.uppercase.xl\\:text-base")
    ]
    return all_forward_names[:3]

def send_discord_notification(team, new_players, old_players):
    content = f"**PP1 Update for {team}**\n"
    added = [p for p in new_players if p not in old_players]
    removed = [p for p in old_players if p not in new_players]
    if added:
        content += f"Added: {', '.join(added)}\n"
    if removed:
        content += f"Removed: {', '.join(removed)}\n"

    requests.post(DISCORD_WEBHOOK_URL, json={"content": content})

def display_all_teams(data):
    print("\n" + "="*80)
    for team, info in data.items():
        line1 = ", ".join(info["line1"]) if info["line1"] else "N/A"
        pp1 = ", ".join(info["pp1"]) if info["pp1"] else "N/A"
        print(f"{team} | Line 1: {line1} | PP1: {pp1}")
    print("="*80)

# --- Main async loop ---
async def main_once():
    async with aiohttp.ClientSession() as session:
        while True:
            tasks = [fetch_team(session, team_name, team_path) for team_name, team_path in teams.items()]
            results = await asyncio.gather(*tasks)

            all_team_data = {}

            for team_name, soup in results:
                if not soup:
                    continue

                line1_players = extract_first_forward_line(soup)
                pp1_players = extract_section_players(soup, "1st Powerplay Unit", num_players=5)

                old_pp1 = previous_pp1.get(team_name, [])
                if pp1_players != old_pp1 and old_pp1:
                    send_discord_notification(team_name, pp1_players, old_pp1)
                previous_pp1[team_name] = pp1_players

                all_team_data[team_name] = {"line1": line1_players, "pp1": pp1_players}

            display_all_teams(all_team_data)
            await asyncio.sleep(POLL_INTERVAL)

# --- Run once and exit ---
asyncio.run(main_once())


