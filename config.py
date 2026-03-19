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
TARGET_ODDS_MIN: float = float(os.getenv("TARGET_ODDS_MIN", "10.0"))
TARGET_ODDS_MAX: float = float(os.getenv("TARGET_ODDS_MAX", "12.0"))

# Foundation legs – odds range per leg
FOUNDATION_ODDS_MIN: float = float(os.getenv("FOUNDATION_ODDS_MIN", "1.15"))
FOUNDATION_ODDS_MAX: float = float(os.getenv("FOUNDATION_ODDS_MAX", "1.50"))

# Booster legs – odds range per leg
BOOSTER_ODDS_MIN: float = float(os.getenv("BOOSTER_ODDS_MIN", "2.00"))
BOOSTER_ODDS_MAX: float = float(os.getenv("BOOSTER_ODDS_MAX", "3.00"))

# How many foundation and booster legs to aim for
FOUNDATION_LEGS_MIN: int = int(os.getenv("FOUNDATION_LEGS_MIN", "4"))
FOUNDATION_LEGS_MAX: int = int(os.getenv("FOUNDATION_LEGS_MAX", "6"))
BOOSTER_LEGS_COUNT: int = int(os.getenv("BOOSTER_LEGS_COUNT", "1"))

# Minimum statistical threshold for foundation legs
# e.g., team must score in at least this fraction of recent matches
MIN_SCORING_RATE: float = float(os.getenv("MIN_SCORING_RATE", "0.70"))

# Flat daily stake in USD used for ROI calculation
DAILY_STAKE_USD: float = float(os.getenv("DAILY_STAKE_USD", "10.0"))

# Target leagues (sport_key format used by The Odds API)
TARGET_LEAGUES_ODDS_API: list[str] = [
    "soccer_epl",             # English Premier League
    "soccer_spain_la_liga",   # La Liga
    "soccer_italy_serie_a",   # Serie A
    "soccer_germany_bundesliga",  # Bundesliga
    "soccer_uefa_champs_league",  # UEFA Champions League
]

# Target league IDs for API-Football (api-football.com)
TARGET_LEAGUES_API_FOOTBALL: dict[str, int] = {
    "EPL": 39,
    "La Liga": 140,
    "Serie A": 135,
    "Bundesliga": 78,
    "Champions League": 2,
}

# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
# Daily ticket generation time (24-h format, UTC) – kept for backwards compatibility
DAILY_SEND_HOUR: int = int(os.getenv("DAILY_SEND_HOUR", "9"))
DAILY_SEND_MINUTE: int = int(os.getenv("DAILY_SEND_MINUTE", "0"))

# Interval between automatic ticket generations in seconds (default: 1 hour)
TICKET_INTERVAL_SECONDS: int = int(os.getenv("TICKET_INTERVAL_SECONDS", "3600"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "parifoot.db")
