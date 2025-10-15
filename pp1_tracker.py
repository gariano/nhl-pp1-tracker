import asyncio
import aiohttp
from bs4 import BeautifulSoup
import requests
import os
import json

# Discord Webhook URL
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

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
PREV_FILE = "previous_pp1.json"

# --- Helpers to persist previous_pp1 between runs --- #
def load_previous():
    if os.path.exists(PREV_FILE):
        try:
            with open(PREV_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_previous(prev_dict):
    # atomic-ish write
    tmp = PREV_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prev_dict, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREV_FILE)

# --- Scraping / parsing --- #
async def fetch_team(session, team_name, team_path):
    url = BASE_URL.format(team=team_path)
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with session.get(url, headers=HEADERS, timeout=timeout) as response:
            if response.status != 200:
                print(f"{team_name}: HTTP {response.status}")
                return team_name, None
            text = await response.text()
            return team_name, BeautifulSoup(text, "lxml")
    except asyncio.TimeoutError:
        print(f"{team_name}: ❌ Timeout")
        return team_name, None
    except Exception as e:
        print(f"{team_name} ERROR: {e}")
        return team_name, None

def extract_section_players(soup, header_text, num_players=None):
    if not soup:
        return []
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
    if not soup:
        return []
    forward_section = soup.find("span", string="Forwards")
    if not forward_section:
        return []
    all_forward_names = [
        span.get_text(strip=True)
        for span in soup.select("div.flex.flex-row.justify-center span.text-xs.font-bold.uppercase.xl\\:text-base")
    ]
    return all_forward_names[:3]

def send_discord_notification(team, new_players, old_players):
    if not DISCORD_WEBHOOK_URL:
        print("Discord webhook not configured; skipping notification.")
        return
    added = [p for p in new_players if p not in old_players]
    removed = [p for p in old_players if p not in new_players]
    if not added and not removed:
        return
    content = f"**PP1 Update for {team}** @seang37 \n"
    if added:
        content += f"Added: {', '.join(added)}\n"
    if removed:
        content += f"Removed: {', '.join(removed)}"
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=10)
    except Exception as e:
        print("Failed to send Discord webhook:", e)

def display_all_teams(data):
    print("\n" + "="*80)
    for team, info in data.items():
        line1 = ", ".join(info["line1"]) if info["line1"] else "N/A"
        pp1 = ", ".join(info["pp1"]) if info["pp1"] else "N/A"
        print(f"{team} | Line 1: {line1} | PP1: {pp1}")
    print("="*80)


# --- Main single-run function (for GitHub Actions) --- #
async def main_once():
    previous = load_previous()  # dict: team -> list of players
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_team(session, team, path) for team, path in teams.items()]
        results = await asyncio.gather(*tasks)

    all_team_data = {}
    updated_prev = dict(previous)  # copy to update

    for team_name, soup in results:
        if not soup:
            # leave previous as-is
            continue

        line1_players = extract_first_forward_line(soup)
        pp1_players = extract_section_players(soup, "1st Powerplay Unit", num_players=5)

        old_pp1 = previous.get(team_name, [])
        if pp1_players != old_pp1 and old_pp1:
            send_discord_notification(team_name, pp1_players, old_pp1)

        updated_prev[team_name] = pp1_players
        all_team_data[team_name] = {"line1": line1_players, "pp1": pp1_players}

    display_all_teams(all_team_data)

    # save updated previous_pp1.json ALWAYS (so the runner can commit it back)
    save_previous(updated_prev)
    print("Saved updated previous_pp1.json")

if __name__ == "__main__":
    print("Starting single-run PP1 tracker...")
    try:
        asyncio.run(asyncio.wait_for(main_once(), timeout=120))
    except asyncio.TimeoutError:
        print("Script timed out.")
    print("Done.")









