# Roadmap

## Milestone 1 — paper baseline (this pull request)

- local authenticated dashboard
- explainable long-only swing strategy
- paper orders, history, backtesting, Discord notifications, and circuit breakers
- tests and beginner documentation

## Milestone 2 — evidence and reliability

- run paper trading long enough to cover different market conditions
- add order/fill reconciliation and explicit pending-order state
- add broker-native protective orders where fractional-order behavior is verified
- add walk-forward backtests, benchmark comparison against SPY, exposure metrics, and downloadable
  monthly reports
- add structured logs, database backups, and simulated disconnect/retry tests

## Milestone 3 — machine-learning research

- create a leakage-resistant feature pipeline and time-series splits
- compare logistic regression and tree-based models against the unchanged baseline
- require out-of-sample improvement after slippage, not just raw training accuracy
- log model version and features behind every decision
- retrain only after data validation, with automatic rollback and drift monitoring

No ML model should place orders merely because it performs well in-sample.

## Milestone 4 — optional Schwab read-only adapter

- obtain official developer access and confirm current API capabilities
- implement account, positions, orders, and market-data reads only
- run side-by-side reconciliation without order permission

## Milestone 5 — separately approved live pilot

Only after stable paper evidence and a specific owner decision: independent review, broker-side risk
controls, manual deployment approval, explicit live-mode build, tiny capital allocation, and a staged
rollout. Live mode should never be unlocked by changing one environment variable.

