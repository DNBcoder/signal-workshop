# Signal Workshop

A local research dashboard following the workflow in Zerodha Varsity's [Build a Trading Algo with AI](https://www.youtube.com/watch?v=V9Ra8klDzrM), with **both** the tutorial's SMA crossover and a separate swing trendline strategy. The Varsity video and learning modules are free; this app needs no Varsity account, software, or paid certification. It has no Kite Connect dependency, API key, account login, paid-data integration, or order placement.

## Pick a free data source

- **Yahoo Finance** — fetches daily history through [yfinance](https://github.com/ranaroussi/yfinance), an open-source community package. It needs no API key or subscription. The package is not affiliated with Yahoo; its maintainers describe the Yahoo Finance interface as intended for personal use. Access can change or be rate-limited, and data may be delayed or incomplete. Review [Yahoo's terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) for the data-use conditions that apply to you.
- **Manual CSV** — upload candles from a spreadsheet, broker export, or other source. Files are parsed in the local app process and kept in memory until the API server restarts. No data provider account is needed.

The Yahoo option defaults to the current Nifty 100 constituent list published by [NSE Indices](https://www.nseindia.in/static/products-services/indices-nifty100-index). Enter comma-separated symbols to scan a smaller/custom universe. Yahoo symbols are resolved as NSE tickers by appending `.NS` when needed.

## Strategies & Confluence Engine

### Multi-Factor Confluence (Strategy Mixing)
- Allows mixing any combination of techniques: Candlestick Patterns, Body-Tip Swing Trendlines, and SMA Crossovers.
- Pick presets or select custom combinations (e.g. only Pattern + SMA without trendline, or all 3).
- Confluence modes: **Strict Confluence** (match ALL active techniques) or **Match ANY active technique**.
- Output notification sorting: easily toggle between **Latest Breakout First** or **Oldest Breakout First**.
- Interactive chart simultaneously displays active overlays (candlestick pattern pins, trendline, and SMA curves).
- All parameters feature synchronized **Dual Sliders and Numeric Input boxes**.

### Supported Timeframes
- **Intraday:** `5m` (5 Min), `15m` (15 Min), `1h` (1 Hour) with timestamps (`YYYY-MM-DD HH:MM`).
- **Higher Timeframes:** `1D` (Daily), `1W` (Weekly), and `1M` (Monthly up to 10 years).

### 1. Candlestick Pattern Recognition
- **Formulas evaluated for candle $t$:**
  - $\text{Range} = H - L, \quad \text{Body} = |C - O|$
  - $\text{UpperShadow} = H - \max(O, C), \quad \text{LowerShadow} = \min(O, C) - L$
  - Candle colors: Bullish (Blue, $C \ge O$), Bearish (Red, $C < O$)
  - **Candle Length Filter (Trade Trap Rule):** $0.01 \le \frac{H - L}{O} \le 0.10$ ignores abnormally subdued (<1%) or giant (>10%) candles. Toggleable in UI.
- **Patterns Detected:**
  - **Bullish Marubozu:** $C > O \land \frac{H - C}{H} \le \delta \land \frac{O - L}{L} \le \delta$ (tolerance $\delta \in [0.002, 0.020]$, default $0.005$ / $0.5\%$).
  - **Bearish Marubozu:** $O > C \land \frac{H - O}{H} \le \delta \land \frac{C - L}{L} \le \delta$.
  - **Hammer:** $\text{LowerShadow} \ge 2 \times \text{Body} \land \frac{|C - O|}{O} \le 0.02 \land \frac{\text{UpperShadow}}{\text{Range}} \le 0.10$.
  - **Inverted Hammer / Shooting Star:** $\text{UpperShadow} \ge 2 \times \text{Body} \land \frac{|C - O|}{O} \le 0.02 \land \frac{\text{LowerShadow}}{\text{Range}} \le 0.10$.
- **Lookback Window:** Scans last $N$ candles (default 10, adjustable via slider).
- **Interactive Pins:** Floating pattern pins (`HAMMER`, `B-MARU`, `BR-MARU`, `STAR`) appear directly on the candlestick chart.

### 2. Multi-Timeframe Swing Trendlines (Candlestick Body Tips & Breakouts)
- Identifies swing highs strictly on candle body tips: `max(open, close)`.
- Nearest completed swing highs chosen; current market price / forming candle is never chosen as a pivot.
- Extended trendline passes through pivots touching body tips and extends across the entire chart.
- Displays true historical breakout date where price first crossed the line.

### 3. SMA Crossover (Tutorial Strategy)
- Defaults to a 6-day and 30-day simple moving average.
- Bullish cross: fast SMA crosses above slow SMA; Bearish cross: fast crosses below slow.

Both strategies read the same chosen daily candle source and universe, and each can be selected independently from the dashboard.

## How to run locally on Windows

### Option A: One-click launcher (Easiest)

Simply open the project folder:
`C:\Users\samaj\Documents\Codex\2026-11-20\c\outputs\signal-workshop`

1. Double-click **`start.bat`**:
   - Launches the backend API server on port 8000.
   - Launches the Vite frontend on port 5173.
   - Automatically opens `http://127.0.0.1:5173` in your browser.
2. Double-click **`stop.bat`** whenever you want to close both servers.

### Option B: From PowerShell / Command Prompt

Start the API in one PowerShell window:

```powershell
cd C:\Users\samaj\Documents\Codex\2026-11-20\c\outputs\signal-workshop
.\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Start the frontend in another PowerShell window:

```powershell
cd C:\Users\samaj\Documents\Codex\2026-11-20\c\outputs\signal-workshop
$env:Path = "C:\Program Files\nodejs;$env:Path"
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173` in your browser.

