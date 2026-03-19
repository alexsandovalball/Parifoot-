"""
bot.py – Telegram bot entry-point.

Commands
--------
/start          Welcome message and strategy overview.
/today          Generate and display today's 10x accumulator ticket.
/upcoming       Generate and display tickets for the next 3 days.
/track <win|loss>
                Mark yesterday's ticket result in the database.
/stats          Display all-time tracking statistics.

The JobQueue fires the daily ticket automatically at 09:00 UTC.
"""

import logging
import os
from datetime import date, time as dt_time, timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    JobQueue,
)

import algorithm
import config
import database

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message formatting helpers
# ---------------------------------------------------------------------------

_NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]


def _day_label(ticket_date: date) -> str:
    """Return a human-readable day label relative to today."""
    today = date.today()
    delta = (ticket_date - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    return ticket_date.strftime("%A, %d %b")


def _format_ticket(ticket: dict, day_label: str | None = None) -> str:
    """Render a ticket dict as a Telegram HTML-formatted message."""
    legs = ticket["legs"]
    foundation = [l for l in legs if l["leg_type"] == "foundation"]
    boosters = [l for l in legs if l["leg_type"] == "booster"]

    lines: list[str] = []
    if day_label:
        lines.append(f"📅 <b>{_escape(day_label)}</b>")
    lines.append("⚽ <b>Daily 10x Aggregation Ticket</b> ⚽")
    lines.append(f"📅 <b>Date:</b> {ticket['date']}")
    lines.append("")

    # Foundation legs
    lines.append("🛡️ <b>Foundation Legs (High Probability):</b>")
    idx = 0
    for leg in foundation:
        emoji = _NUMBER_EMOJIS[idx] if idx < len(_NUMBER_EMOJIS) else f"{idx + 1}."
        lines.append(
            f"{emoji} {_escape(leg['match_name'])} – "
            f"{_escape(leg['market'])} @ <b>{leg['odds']:.2f}</b>"
        )
        idx += 1
    lines.append("")

    # Booster leg(s)
    lines.append("🚀 <b>Booster Leg(s) (Value Pick):</b>")
    for leg in boosters:
        emoji = _NUMBER_EMOJIS[idx] if idx < len(_NUMBER_EMOJIS) else f"{idx + 1}."
        lines.append(
            f"{emoji} {_escape(leg['match_name'])} – "
            f"{_escape(leg['market'])} @ <b>{leg['odds']:.2f}</b>"
        )
        idx += 1
    lines.append("")

    # Summary
    lines.append(f"📈 <b>Total Combined Odds:</b> {ticket['total_odds']:.2f}")
    lines.append(f"🏢 <b>Recommended Bookmaker:</b> {_escape(ticket['bookmaker'])}")
    lines.append("💰 <b>Suggested Stake:</b> Small / Residual Income only!")
    lines.append("")
    lines.append("⚠️ <i>Gambling involves risk. Only stake what you can afford to lose.</i>")

    return "\n".join(lines)


def _escape(text: str) -> str:
    """Minimal HTML escaping for Telegram HTML mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "⚽ <b>Welcome to Parifoot – your daily 10x accumulator bot!</b>\n\n"
        "📋 <b>Strategy: Safe Aggregation</b>\n"
        "Instead of guessing, the bot compounds <i>high-probability, low-odds</i> "
        "selections (Over 1.5 Goals, Double Chance, Draw No Bet) from the top 5 "
        "European leagues with 4–6 foundation legs (each @ 1.15–1.50).\n\n"
        "A single <i>value booster</i> leg (@ 2.00–3.00) cross-checked for positive "
        "Expected Value pushes the total past 10.0.\n\n"
        "<b>Commands:</b>\n"
        "• /today – Generate today's ticket\n"
        "• /upcoming – Tickets for the next 3 days\n"
        "• /track win|loss – Record yesterday's result\n"
        "• /stats – All-time hit rate &amp; ROI\n\n"
        "⚠️ <i>For educational purposes. Gamble responsibly.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔄 <i>Fetching live odds and statistics… this may take a moment.</i>",
        parse_mode=ParseMode.HTML,
    )
    try:
        ticket = await algorithm.build_10x_accumulator()
    except Exception:
        logger.exception("Error building accumulator")
        await update.message.reply_text(
            "❌ <b>Failed to generate ticket.</b> Please try again later.",
            parse_mode=ParseMode.HTML,
        )
        return

    if ticket is None:
        await update.message.reply_text(
            "😔 <b>No valid ticket could be constructed today.</b>\n"
            "Try again later when more fixtures are available.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Persist to DB
    database.save_ticket(
        ticket_date=ticket["date"],
        total_odds=ticket["total_odds"],
        bookmaker=ticket["bookmaker"],
        legs=ticket["legs"],
    )

    await update.message.reply_text(
        _format_ticket(ticket),
        parse_mode=ParseMode.HTML,
    )


async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔄 <i>Fetching upcoming tickets for the next 3 days… this may take a moment.</i>",
        parse_mode=ParseMode.HTML,
    )
    try:
        tickets = await algorithm.build_3day_tickets()
    except Exception:
        logger.exception("Error building upcoming tickets")
        await update.message.reply_text(
            "❌ <b>Failed to generate upcoming tickets.</b> Please try again later.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not tickets:
        await update.message.reply_text(
            "😔 <b>No valid tickets found for the next 3 days.</b>\n"
            "Try again later when more fixtures are available.",
            parse_mode=ParseMode.HTML,
        )
        return

    for ticket in tickets:
        label = _day_label(ticket["date"])
        database.save_ticket(
            ticket_date=ticket["date"],
            total_odds=ticket["total_odds"],
            bookmaker=ticket["bookmaker"],
            legs=ticket["legs"],
        )
        await update.message.reply_text(
            _format_ticket(ticket, day_label=label),
            parse_mode=ParseMode.HTML,
        )


async def cmd_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: /track <code>win</code> or /track <code>loss</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    outcome = context.args[0].lower()
    if outcome not in ("win", "loss"):
        await update.message.reply_text(
            "❌ Please specify <code>win</code> or <code>loss</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    result = database.record_result(outcome)
    if result is None:
        await update.message.reply_text(
            "😕 No ticket found in the database to track. Use /today first.",
            parse_mode=ParseMode.HTML,
        )
        return

    emoji = "🏆" if outcome == "win" else "😔"
    sign = "+" if result["pnl_usd"] >= 0 else ""
    await update.message.reply_text(
        f"{emoji} Ticket #{result['ticket_id']} recorded as <b>{outcome.upper()}</b>.\n"
        f"P&amp;L: <b>{sign}${result['pnl_usd']:.2f}</b> "
        f"(stake: ${config.DAILY_STAKE_USD:.2f})",
        parse_mode=ParseMode.HTML,
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = database.get_stats()
    pnl_sign = "+" if stats["net_pnl"] >= 0 else ""
    roi_sign = "+" if stats["roi"] >= 0 else ""
    text = (
        "📊 <b>All-Time Statistics</b>\n\n"
        f"🎟️ Total Tickets:  <b>{stats['total_tickets']}</b>\n"
        f"✅ Wins:           <b>{stats['wins']}</b>\n"
        f"❌ Losses:         <b>{stats['losses']}</b>\n"
        f"🎯 Hit Rate:       <b>{stats['hit_rate']}%</b>\n"
        f"💵 Total Staked:   <b>${stats['total_staked']:.2f}</b>\n"
        f"💰 Net P&amp;L:       <b>{pnl_sign}${stats['net_pnl']:.2f}</b>\n"
        f"📈 ROI:            <b>{roi_sign}{stats['roi']}%</b>\n\n"
        f"<i>Assuming ${config.DAILY_STAKE_USD:.2f} flat stake per ticket.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Daily scheduled job
# ---------------------------------------------------------------------------

async def _daily_ticket_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job: generate and push upcoming tickets to the owner chat."""
    logger.info("Running daily scheduled ticket generation")
    try:
        tickets = await algorithm.build_3day_tickets()
    except Exception:
        logger.exception("Scheduled job error")
        await context.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text="❌ <b>Scheduled ticket failed.</b> Please check the bot logs.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not tickets:
        await context.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=(
                "😔 <b>Daily Ticket – No valid tickets for the next 3 days.</b>\n"
                "No qualifying fixtures found. Try /today or /upcoming later."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    for ticket in tickets:
        label = _day_label(ticket["date"])
        database.save_ticket(
            ticket_date=ticket["date"],
            total_odds=ticket["total_odds"],
            bookmaker=ticket["bookmaker"],
            legs=ticket["legs"],
        )
        await context.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=_format_ticket(ticket, day_label=label),
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

def create_application() -> Application:
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("track", cmd_track))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Schedule daily ticket
    job_queue: JobQueue = app.job_queue
    job_queue.run_daily(
        _daily_ticket_job,
        time=dt_time(
            hour=config.DAILY_SEND_HOUR,
            minute=config.DAILY_SEND_MINUTE,
            tzinfo=timezone.utc,
        ),
        name="daily_ticket",
    )

    return app


def main() -> None:
    database.init_db()
    app = create_application()

    render_url = os.getenv("RENDER_EXTERNAL_URL")
    port = int(os.getenv("PORT", "8080"))

    if render_url:
        webhook_url = f"{render_url}/webhook"
        logger.info("Parifoot bot starting – webhook mode at %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("Parifoot bot starting – polling for updates…")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
