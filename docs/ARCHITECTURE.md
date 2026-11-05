# Architecture

The first release is a single local Python service. One process is easier to understand and operate
than separate frontend, API, worker, and database deployments, while still leaving clean boundaries
for later broker and strategy additions.

```text
Browser dashboard
       │ authenticated JSON
       ▼
FastAPI application ─── SQLite history
       │
       ├── APScheduler (checks every minute; respects configured 15-minute cadence)
       ├── baseline strategy (pure calculation)
       ├── risk engine (pure calculation)
       ├── Discord notifier
       └── AlpacaPaperBroker
              ├── Trading API, hard-coded paper=True
              └── Market Data API, IEX hourly bars
```

## Important boundaries

- `alpaca_adapter.py` is the only code that knows the Alpaca SDK. A future Schwab adapter should
  implement a matching interface without modifying strategy calculations.
- `strategy.py`, `risk.py`, and `backtest.py` are broker-independent and testable without secrets.
- `trader.py` orchestrates state transitions and owns the order policy.
- `database.py` stores only non-secret operational data. Credentials remain environment variables.
- `static/` is a buildless dashboard, avoiding a Node toolchain for a beginner-run local service.

## Why the bot checks every 15 minutes but uses hourly bars

The requested style is swing trading rather than frequent day trading. Hourly features reduce noise
relative to 15-minute signals, while a 15-minute engine cadence notices fills, stops, and market
state sooner. It intentionally does not attempt high-frequency execution.

## Virtual allocation

Alpaca paper accounts may have more than `$2,000`. The engine records account equity at first run,
then treats later account P/L as changes to a capped virtual allocation. Concentration and risk
budgets use the virtual value, not the account's potentially much larger buying power.

