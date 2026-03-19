"""
algorithm.py – Core accumulator-building logic.

Strategy (Safe Aggregation)
---------------------------
Foundation legs  (3–6):  odds 1.10–1.70 each, statistically backed by
                          API-Football team stats / H2H.
Booster leg(s)   (1–2):  odds 1.50–4.00 each, positive EV cross-checked
                          against Pinnacle-style sharp bookmakers.
Target total             8.0–20.0 combined odds.
"""

import asyncio
import itertools
import logging
import math
from datetime import date, timedelta
from typing import Optional

import api_client
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

Leg = dict  # keys: match_name, market, odds, leg_type, league, bookmaker


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def build_10x_accumulator() -> Optional[dict]:
    """
    Fetch live data and attempt to construct a 10x accumulator ticket for today.

    Returns a dict with keys:
        legs         list[Leg]
        total_odds   float
        bookmaker    str
        date         date
    or None if no valid ticket could be constructed.
    """
    return await build_accumulator_for_date(date.today())


async def build_accumulator_for_date(target_date: date) -> Optional[dict]:
    """
    Build an accumulator ticket for *target_date*.

    Returns a ticket dict or None if no valid ticket could be constructed.
    """
    logger.info("Starting accumulator build for %s", target_date)

    # Fetch data concurrently
    odds_events, fixtures = await _fetch_data(target_date)

    if not odds_events and not fixtures:
        logger.error("No data available from APIs for %s – cannot build ticket", target_date)
        return None

    # Build candidate legs
    foundation_candidates = await get_foundation_legs(odds_events, fixtures)
    booster_candidates = await get_booster_legs(odds_events, fixtures)

    logger.info(
        "Candidates for %s – foundation: %d, booster: %d",
        target_date,
        len(foundation_candidates),
        len(booster_candidates),
    )

    ticket = _build_ticket(foundation_candidates, booster_candidates, target_date)
    if ticket is None:
        logger.warning("Could not construct a ticket within target odds window for %s", target_date)
    return ticket


async def build_3day_tickets() -> list[dict]:
    """
    Build accumulator tickets for today and the next LOOKAHEAD_DAYS-1 days.

    Returns a list of non-None ticket dicts (up to LOOKAHEAD_DAYS entries).
    Each ticket dict includes a 'date' key with the target date.
    """
    today = date.today()
    tickets: list[dict] = []
    for offset in range(config.LOOKAHEAD_DAYS):
        target_date = today + timedelta(days=offset)
        try:
            ticket = await build_accumulator_for_date(target_date)
        except Exception:
            logger.exception("Error building ticket for %s", target_date)
            ticket = None
        if ticket is not None:
            tickets.append(ticket)
    return tickets


async def get_foundation_legs(
    odds_events: list[dict],
    fixtures: list[dict],
) -> list[Leg]:
    """
    Find matches suitable for foundation legs.

    Criteria:
    - Odds between FOUNDATION_ODDS_MIN and FOUNDATION_ODDS_MAX
    - Markets: Over 1.5 Goals, Double Chance (1X / X2), Draw No Bet
    - Statistically backed by team scoring-rate / H2H data
    """
    candidates: list[Leg] = []

    # Index fixtures by home/away team name for quick lookup
    fixture_index = _index_fixtures(fixtures)

    for event in odds_events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        league = event.get("_sport_key", "")

        # ------------------------------------------------------------------
        # Market 1 – Over 1.5 Goals
        # ------------------------------------------------------------------
        over15_odds, bookmaker = api_client.extract_best_odds(event, "totals", "Over 1.5")
        if not over15_odds:
            # Fallback: look for generic "Over" in totals with point 1.5
            over15_odds, bookmaker = _extract_totals_at_point(event, "totals", "Over", 1.5)

        if config.FOUNDATION_ODDS_MIN <= over15_odds <= config.FOUNDATION_ODDS_MAX:
            # Verify statistically: check H2H over-1.5 rate
            h2h_key = _fixture_key(home, away)
            stat_ok = True
            if h2h_key in fixture_index:
                rate = api_client.compute_over15_rate(fixture_index[h2h_key])
                stat_ok = rate >= config.MIN_SCORING_RATE

            if stat_ok:
                candidates.append(
                    _make_leg(home, away, "Over 1.5 Goals", over15_odds, league, bookmaker, "foundation")
                )

        # ------------------------------------------------------------------
        # Market 2 – Double Chance 1X (home or draw)
        # ------------------------------------------------------------------
        dc1x_odds, dc1x_book = api_client.compute_double_chance_odds(event, "1X")
        if config.FOUNDATION_ODDS_MIN <= dc1x_odds <= config.FOUNDATION_ODDS_MAX:
            candidates.append(
                _make_leg(home, away, "Double Chance 1X", dc1x_odds, league, dc1x_book, "foundation")
            )

        # ------------------------------------------------------------------
        # Market 3 – Double Chance X2 (draw or away)
        # ------------------------------------------------------------------
        dcx2_odds, dcx2_book = api_client.compute_double_chance_odds(event, "X2")
        if config.FOUNDATION_ODDS_MIN <= dcx2_odds <= config.FOUNDATION_ODDS_MAX:
            candidates.append(
                _make_leg(home, away, "Double Chance X2", dcx2_odds, league, dcx2_book, "foundation")
            )

    # De-duplicate (same match, same market) and sort by odds ascending
    candidates = _deduplicate(candidates)
    candidates.sort(key=lambda x: x["odds"])
    logger.info("Foundation candidates after filtering: %d", len(candidates))
    return candidates


async def get_booster_legs(
    odds_events: list[dict],
    fixtures: list[dict],
) -> list[Leg]:
    """
    Find matches suitable for booster legs.

    Criteria:
    - Odds between BOOSTER_ODDS_MIN and BOOSTER_ODDS_MAX
    - Markets: Home Win, BTTS
    - EV cross-check: compare against Pinnacle (sharp) odds to ensure
      our chosen bookmaker is offering a positive edge.
    """
    candidates: list[Leg] = []
    fixture_index = _index_fixtures(fixtures)

    for event in odds_events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        league = event.get("_sport_key", "")

        # Pinnacle odds for EV baseline (sharp bookmaker)
        pinnacle_home = _get_pinnacle_odds(event, "h2h", home)

        # ------------------------------------------------------------------
        # Market 1 – Home Win (h2h)
        # ------------------------------------------------------------------
        home_odds, home_book = api_client.extract_best_odds(event, "h2h", home)
        if config.BOOSTER_ODDS_MIN <= home_odds <= config.BOOSTER_ODDS_MAX:
            # EV check: soft-book odds must beat Pinnacle by at least BOOSTER_MIN_EV_EDGE
            ev_ok = (pinnacle_home == 0.0) or (
                home_odds >= pinnacle_home * (1.0 + config.BOOSTER_MIN_EV_EDGE)
            )
            if ev_ok:
                candidates.append(
                    _make_leg(home, away, "Home Win", home_odds, league, home_book, "booster")
                )

        # ------------------------------------------------------------------
        # Market 2 – Both Teams to Score (BTTS)
        # btts is The Odds API's dedicated BTTS market key.
        # ------------------------------------------------------------------
        btts_odds, btts_book = api_client.extract_best_odds(event, "btts", "Yes")

        if config.BOOSTER_ODDS_MIN <= btts_odds <= config.BOOSTER_ODDS_MAX:
            pinnacle_btts = _get_pinnacle_odds(event, "btts", "Yes")
            h2h_key = _fixture_key(home, away)
            if pinnacle_btts > 0.0:
                # EV check: soft-book BTTS odds must beat Pinnacle by at least BOOSTER_MIN_EV_EDGE
                ev_ok = btts_odds >= pinnacle_btts * (1.0 + config.BOOSTER_MIN_EV_EDGE)
            else:
                # No Pinnacle reference – require a strong H2H BTTS rate instead
                ev_ok = False
                if h2h_key in fixture_index:
                    rate = api_client.compute_btts_rate(fixture_index[h2h_key])
                    ev_ok = rate >= config.MIN_SCORING_RATE + 0.15
            if ev_ok:
                candidates.append(
                    _make_leg(home, away, "Both Teams to Score", btts_odds, league, btts_book, "booster")
                )

    candidates = _deduplicate(candidates)
    # Sort by best EV proxy: highest odds (within booster range)
    candidates.sort(key=lambda x: x["odds"], reverse=True)
    logger.info("Booster candidates after filtering: %d", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Ticket construction
# ---------------------------------------------------------------------------

def _build_ticket(
    foundation_candidates: list[Leg],
    booster_candidates: list[Leg],
    target_date: date,
) -> Optional[dict]:
    """
    Try combinations of foundation legs (and optionally a booster leg) to find
    a ticket whose total odds fall within [TARGET_ODDS_MIN, TARGET_ODDS_MAX].

    Strategy:
    1. Always try foundation-only combos first (2–6 legs).
    2. If at least one booster candidate exists, also try foundation+booster
       combos. Keep the result only if it is a *better* ticket (closer to
       TARGET_ODDS_MIN from above) than the foundation-only result.
    3. Never require a booster – return the foundation-only ticket if no
       booster improves it.
    """
    n_foundation_min = config.FOUNDATION_LEGS_MIN
    n_foundation_max = min(config.FOUNDATION_LEGS_MAX, len(foundation_candidates))

    best_foundation_ticket: Optional[dict] = None

    # ------------------------------------------------------------------
    # Step 1: foundation-only search
    # ------------------------------------------------------------------
    for n in range(n_foundation_min, n_foundation_max + 1):
        for combo in itertools.combinations(
            foundation_candidates[: min(20, len(foundation_candidates))],
            n,
        ):
            match_names = [leg["match_name"] for leg in combo]
            if len(match_names) != len(set(match_names)):
                continue
            total = math.prod(leg["odds"] for leg in combo)
            if config.TARGET_ODDS_MIN <= total <= config.TARGET_ODDS_MAX:
                all_legs = list(combo)
                ticket = {
                    "legs": all_legs,
                    "total_odds": round(total, 4),
                    "bookmaker": _pick_best_bookmaker(all_legs),
                    "date": target_date,
                }
                # Keep the combo closest to TARGET_ODDS_MIN (lowest = safest)
                if best_foundation_ticket is None or total < best_foundation_ticket["total_odds"]:
                    best_foundation_ticket = ticket

    # ------------------------------------------------------------------
    # Step 2: optionally try foundation+booster combos
    # ------------------------------------------------------------------
    best_booster_ticket: Optional[dict] = None

    eligible_boosters = [
        b for b in booster_candidates if b["odds"] < config.TARGET_ODDS_MAX
    ]

    if eligible_boosters:
        n_boosters = config.BOOSTER_LEGS_COUNT
        for booster_combo in itertools.combinations(
            eligible_boosters[: min(10, len(eligible_boosters))],
            min(n_boosters, len(eligible_boosters)),
        ):
            booster_product = math.prod(b["odds"] for b in booster_combo)
            if booster_product > config.TARGET_ODDS_MAX:
                continue

            needed_min = config.TARGET_ODDS_MIN / booster_product
            needed_max = config.TARGET_ODDS_MAX / booster_product

            for n in range(n_foundation_min, n_foundation_max + 1):
                for combo in itertools.combinations(
                    foundation_candidates[: min(20, len(foundation_candidates))],
                    n,
                ):
                    match_names = (
                        [leg["match_name"] for leg in combo]
                        + [b["match_name"] for b in booster_combo]
                    )
                    if len(match_names) != len(set(match_names)):
                        continue
                    foundation_product = math.prod(leg["odds"] for leg in combo)
                    if needed_min <= foundation_product <= needed_max:
                        total = foundation_product * booster_product
                        all_legs = list(combo) + list(booster_combo)
                        ticket = {
                            "legs": all_legs,
                            "total_odds": round(total, 4),
                            "bookmaker": _pick_best_bookmaker(all_legs),
                            "date": target_date,
                        }
                        if best_booster_ticket is None or total < best_booster_ticket["total_odds"]:
                            best_booster_ticket = ticket

    # ------------------------------------------------------------------
    # Step 3: pick the best ticket (foundation preferred; booster only if better)
    # ------------------------------------------------------------------
    if best_foundation_ticket is not None and best_booster_ticket is not None:
        # Prefer whichever is closer to TARGET_ODDS_MIN (lower = safer)
        if best_booster_ticket["total_odds"] < best_foundation_ticket["total_odds"]:
            return best_booster_ticket
        return best_foundation_ticket
    if best_foundation_ticket is not None:
        return best_foundation_ticket
    if best_booster_ticket is not None:
        return best_booster_ticket

    # No exact window found – attempt a relaxed search (up to 25x)
    logger.info("Exact window not found – trying relaxed search")
    return _relaxed_build(foundation_candidates, booster_candidates, target_date)


def _relaxed_build(
    foundation_candidates: list[Leg],
    booster_candidates: list[Leg],
    target_date: date,
) -> Optional[dict]:
    """
    Last-resort: find the combination whose total odds are closest to
    TARGET_ODDS_MIN from above (up to 25x ceiling).

    Foundation-only is tried first; a booster is only included when it
    produces a better (safer) ticket.
    """
    RELAXED_MAX = 25.0
    best_ticket: Optional[dict] = None
    best_odds = float("inf")

    n_foundation_max = min(config.FOUNDATION_LEGS_MAX, len(foundation_candidates))

    # ------------------------------------------------------------------
    # Step 1: foundation-only relaxed search
    # ------------------------------------------------------------------
    for n in range(config.FOUNDATION_LEGS_MIN, n_foundation_max + 1):
        for combo in itertools.combinations(
            foundation_candidates[:15],
            n,
        ):
            match_names = [leg["match_name"] for leg in combo]
            if len(match_names) != len(set(match_names)):
                continue
            total = math.prod(leg["odds"] for leg in combo)
            if config.TARGET_ODDS_MIN <= total <= RELAXED_MAX:
                if total < best_odds:
                    best_odds = total
                    all_legs = list(combo)
                    best_ticket = {
                        "legs": all_legs,
                        "total_odds": round(total, 4),
                        "bookmaker": _pick_best_bookmaker(all_legs),
                        "date": target_date,
                    }

    # ------------------------------------------------------------------
    # Step 2: optionally try foundation+booster relaxed search
    # ------------------------------------------------------------------
    eligible_boosters = [b for b in booster_candidates if b["odds"] < RELAXED_MAX]

    if eligible_boosters:
        n_boosters = config.BOOSTER_LEGS_COUNT
        for booster_combo in itertools.combinations(
            eligible_boosters[: min(6, len(eligible_boosters))],
            min(n_boosters, len(eligible_boosters)),
        ):
            booster_product = math.prod(b["odds"] for b in booster_combo)
            for n in range(config.FOUNDATION_LEGS_MIN, n_foundation_max + 1):
                for combo in itertools.combinations(
                    foundation_candidates[:15],
                    n,
                ):
                    match_names = (
                        [leg["match_name"] for leg in combo]
                        + [b["match_name"] for b in booster_combo]
                    )
                    if len(match_names) != len(set(match_names)):
                        continue
                    total = math.prod(leg["odds"] for leg in combo) * booster_product
                    if config.TARGET_ODDS_MIN <= total <= RELAXED_MAX:
                        if total < best_odds:
                            best_odds = total
                            all_legs = list(combo) + list(booster_combo)
                            best_ticket = {
                                "legs": all_legs,
                                "total_odds": round(total, 4),
                                "bookmaker": _pick_best_bookmaker(all_legs),
                                "date": target_date,
                            }

    return best_ticket


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_data(target_date: date) -> tuple[list[dict], list[dict]]:
    odds_task = api_client.fetch_all_target_odds_for_date(target_date)
    fix_task = api_client.fetch_all_fixtures_for_date(target_date)
    odds_events, fixtures = await asyncio.gather(odds_task, fix_task, return_exceptions=True)
    if isinstance(odds_events, Exception):
        logger.error("Odds API error: %s", odds_events)
        odds_events = []
    if isinstance(fixtures, Exception):
        logger.error("Fixtures API error: %s", fixtures)
        fixtures = []
    return odds_events, fixtures


def _make_leg(
    home: str,
    away: str,
    market: str,
    odds: float,
    league: str,
    bookmaker: str,
    leg_type: str,
) -> Leg:
    return {
        "match_name": f"{home} vs {away}",
        "market": market,
        "odds": round(odds, 4),
        "league": league,
        "bookmaker": bookmaker,
        "leg_type": leg_type,
    }


def _index_fixtures(fixtures: list[dict]) -> dict[str, list[dict]]:
    """Create a lookup dict from fixture key to list of historical fixtures."""
    index: dict[str, list[dict]] = {}
    for f in fixtures:
        home = f.get("teams", {}).get("home", {}).get("name", "")
        away = f.get("teams", {}).get("away", {}).get("name", "")
        key = _fixture_key(home, away)
        index.setdefault(key, []).append(f)
    return index


def _fixture_key(home: str, away: str) -> str:
    return f"{home.lower().strip()}|{away.lower().strip()}"


def _deduplicate(legs: list[Leg]) -> list[Leg]:
    """Remove duplicate (match_name, market) combinations keeping highest odds."""
    seen: dict[tuple, Leg] = {}
    for leg in legs:
        key = (leg["match_name"], leg["market"])
        if key not in seen or leg["odds"] > seen[key]["odds"]:
            seen[key] = leg
    return list(seen.values())


def _get_pinnacle_odds(event: dict, market_key: str, outcome_name: str) -> float:
    """Return Pinnacle's odds for an outcome (0.0 if not available)."""
    for bm in event.get("bookmakers", []):
        if "pinnacle" in bm.get("title", "").lower():
            for mkt in bm.get("markets", []):
                if mkt["key"] != market_key:
                    continue
                for outcome in mkt.get("outcomes", []):
                    if outcome["name"].lower() == outcome_name.lower():
                        return float(outcome["price"])
    return 0.0


def _pick_best_bookmaker(legs: list[Leg]) -> str:
    """Return the most frequently cited bookmaker across the legs."""
    from collections import Counter
    books = [leg.get("bookmaker", "") for leg in legs if leg.get("bookmaker")]
    if not books:
        return "Best Available"
    return Counter(books).most_common(1)[0][0]


def _extract_totals_at_point(
    event: dict,
    market_key: str,
    outcome_name: str,
    point: float,
) -> tuple[float, str]:
    """
    Some APIs include the handicap/point in the outcome.
    This helper finds Over/Under at a specific point value.
    """
    best_odds = 0.0
    best_book = ""
    for bm in event.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt["key"] != market_key:
                continue
            for outcome in mkt.get("outcomes", []):
                name_match = outcome["name"].lower() == outcome_name.lower()
                point_match = abs(float(outcome.get("point", -999)) - point) < 0.01
                if name_match and point_match and outcome["price"] > best_odds:
                    best_odds = outcome["price"]
                    best_book = bm["title"]
    return best_odds, best_book
