# A1 Trading Bot

A paper-first Alpaca swing-trading bot with an authenticated local dashboard. It evaluates a
starter universe every 15 minutes during regular US market hours, using hourly trend and momentum
signals. It is intentionally conservative, explainable, and **incapable of selecting Alpaca's live
endpoint**.

> This project is educational software, not investment advice. Paper fills do not model every
> source of live-trading cost or risk, and profitable backtests can fail in live markets.

## What the first milestone includes

- Alpaca paper-account connection using the official Python SDK and free IEX data
- long-only US stocks and ETFs; no options, crypto, shorting, margin, or extended-hours orders
- a transparent 20/50-hour EMA, RSI, volume, and momentum baseline strategy
- fractional paper orders sized against a capped `$2,000` virtual allocation
- 1% risk budget per trade, 20% position cap, four-position cap
- 3% daily-loss and 10% drawdown circuit breakers
- manual pause, manual run, and emergency stop that cancels open orders
- manual confirmation phrase before restarting after an emergency stop
- password-protected, phone-responsive dashboard
- SQLite history for equity, signals, events, and managed positions
- Discord webhook notifications
- six-month backtest with configurable slippage
- downloadable current-month CSV performance report

The bot starts **paused** on every new database. It cannot place an order until you add paper keys,
set strong local secrets, sign in, test the connection, and press **Start bot**.

## Beginner setup on Windows

1. Install [Python 3.12](https://www.python.org/downloads/) and Git.
2. In Alpaca, create a dedicated paper account. A `$2,000` starting balance is easiest to interpret;
   if the paper account has a larger balance, the bot still limits its allocation to `$2,000`.
3. Clone this repository and open PowerShell inside it.
4. Run `./start.ps1`. The first run creates `.env` and stops.
5. Open `.env` and enter **paper-account** keys. Change the dashboard password and use a random
   session secret at least 32 characters long. Never paste keys into chat or commit `.env`.
6. Run `./start.ps1` again, then open <http://127.0.0.1:8000>.
7. Sign in, click **Test connection**, review the settings, run a backtest, then start the bot.

Generate a session secret in PowerShell:

```powershell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
```

### Docker alternative

After creating `.env`:

```powershell
docker compose up --build -d
```

Open <http://127.0.0.1:8000>. Data is stored in the local `data/` directory.

## Viewing it on your phone

Set `HOST=0.0.0.0` in `.env`, start Uvicorn with `--host 0.0.0.0`, allow the private-network
Windows Firewall prompt, and visit `http://YOUR-COMPUTER-LAN-IP:8000` while both devices are on the
same trusted Wi-Fi. Do **not** forward port 8000 from your router or expose this development server
to the public internet.

## Strategy in plain English

Every scheduled check, the bot downloads roughly 90 days of hourly bars from Alpaca's free IEX
feed. A symbol becomes an entry candidate when:

1. its 20-hour exponential moving average is above its 50-hour average;
2. price remains above the faster average;
3. five-hour momentum is positive;
4. RSI is between 50 and 70; and
5. the latest volume is at least 70% of its recent average.

Candidates are ranked by trend strength, momentum, RSI, and volume. Position size is the smaller
of the concentration cap and the amount implied by the ATR stop distance and risk budget. Exits use
software-checked ATR stop/target levels plus a trend-break signal after the minimum hold period.

**Important:** software stops are only checked on a cycle and are not broker-resident stop orders.
That is acceptable for this paper-learning stage, but it is not sufficient for live money.

## Safety model

- `TradingClient(..., paper=True)` is hard-coded; there is no live-mode environment switch.
- Orders set `extended_hours=False` and the engine checks Alpaca's regular-hours clock.
- New entries stop 30 minutes before the close.
- The engine uses cash for sizing instead of buying power, avoiding intentional margin use.
- Any unhandled cycle error pauses the bot and generates a dashboard/Discord event.
- Circuit breakers pause the bot, set the emergency flag, and cancel open orders.
- Emergency stop does not liquidate existing positions; it prevents a panic button from generating
  irreversible market sells.
- Existing paper positions not opened by this bot are displayed but not automatically closed.

Use a dedicated Alpaca paper account. Manual trades in the same account can distort the virtual
allocation and circuit-breaker calculations.

## Commands for developers

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

See [Architecture](docs/ARCHITECTURE.md), [Security](docs/SECURITY.md), and the
[Roadmap](docs/ROADMAP.md) for the rationale and next milestones.

