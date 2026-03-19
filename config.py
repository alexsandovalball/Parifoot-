"""
config.py – Centralised configuration loaded from environment variables.

Copy `.env.example` to `.env`, fill in your keys, then run the bot.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]

# Your personal Telegram chat-id (integer).  The daily scheduler sends the
# ticket to this chat automatically every morning.
TELEGRAM_CHAT_ID: int = int(os.environ["TELEGRAM_CHAT_ID"])

# ---------------------------------------------------------------------------
# External API keys
# ---------------------------------------------------------------------------
# https://the-odds-api.com/
ODDS_API_KEY: str = os.environ["ODDS_API_KEY"]

# https://www.api-football.com/
API_FOOTBALL_KEY: str = os.environ["API_FOOTBALL_KEY"]

# ---------------------------------------------------------------------------
# Algorithm parameters
# ---------------------------------------------------------------------------
# Target total combined odds window
TARGET_ODDS_MIN: float = float(os.getenv("TARGET_ODDS_MIN", "8.0"))
TARGET_ODDS_MAX: float = float(os.getenv("TARGET_ODDS_MAX", "20.0"))

# Foundation legs – odds range per leg
FOUNDATION_ODDS_MIN: float = float(os.getenv("FOUNDATION_ODDS_MIN", "1.10"))
FOUNDATION_ODDS_MAX: float = float(os.getenv("FOUNDATION_ODDS_MAX", "1.70"))

# Booster legs – odds range per leg
BOOSTER_ODDS_MIN: float = float(os.getenv("BOOSTER_ODDS_MIN", "1.50"))
BOOSTER_ODDS_MAX: float = float(os.getenv("BOOSTER_ODDS_MAX", "4.00"))

# How many foundation and booster legs to aim for
FOUNDATION_LEGS_MIN: int = int(os.getenv("FOUNDATION_LEGS_MIN", "3"))
FOUNDATION_LEGS_MAX: int = int(os.getenv("FOUNDATION_LEGS_MAX", "6"))
BOOSTER_LEGS_COUNT: int = int(os.getenv("BOOSTER_LEGS_COUNT", "1"))

# Minimum statistical threshold for foundation legs
# e.g., team must score in at least this fraction of recent matches
MIN_SCORING_RATE: float = float(os.getenv("MIN_SCORING_RATE", "0.50"))

# Minimum EV edge required to include a booster leg (ratio: soft_odds / pinnacle_odds - 1)
# Set to 0.0 to include any booster with positive or neutral EV; increase to be more selective.
BOOSTER_MIN_EV_EDGE: float = float(os.getenv("BOOSTER_MIN_EV_EDGE", "0.05"))

# Flat daily stake in USD used for ROI calculation
DAILY_STAKE_USD: float = float(os.getenv("DAILY_STAKE_USD", "10.0"))

# How many days ahead to generate tickets for (used by /upcoming and daily job)
LOOKAHEAD_DAYS: int = int(os.getenv("LOOKAHEAD_DAYS", "3"))

# Target leagues (sport_key format used by The Odds API)
TARGET_LEAGUES_ODDS_API: list[str] = [
    "soccer_epl",                    # English Premier League
    "soccer_spain_la_liga",          # La Liga
    "soccer_italy_serie_a",          # Serie A
    "soccer_germany_bundesliga",     # Bundesliga
    "soccer_france_ligue_one",       # Ligue 1
    "soccer_uefa_champs_league",     # UEFA Champions League (bonus)
]

# Target league IDs for API-Football (api-football.com)
TARGET_LEAGUES_API_FOOTBALL: dict[str, int] = {
    "EPL": 39,
    "La Liga": 140,
    "Serie A": 135,
    "Bundesliga": 78,
    "Ligue 1": 61,
    "Champions League": 2,
}

# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
# Daily ticket generation time (24-h format, UTC)
DAILY_SEND_HOUR: int = int(os.getenv("DAILY_SEND_HOUR", "9"))
DAILY_SEND_MINUTE: int = int(os.getenv("DAILY_SEND_MINUTE", "0"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "parifoot.db")
