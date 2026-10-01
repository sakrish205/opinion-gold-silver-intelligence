# DASHBOARD MIGRATION PLAN

---

## CURRENT (8 pages)

| Page | Path | Core Function | Redundancy |
|------|------|--------------|------------|
| Overview | / | INR-first prices, FX table | — |
| Metals | /metals | Candlestick OHLCV + MA20/MA50 | Prices also shown in Overview |
| Markets | /markets | International prices, FX chart, FX history | FX table overlaps Overview; prices overlap Overview |
| Analytics | /analytics | Currency influence heatmap, Backtest UI | — |
| Forecasts | /forecasts | Run/Grade/Audit/Verify | — |
| Models | /models | Registry, performance chart | — |
| System | /system | Provider health, settings | — |
| Intelligence | /intelligence | News, Decision log | — |

---

## TARGET (5 pages — do not implement yet)

| Page | Contents | Source pages merged |
|------|----------|-------------------|
| Market | Price cards (INR + USD), candlestick chart, FX rates | Overview + Metals + Markets |
| Forecast | Run/Grade/Audit/Verify + signal output (future) | Forecasts |
| Signals | BUY/HOLD/SELL rationale, decision log | Intelligence (decisions) + new signal engine |
| News | RSS news, Ollama/FinBERT analysis | Intelligence (news tab) |
| System | Model registry, performance, health, settings | Models + System + Analytics |

---

## Planned Consolidation (do in a future prompt)

1. **Market** ← merge Overview + Metals + Markets
   - Keep: INR-first price cards, candlestick, FX table, FX sparklines
   - Remove: redundant price display in Markets (already in Overview)
   - Move: FX chart from Markets into Market page

2. **Signals** ← new page (requires signal engine, build in Prompt 5+)
   - Decision log from Intelligence > Decisions tab
   - Automated system signal (once signal engine exists)

3. **News** ← extract from Intelligence page
   - Keep current RSS + Ollama pipeline
   - Add FinBERT sentiment column when available

4. **System** ← merge Models + System + Analytics
   - Model registry, backtest runner, provider health, settings in one place

---

## What NOT to do yet

- Do not delete any of the 8 current pages
- Do not merge pages until the signal engine exists (Signals page would be empty)
- Do not remove Analytics page (backtest UI is only there)
- Do not remove Intelligence page (news pipeline is only there)

## Minor cleanup safe to do now (Prompt 2)

- None identified that wouldn't risk breaking functionality
- Dashboard page cleanup belongs in Prompt 5+ alongside signal engine
