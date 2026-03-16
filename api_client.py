"""
api_client.py – Async wrappers around The Odds API and API-Football.

All network calls use httpx with proper timeout/retry handling so the bot
stays resilient under rate-limit pressure.
"""

import asyncio
import logging
from datetime import date, timezone, datetime
from typing import Any, Optional

import httpx

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared HTTP client configuration
# ---------------------------------------------------------------------------
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_RETRIES = 3
_BACKOFF_BASE = 2.0  # seconds


async def _get(url: str, params: dict, headers: dict | None = None) -> Any:
    """GET with exponential-backoff retry for transient errors and rate limits."""
    for attempt in range(1, _RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url, params=params, headers=headers or {})
            if resp.status_code == 429:
                wait = _BACKOFF_BASE ** attempt
                logger.warning("Rate limited by %s – waiting %.0fs", url, wait)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %s from %s: %s", exc.response.status_code, url, exc)
            if attempt == _RETRIES:
                raise
            await asyncio.sleep(_BACKOFF_BASE ** attempt)
        except httpx.RequestError as exc:
            logger.error("Request error for %s: %s", url, exc)
            if attempt == _RETRIES:
                raise
            await asyncio.sleep(_BACKOFF_BASE ** attempt)
    return None  # unreachable, but satisfies type checkers


# ===========================================================================
# The Odds API
# ===========================================================================
_ODDS_BASE = "https://api.the-odds-api.com/v4"


async def fetch_odds(sport: str, markets: str = "h2h,totals") -> list[dict]:
    """
    Fetch live odds for a sport from The Odds API.

    Returns a list of event dicts as returned by the API.
    Each event includes bookmaker odds for the requested markets.
    """
    url = f"{_ODDS_BASE}/sports/{sport}/odds"
    params = {
        "apiKey": config.ODDS_API_KEY,
        "regions": "eu,uk",       # European / UK bookmakers incl. Pinnacle
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    data = await _get(url, params)
    if not isinstance(data, list):
        logger.warning("Unexpected odds response for %s: %s", sport, type(data))
        return []
    logger.info("Fetched %d events for sport=%s", len(data), sport)
    return data


async def fetch_all_target_odds() -> list[dict]:
    """
    Fetch odds for every target league concurrently and merge results.
    """
    tasks = [fetch_odds(sport) for sport in config.TARGET_LEAGUES_ODDS_API]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    events: list[dict] = []
    for sport, result in zip(config.TARGET_LEAGUES_ODDS_API, results):
        if isinstance(result, Exception):
            logger.error("Failed to fetch odds for %s: %s", sport, result)
        else:
            for event in result:
                event["_sport_key"] = sport
            events.extend(result)
    return events


def extract_best_odds(event: dict, market_key: str, outcome_name: str) -> tuple[float, str]:
    """
    Scan all bookmakers in the event and return (best_decimal_odds, bookmaker_name).

    market_key:    'h2h' | 'totals' | 'spreads'
    outcome_name:  e.g. 'Over', 'Under', home-team name, away-team name, 'Draw'
    """
    best_odds = 0.0
    best_book = ""
    for bm in event.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt["key"] != market_key:
                continue
            for outcome in mkt.get("outcomes", []):
                if outcome["name"].lower() == outcome_name.lower():
                    if outcome["price"] > best_odds:
                        best_odds = outcome["price"]
                        best_book = bm["title"]
    return best_odds, best_book


def extract_double_chance_odds(event: dict, dc_type: str) -> tuple[float, str]:
    """
    Extract Double Chance odds (1X or X2) from bookmakers.

    dc_type: '1X' or 'X2'
    """
    return extract_best_odds(event, "h2h", dc_type)


# ===========================================================================
# API-Football
# ===========================================================================
_APIFB_BASE = "https://v3.football.api-sports.io"


def _apifb_headers() -> dict:
    return {"x-apisports-key": config.API_FOOTBALL_KEY}


async def fetch_fixtures_today(league_id: int, season: int | None = None) -> list[dict]:
    """
    Return today's fixtures for a given API-Football league id.
    """
    if season is None:
        season = _current_season()
    today_str = date.today().isoformat()
    data = await _get(
        f"{_APIFB_BASE}/fixtures",
        params={
            "league": league_id,
            "season": season,
            "date": today_str,
            "timezone": "UTC",
        },
        headers=_apifb_headers(),
    )
    fixtures = data.get("response", []) if isinstance(data, dict) else []
    logger.info("Fetched %d fixtures for league_id=%s date=%s", len(fixtures), league_id, today_str)
    return fixtures


async def fetch_all_fixtures_today() -> list[dict]:
    """
    Fetch today's fixtures for every target league concurrently.
    """
    season = _current_season()
    tasks = [
        fetch_fixtures_today(league_id, season)
        for league_id in config.TARGET_LEAGUES_API_FOOTBALL.values()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    fixtures: list[dict] = []
    for league_name, result in zip(config.TARGET_LEAGUES_API_FOOTBALL, results):
        if isinstance(result, Exception):
            logger.error("Failed to fetch fixtures for %s: %s", league_name, result)
        else:
            for f in result:
                f["_league_name"] = league_name
            fixtures.extend(result)
    return fixtures


async def fetch_team_stats(team_id: int, league_id: int, season: int | None = None) -> Optional[dict]:
    """
    Return the team statistics object from API-Football.
    Contains form, goals, fixtures counts, etc.
    """
    if season is None:
        season = _current_season()
    data = await _get(
        f"{_APIFB_BASE}/teams/statistics",
        params={"team": team_id, "league": league_id, "season": season},
        headers=_apifb_headers(),
    )
    if not isinstance(data, dict):
        return None
    return data.get("response")


async def fetch_head_to_head(team1_id: int, team2_id: int, last: int = 10) -> list[dict]:
    """
    Return the last N head-to-head fixtures between two teams.
    """
    data = await _get(
        f"{_APIFB_BASE}/fixtures/headtohead",
        params={"h2h": f"{team1_id}-{team2_id}", "last": last},
        headers=_apifb_headers(),
    )
    if not isinstance(data, dict):
        return []
    return data.get("response", [])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_season() -> int:
    """Return the current football season year (e.g. 2024 for 2024/25)."""
    now = datetime.now(tz=timezone.utc)
    # Seasons start in July/August – if we are in Jan-Jun we are still in the
    # previous calendar year's season.
    return now.year if now.month >= 7 else now.year - 1


def compute_btts_rate(h2h_fixtures: list[dict]) -> float:
    """
    Given a list of head-to-head fixture objects (API-Football format),
    return the fraction of games where Both Teams Scored.
    """
    if not h2h_fixtures:
        return 0.0
    btts = sum(
        1
        for f in h2h_fixtures
        if (
            f.get("score", {}).get("fulltime", {}).get("home", 0) or 0
        ) > 0
        and (
            f.get("score", {}).get("fulltime", {}).get("away", 0) or 0
        ) > 0
    )
    return btts / len(h2h_fixtures)


def compute_over15_rate(fixtures: list[dict]) -> float:
    """
    Return the fraction of games where total goals > 1.5 (i.e., >= 2 goals).
    Works with API-Football fixture objects.
    """
    if not fixtures:
        return 0.0
    over = sum(
        1
        for f in fixtures
        if (
            (f.get("score", {}).get("fulltime", {}).get("home") or 0)
            + (f.get("score", {}).get("fulltime", {}).get("away") or 0)
        ) >= 2
    )
    return over / len(fixtures)
