# OPINION — Gold & Silver Market Intelligence

Local-first, ₹0-budget Gold & Silver market intelligence dashboard for Indian investors.

## What this is

A Dash dashboard that fetches Gold and Silver **FUTURES** prices (GC=F, SI=F via Yahoo Finance), builds forecasts using 5 statistical/ML models, grades forecast accuracy against observed prices, and provides a news intelligence feed. All processing is local; no paid APIs, no cloud.

## What this is NOT

- Not a trading system. Does not execute trades or manage funds.
- Not a spot-price system. GC=F and SI=F are FUTURES contracts, not spot prices.
- Does not contain FinBERT or any NLP embedding model (planned for a future stage).
- Does not contain a BUY/HOLD/SELL signal engine (planned for a future stage).
- Does not contain a REST/HTTP API (planned for a future stage).
- Models are re-trained from scratch on each forecast run. No persisted model weights.

## Features

- India/INR-first pricing
- XAU/XAG in USD and INR (INR is DERIVED: futures price × USD/INR)
- 5 FX pairs: USD/INR, EUR/INR, CNY/INR, JPY/INR, CHF/INR
- 5 forecast horizons: +1h, +5h, +12h, +24h, +48h
- 5 forecasting models: Naive, AutoARIMA, AutoETS, Theta (statsforecast), XGBoost+FX
- Walk-forward backtesting; best model selected per asset × horizon
- Immutable forecast history and append-only audit tables
- +3/−6 scoring (market data only — LLM excluded from scoring)
- **8 dashboard pages**
- Local Ollama LLM (configurable, optional — for news analysis only)
- No paid APIs, no cloud, no subscriptions

## Price Labels

| Label | Meaning |
|-------|---------|
| `FUTURES` | COMEX futures contract (GC=F, SI=F via yfinance) |
| `DERIVED` | Computed cross-price (XAU/INR = XAU/USD_futures × USD/INR) |
| `UNAVAILABLE` | No verified free source available |

GC=F and SI=F are **FUTURES contracts**. Never displayed as spot prices.

## Data Quality States

| State | Meaning |
|-------|---------|
| `LIVE` | Freshly fetched, passes validation |
| `STALE` | From cache, older than refresh interval |
| `UNAVAILABLE` | All providers failed or no free source exists |
| `ERROR` | Data failed validation |

## Dashboard Pages

1. **Overview** (`/`) — INR-first Gold and Silver prices, FX rates table
2. **Metals** (`/metals`) — Hourly candlestick chart, MA-20/MA-50 technicals
3. **Markets** (`/markets`) — International prices, FX chart, historical data
4. **Analytics** (`/analytics`) — Currency influence heatmap, walk-forward backtest runner
5. **Forecasts** (`/forecasts`) — Run forecasts, grade outcomes, audit chart, verify queue
6. **Models** (`/models`) — Model registry, performance metrics
7. **System** (`/system`) — Provider health, data source log, settings
8. **Intelligence** (`/intelligence`) — News feed with optional Ollama analysis, decision log

## Setup

```bash
pip install -r requirements.txt

# Install Ollama (optional — for news analysis only)
# https://ollama.com
# ollama pull phi3:mini

python app.py
# Opens http://localhost:8050
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPINION_DB` | `opinion.db` | Path to SQLite database |

## Architecture

```
opinion/
├── app.py                  # Dash entry point, 8-page sidebar nav
├── config.py               # Horizons, FX pairs, scoring constants
├── pages/                  # 8 Dash pages
├── data/providers/         # DataProvider ABC, yfinance, FX, RSS news
├── data/cache.py           # SQLite TTL cache
├── models/                 # statsforecast + XGBoost + backtest + grader
├── llm/                    # Ollama client (news analysis only)
├── db/                     # SQLite schema (11 tables) + ops
└── tests/                  # pytest test suite
```

## Budget

₹0 — all data sources and libraries are free and open source.

## Disclaimer

This system is for market intelligence and personal research only. It does not execute trades, manage funds, or provide financial advice. All forecasts are experimental. Past performance does not guarantee future results.
