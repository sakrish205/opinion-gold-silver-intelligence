# OPINION — Gold & Silver Market Intelligence

Local-first, ₹0-budget Gold & Silver market intelligence dashboard for Indian investors.

## Features

- India/INR-first pricing
- XAU/XAG in USD, EUR, CNY, INR
- 5 FX pairs: USD/INR, EUR/INR, CNY/INR, JPY/INR, CHF/INR
- 5 forecast horizons: +1h, +5h, +12h, +24h, +48h
- 5 forecasting models: Naive, AutoARIMA, AutoETS, Theta (statsforecast), XGBoost+FX
- Walk-forward backtesting; best model selected per asset × horizon
- Immutable forecast history and append-only audit tables
- +3/−6 scoring (market data only, LLM excluded)
- 18 dashboard pages
- Local Ollama LLM (configurable, not hardcoded)
- No paid APIs, no cloud, no subscriptions

## Price Labels

| Label | Meaning |
|-------|---------|
| `FUTURES` | COMEX futures contract (GC=F, SI=F via yfinance) |
| `DERIVED` | Computed cross-price (e.g. XAU/INR = XAU/USD_futures × USD/INR) |
| `UNAVAILABLE` | No verified free source available |

GC=F and SI=F are **FUTURES contracts**. They are never displayed as spot prices.

## Data Quality States

| State | Meaning |
|-------|---------|
| `LIVE` | Freshly fetched, passes validation |
| `STALE` | From cache, older than refresh interval |
| `UNAVAILABLE` | All providers failed or no free source exists |
| `ERROR` | Data failed validation |

## Setup

```bash
pip install -r requirements.txt

# Install Ollama (optional — for news analysis)
# https://ollama.com
# ollama pull phi3:mini

python app.py
# Open http://localhost:8050
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPINION_DB` | `opinion.db` | Path to SQLite database |

## Architecture

```
opinion/
├── app.py              # Dash entry, sidebar nav (18 pages)
├── config.py           # Horizons, FX pairs, thresholds
├── pages/              # 18 Dash pages
├── data/providers/     # DataProvider ABC, yfinance, FX, news
├── models/             # statsforecast + XGBoost + backtest
├── llm/                # Ollama client + configurable model registry
└── db/                 # SQLite schema (11 tables) + ops
```

## Budget

₹0 — all data sources and libraries are free and open source.

## Disclaimer

This system is for market intelligence and personal research only. It does not execute trades, manage funds, or provide financial advice. All forecasts are experimental. Past performance does not guarantee future results.
