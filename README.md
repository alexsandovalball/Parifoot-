# Parifoot 🤖⚽

A personal Telegram bot that analyses real-time soccer data and bookmaker odds from top European leagues to construct a **daily accumulator/parlay ticket targeting combined odds of 10.0–12.0**.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Tech Stack & APIs](#tech-stack--apis)
3. [Setup & Installation](#setup--installation)
4. [Configuration](#configuration)
5. [Running the Bot](#running-the-bot)
6. [Bot Commands](#bot-commands)
7. [Algorithm Overview](#algorithm-overview)
8. [Project Structure](#project-structure)
9. [Deployment (Production)](#deployment-production)

---

## Architecture

```
config.py       – Centralised environment-variable configuration
api_client.py   – Async HTTP wrappers (The Odds API + API-Football)
algorithm.py    – Core accumulator-building algorithm
database.py     – SQLite persistence (tickets, legs, results)
bot.py          – Telegram bot handlers + daily scheduler
```

---

## Tech Stack & APIs

| Concern          | Tool / Library                                |
|-----------------|-----------------------------------------------|
| Language         | Python 3.10+                                  |
| Telegram         | `python-telegram-bot` v21 (async, JobQueue)   |
| HTTP             | `httpx` (async, retry, timeout)               |
| Data             | `pandas`, `numpy`                             |
| Database         | SQLite (via stdlib `sqlite3`)                 |
| Environment      | `python-dotenv`                               |
| Odds data        | [The Odds API](https://the-odds-api.com/)     |
| Stats / fixtures | [API-Football](https://www.api-football.com/) |

---

## Setup & Installation

### Prerequisites

- Python 3.10 or higher
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A free-tier (or paid) key from [The Odds API](https://the-odds-api.com/)
- A free-tier (or paid) key from [API-Football](https://rapidapi.com/api-sports/api/api-football)

### 1 – Clone the repository

```bash
git clone https://github.com/alexsandovalball/Parifoot-.git
cd Parifoot-
```

### 2 – Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate.bat     # Windows
```

### 3 – Install dependencies

```bash
pip install -r requirements.txt
```

### 4 – Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your API keys and Telegram credentials
```

---

## Configuration

All settings live in `.env` (loaded by `config.py`):

| Variable             | Required | Description                                               |
|---------------------|----------|-----------------------------------------------------------|
| `TELEGRAM_BOT_TOKEN` | ✅       | Token from @BotFather                                     |
| `TELEGRAM_CHAT_ID`   | ✅       | Your chat ID (send `/start` to @userinfobot)              |
| `ODDS_API_KEY`       | ✅       | The Odds API key                                          |
| `API_FOOTBALL_KEY`   | ✅       | API-Football key                                          |
| `TARGET_ODDS_MIN`    | ❌       | Min target combined odds (default `10.0`)                 |
| `TARGET_ODDS_MAX`    | ❌       | Max target combined odds (default `12.0`)                 |
| `FOUNDATION_ODDS_MIN`| ❌       | Min per-leg odds for foundation legs (default `1.15`)     |
| `FOUNDATION_ODDS_MAX`| ❌       | Max per-leg odds for foundation legs (default `1.50`)     |
| `BOOSTER_ODDS_MIN`   | ❌       | Min per-leg odds for booster leg (default `2.00`)         |
| `BOOSTER_ODDS_MAX`   | ❌       | Max per-leg odds for booster leg (default `3.00`)         |
| `FOUNDATION_LEGS_MIN`| ❌       | Minimum foundation legs (default `4`)                     |
| `FOUNDATION_LEGS_MAX`| ❌       | Maximum foundation legs (default `6`)                     |
| `BOOSTER_LEGS_COUNT` | ❌       | Number of booster legs (default `1`)                      |
| `MIN_SCORING_RATE`   | ❌       | Minimum historical scoring rate 0–1 (default `0.70`)      |
| `DAILY_STAKE_USD`    | ❌       | Flat daily stake for ROI tracking (default `10.0`)        |
| `DAILY_SEND_HOUR`    | ❌       | UTC hour for the daily push (default `9`)                 |
| `DAILY_SEND_MINUTE`  | ❌       | UTC minute for the daily push (default `0`)               |
| `DATABASE_PATH`      | ❌       | SQLite file path (default `parifoot.db`)                  |

---

## Running the Bot

```bash
python bot.py
```

The bot will:
1. Initialise the SQLite database on first run.
2. Start polling Telegram for updates.
3. Schedule an automatic daily ticket push at `DAILY_SEND_HOUR:DAILY_SEND_MINUTE` UTC.

---

## Bot Commands

| Command            | Description                                      |
|-------------------|--------------------------------------------------|
| `/start`           | Welcome message and strategy overview            |
| `/today`           | Generate & display today's 10x ticket            |
| `/track win`       | Mark the latest ticket as a **win**              |
| `/track loss`      | Mark the latest ticket as a **loss**             |
| `/stats`           | Display all-time win rate, P&L, and ROI          |

### Example Ticket Output

```
⚽ Daily 10x Aggregation Ticket ⚽
📅 Date: 2025-08-15

🛡️ Foundation Legs (High Probability):
1️⃣ Manchester City vs Bournemouth – Over 1.5 Goals @ 1.22
2️⃣ Real Madrid vs Getafe – Double Chance 1X @ 1.18
3️⃣ Bayern Munich vs Freiburg – Over 1.5 Goals @ 1.28
4️⃣ Arsenal vs Wolves – Double Chance 1X @ 1.35

🚀 Booster Leg(s) (Value Pick):
5️⃣ Inter Milan vs Udinese – Home Win @ 2.20

📈 Total Combined Odds: 10.47
🏢 Recommended Bookmaker: Pinnacle
💰 Suggested Stake: Small / Residual Income only!
```

---

## Algorithm Overview

### Foundation Legs (High Probability)
- Target odds range: **1.15–1.50** per leg
- Markets considered:
  - **Over 1.5 Goals** – backed by H2H over-1.5 rate ≥ 70%
  - **Double Chance 1X** – for home favourites
  - **Double Chance X2** – for away favourites
- Pulls from EPL, La Liga, Serie A, Bundesliga, and Champions League only

### Booster Leg (Value Pick)
- Target odds range: **2.00–3.00** per leg
- Markets considered:
  - **Home Win** – cross-checked against Pinnacle odds for positive EV
  - **Both Teams to Score (BTTS)** – backed by H2H BTTS rate ≥ 70%

### Ticket Construction
1. All combinations of 4–6 foundation legs are evaluated.
2. For each combination, the product is checked against the required range to hit 10.0–12.0 combined with the booster.
3. The first valid combination is locked in.
4. If no exact solution exists, a relaxed search (up to 15x) returns the closest result.

---

## Project Structure

```
Parifoot-/
├── bot.py            # Telegram bot (handlers + scheduler)
├── algorithm.py      # Accumulator-building algorithm
├── api_client.py     # Async API wrappers
├── database.py       # SQLite ORM-lite layer
├── config.py         # Environment-variable configuration
├── requirements.txt  # Python dependencies
├── .env.example      # Environment template
└── README.md         # This file
```

---

## Deployment (Production)

### Option A – systemd service (Linux VPS)

Create `/etc/systemd/system/parifoot.service`:

```ini
[Unit]
Description=Parifoot Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/parifoot
ExecStart=/opt/parifoot/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10
EnvironmentFile=/opt/parifoot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now parifoot
sudo journalctl -u parifoot -f   # view logs
```

### Option B – Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t parifoot .
docker run -d --env-file .env --name parifoot parifoot
```

---

> ⚠️ **Disclaimer:** This bot is for educational and personal entertainment purposes only.
> Sports betting involves financial risk. Never stake more than you can afford to lose.
> Check the gambling laws in your jurisdiction before use.
