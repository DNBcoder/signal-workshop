# Handoff for the next LLM

Read this file first, then `README.md`, before changing the project.

## User's goal and preferences

The user is following Zerodha Varsity's video [Build a Trading Algo with AI | No Coding Required](https://www.youtube.com/watch?v=V9Ra8klDzrM). They want a personal signal dashboard based on that workflow, but with their own swing-high/swing-low trendline breakout analysis too. Varsity's video and learning modules are free; no Varsity app, account, or paid certification is a project dependency.

The user clarified two requirements:

1. Keep the tutorial's SMA crossover strategy; do not replace it. Add the user's trendline strategy alongside it so they can select either one.
2. Keep the project free. Do not depend on Kite Connect paid data. Prefer free data such as yfinance, with manual candle data as a fallback.

Keep the interface signal-only. Do not add automatic order placement unless the user explicitly requests it. Do not ask for Kite API keys; this project should not need them.

## Project location

`C:\Users\samaj\Documents\Codex\2026-11-20\c\outputs\signal-workshop`

The project folder is named `signal-workshop`; the app does not depend on Kite Connect. The frontend package is named `signal-workshop-ui`.

## What is implemented

- **Multi-Factor Confluence Engine (Strategy Mixing):**
  - Allows mixing any combination of techniques: Candlestick Patterns, Body-Tip Swing Trendlines, and SMA Crossovers.
  - Supports custom technique combinations (e.g. only Pattern + SMA without trendline, Pattern + Trendline, or all 3).
  - Confluence modes: **Strict Confluence** (match ALL active techniques) or **Match ANY active technique**.
  - Unified interactive candlestick chart overlaying Trendlines, Pattern Pins, and SMA curves concurrently.
- **Intraday Timeframes (Minute & Hour-wise):**
  - Full support for `5m` (5 Min), `15m` (15 Min), and `1h` (1 Hour) intraday candles alongside `1D` (Daily), `1W` (Weekly), and `1M` (Monthly).
  - Preserves exact intraday timestamps (`YYYY-MM-DD HH:MM`).
  - Automatically respects Yahoo Finance historical limits for intraday data.
- **Dual Sliders with Synchronized Numeric Inputs:**
  - Range slider and numeric input boxes for all parameters: Swing Period (highest swing in N candles), Min Pivot Gap, Breakout Window, Lookback Candles, Pattern Window, Marubozu Delta, Hammer Ratio, and SMA Fast/Slow periods.
- **Output Notification Sorting:**
  - Dynamic sort selector: "Latest Breakout / Signal First", "Oldest Breakout in Window First", "Highest Confluence Score First", and "Symbol A-Z".
- **Candlestick pattern recognition mode:**
  - Evaluates candles for Bullish Marubozu, Bearish Marubozu, Hammer, and Inverted Hammer / Shooting Star.
  - Mathematical definitions:
    - $\text{Range} = H - L$, $\text{Body} = |C - O|$, $\text{UpperShadow} = H - \max(O, C)$, $\text{LowerShadow} = \min(O, C) - L$.
    - Candle colors: Bullish (Blue, $C \ge O$), Bearish (Red, $C < O$).
    - Candle Length Filter (Trade Trap Rule): $0.01 \le \frac{H - L}{O} \le 0.10$ ignores subdued activity (<1%) or giant candles (>10%). Toggleable in UI.
    - Bullish Marubozu: $C > O \land \frac{H - C}{H} \le \delta \land \frac{O - L}{L} \le \delta$ (tolerance $\delta \in [0.002, 0.020]$, default $0.005$).
    - Bearish Marubozu: $O > C \land \frac{H - O}{H} \le \delta \land \frac{C - L}{L} \le \delta$.
    - Hammer: $\text{LowerShadow} \ge 2 \times \text{Body} \land \frac{|C - O|}{O} \le 0.02 \land \frac{\text{UpperShadow}}{\text{Range}} \le 0.10$.
  - Scans last $N$ candles (default 10, configurable from 1 to 50 bars).
  - Floating pattern pin badges (`HAMMER`, `B-MARU`, `BR-MARU`, `STAR`) on the candlestick chart.
- **Multi-timeframe swing trendline mode:** 
  - Candlestick body-tip swing highs (`max(open, close)`).
  - Swing period check: strictly higher than N prior and N subsequent candles (default 30).
  - Minimum gap check: at least N candles between swing points (default 10).
  - Supports Daily (1D), Weekly (1W), and Monthly (1M) charts (36–120 monthly candles / 3–10 years).
  - Nearest swing high anchoring: selects completed swing highs closest to current date (excluding forming candle / current price).
  - Extended trendline: line touches candle body tips and extends in both directions across the entire chart.
  - Breakout detection: true historical crossover date identification.
- **SMA crossover mode:** default fast SMA 6 and slow SMA 30, matching the tutorial's example. It detects bullish and bearish crosses on completed daily closes and ranks recent signals.
- **One-click scripts:** `start.bat` and `stop.bat` in the project root for launching and stopping without agent assistance.
- **Free data choices:**
  - Yahoo Finance history through the community `yfinance` package, using NSE `.NS` tickers. Default universe is the Nifty 100 constituent CSV from NSE Indices; users can enter a custom comma-separated list.
  - Manual CSV upload. Required columns: `date,open,high,low,close`; optional `volume` and `symbol`. Multiple symbols can be in one file when `symbol` is present; otherwise the filename stem is used. Uploaded candles are stored in memory and clear when the backend restarts.
- A React/Vite dashboard with strategy selection, data-source selection, parameters, signal/watch lists, and chart review. The chart overlays SMA lines in SMA mode, trendlines/pivot dots in trendline mode, and candlestick pins in pattern mode.
- Backend FastAPI routes: `/api/status`, `/api/universe/nifty100`, `/api/data/upload` (POST/DELETE), `/api/scan`, `/api/chart/{symbol}`.
- No Kite login, broker API credentials, order placement, GTT, or backtest code.

## Important data-source caveat

`yfinance` is a free community library that accesses Yahoo's publicly available interfaces; its maintainers state that Yahoo Finance access is intended for personal use. It is not an official Yahoo API, may be rate-limited or change, and returned data can be delayed or incomplete. For a stable offline input, use the manual CSV source. Do not describe Yahoo data as guaranteed real-time or suitable for commercial redistribution.

The NSE Nifty 100 CSV download has **not been verified end-to-end from inside the running app**. If that endpoint fails, the dashboard tells the user to enter symbols manually. Preserve that fallback or improve the source only with a free, clearly documented alternative.

## Files to know

- `README.md` — overview, rules, CSV format, and local run instructions.
- `backend/app.py` — data providers, CSV upload parsing, scan/chart API.
- `backend/strategy.py` — SMA and swing-pivot/trendline analysis functions.
- `backend/requirements.txt` — FastAPI, Uvicorn, requests, yfinance, multipart upload dependency.
- `frontend/src/App.jsx` — dashboard UI, strategy/data selection, upload, scan, table, chart.
- `frontend/src/styles.css` — UI styling.
- `frontend/package.json` / `package-lock.json` — React/Vite frontend setup.
- `.gitignore` — excludes `.venv`, `node_modules`, build output, and Python caches.

## Local environment and commands

Python 3.13.17 is installed at `C:\Users\samaj\AppData\Local\Programs\Python\Python313\python.exe`. Node.js 26.13.1 is installed under `C:\Program Files\nodejs`.

The project-local `.venv` already has `backend/requirements.txt` installed. `frontend/node_modules` is also installed. From the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000
```

In another PowerShell window:

```powershell
$env:Path = "C:\Program Files\nodejs;$env:Path"
C:\Program Files\nodejs\npm.cmd --prefix frontend run dev
```

Open `http://127.0.0.1:5173`.

## Work completed and validation

- Created and installed the isolated Python environment with the free Yahoo/CSV backend dependencies.
- Installed frontend dependencies and approved the standard `esbuild` install script required by Vite.
- `npm run build` completed successfully after the SMA/Yahoo/CSV changes.
- Python source files compiled successfully with `compileall`.
- No automated tests or live broker/data integration tests were run. Do not claim that live Yahoo downloads, NSE constituent downloads, or scans have been verified.
- An earlier global Python environment may still have the separately installed `kiteconnect` package from the prior task. The project-local `.venv` and `backend/requirements.txt` do not depend on it. Do not uninstall global packages without user direction.

## Suggested next steps

1. Read the current backend and frontend before editing; this is a hand-built prototype, not a validated trading system.
2. If the user asks, start the local app and inspect its UI. When using actual market data, call out provider failures clearly and keep CSV input available.
3. If adding features, maintain the two independent strategy modes and free/manual source options. Avoid accidental automatic order features.
4. Improve strategy configurability only with explicit, understandable rules (for example, whether sloping resistance/support lines are allowed, volume confirmation, stop/exit rules, or which swing pair to use). Current behavior is documented in `README.md`.
5. Do not present signals as profitable or as investment recommendations. The project has no backtest implementation yet.

