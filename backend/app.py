from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time as day_time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from strategy import _day, analyze_candlestick_patterns, analyze_candles, analyze_confluence, analyze_sma


NIFTY100_CSV = "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
IST = ZoneInfo("Asia/Kolkata")
_manual_data: dict[str, list[dict[str, Any]]] = {}

app = FastAPI(title="Free Swing & SMA Scanner", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normal_symbol(value: str) -> str:
    symbol = value.strip().upper()
    for suffix in (".NS", ".BO"):
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]
    return symbol


def _market_end_date() -> date:
    now = datetime.now(IST)
    # Exclude the current session's still-forming daily candle before the cash close.
    return now.date() if now.time() >= day_time(15, 35) else now.date() - timedelta(days=1)


def get_nifty100_symbols() -> list[str]:
    try:
        response = requests.get(
            NIFTY100_CSV,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.niftyindices.com/"},
            timeout=20,
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
        symbols = [_normal_symbol(str(row.get("Symbol", ""))) for row in reader]
        result = sorted({symbol for symbol in symbols if symbol})
        if not result:
            raise ValueError("The downloaded constituent file did not contain symbols.")
        return result
    except (requests.RequestException, UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=("Could not download the current Nifty 100 list from NSE Indices. "
                    f"Enter symbols manually instead. ({exc})"),
        ) from exc


def _clean_frame(frame: pd.DataFrame, symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    if frame is None or frame.empty:
        return result

    def normalize(value: Any) -> str:
        return str(value).strip().upper()

    for symbol in symbols:
        yahoo_symbol = symbol if symbol.endswith((".NS", ".BO")) else f"{symbol}.NS"
        part = frame
        if isinstance(frame.columns, pd.MultiIndex):
            found = False
            for level in range(frame.columns.nlevels):
                candidates = {normalize(v): v for v in frame.columns.get_level_values(level).unique()}
                key = normalize(yahoo_symbol)
                if key in candidates:
                    part = frame.xs(candidates[key], axis=1, level=level, drop_level=True)
                    found = True
                    break
            if not found and len(symbols) != 1:
                continue
        columns = {normalize(c): c for c in part.columns}
        required = ("OPEN", "HIGH", "LOW", "CLOSE")
        if not all(name in columns for name in required):
            continue
        bars: list[dict[str, Any]] = []
        for stamp, row in part.iterrows():
            try:
                if any(pd.isna(row[columns[name]]) for name in required):
                    continue
                if hasattr(stamp, "to_pydatetime"):
                    dt = stamp.to_pydatetime()
                    stamp_date = dt.strftime("%Y-%m-%d %H:%M") if (dt.hour != 0 or dt.minute != 0) else dt.strftime("%Y-%m-%d")
                elif hasattr(stamp, "hour") and (stamp.hour != 0 or stamp.minute != 0):
                    stamp_date = str(stamp)[:16]
                else:
                    stamp_date = str(stamp)[:10]
                bars.append({
                    "date": stamp_date,
                    "open": float(row[columns["OPEN"]]),
                    "high": float(row[columns["HIGH"]]),
                    "low": float(row[columns["LOW"]]),
                    "close": float(row[columns["CLOSE"]]),
                    "volume": int(row[columns["VOLUME"]]) if "VOLUME" in columns and not pd.isna(row[columns["VOLUME"]]) else 0,
                })
            except (TypeError, ValueError, OverflowError):
                continue
        if bars:
            bars.sort(key=lambda bar: bar["date"])
            result[_normal_symbol(symbol)] = bars
    return result


def yahoo_history(
    symbols: list[str],
    lookback_days: int,
    timeframe: str = "1d",
) -> dict[str, list[dict[str, Any]]]:
    interval_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "60m": "1h",
        "1d": "1d",
        "1w": "1wk",
        "1mo": "1mo",
    }
    interval = interval_map.get(timeframe, "1d")

    # Respect Yahoo Finance maximum historical limits for intraday intervals
    if interval in ("1m",):
        effective_days = min(lookback_days, 7)
    elif interval in ("5m", "15m", "30m"):
        effective_days = min(lookback_days, 59)
    elif interval in ("1h", "60m"):
        effective_days = min(lookback_days, 720)
    else:
        effective_days = min(lookback_days, 4000)

    end = _market_end_date()
    start = end - timedelta(days=effective_days)
    yahoo_symbols = [symbol if symbol.endswith((".NS", ".BO")) else f"{symbol}.NS" for symbol in symbols]
    try:
        frame = yf.download(
            tickers=yahoo_symbols,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False,
            timeout=30,
            multi_level_index=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Yahoo Finance download failed: {exc}") from exc
    return _clean_frame(frame, symbols)


def parse_manual_csv(filename: str, content: bytes) -> dict[str, list[dict[str, Any]]]:
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV is missing a header row.")
        header_map = {name.strip().lower(): name for name in reader.fieldnames if name}
        date_col = next((header_map[name] for name in ("date", "datetime", "timestamp") if name in header_map), None)
        symbol_col = next((header_map[name] for name in ("symbol", "ticker", "tradingsymbol") if name in header_map), None)
        cols = {name: header_map.get(name) for name in ("open", "high", "low", "close", "volume")}
        if not date_col or any(not cols[name] for name in ("open", "high", "low", "close")):
            raise ValueError("CSV needs date, open, high, low, and close columns; volume and symbol are optional.")
        default_symbol = _normal_symbol(filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0])
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in reader:
            symbol = _normal_symbol(row.get(symbol_col, "") if symbol_col else default_symbol)
            if not symbol or not re.fullmatch(r"[A-Z0-9&._-]{1,32}", symbol):
                raise ValueError(f"Invalid or missing symbol '{symbol}'. Add a symbol column or use the ticker as the filename.")
            raw_date = (row.get(date_col) or "").strip()
            try:
                stamp = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
            except ValueError:
                stamp = date.fromisoformat(raw_date[:10])
            values = {key: float(row[cols[key]]) for key in ("open", "high", "low", "close")}
            volume_text = (row.get(cols["volume"]) or "").strip() if cols["volume"] else ""
            volume = int(float(volume_text)) if volume_text else 0
            if values["high"] < max(values["open"], values["close"], values["low"]) or values["low"] > min(values["open"], values["close"], values["high"]):
                raise ValueError(f"Invalid OHLC values for {symbol} on {stamp.isoformat()}.")
            grouped.setdefault(symbol, []).append({"date": stamp, **values, "volume": volume})
        for symbol, bars in grouped.items():
            bars.sort(key=lambda bar: bar["date"])
            unique: dict[date, dict[str, Any]] = {bar["date"]: bar for bar in bars}
            grouped[symbol] = list(unique.values())
        if not grouped:
            raise ValueError("CSV contains no candle rows.")
        return grouped
    except (UnicodeDecodeError, csv.Error, TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not read {filename}: {exc}") from exc


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {"free_data": True, "sources": ["yahoo", "csv"], "manual_symbols": sorted(_manual_data)}


@app.get("/api/universe/nifty100")
def nifty100() -> dict[str, Any]:
    symbols = get_nifty100_symbols()
    return {"name": "Nifty 100", "source": NIFTY100_CSV, "count": len(symbols), "symbols": symbols}


@app.post("/api/data/upload")
async def upload_csv(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if len(files) > 20:
        raise HTTPException(status_code=413, detail="Upload at most 20 CSV files at once.")
    added: dict[str, int] = {}
    for file in files:
        content = await file.read(5_000_001)
        if len(content) > 5_000_000:
            raise HTTPException(status_code=413, detail=f"{file.filename} is larger than 5 MB.")
        parsed = parse_manual_csv(file.filename or "candles.csv", content)
        _manual_data.update(parsed)
        added.update({symbol: len(bars) for symbol, bars in parsed.items()})
    return {"symbols": sorted(_manual_data), "uploaded": added}


@app.delete("/api/data/upload")
def clear_manual_data() -> dict[str, Any]:
    _manual_data.clear()
    return {"symbols": []}


def analyze(
    strategy: str,
    candles: list[dict[str, Any]],
    enabled_techniques: list[str] | None = None,
    confluence_mode: str = "all",
    swing_period: int = 30,
    min_pivot_gap: int = 10,
    min_right_bars: int = 3,
    pivot_depth_bars: int = 5,
    pivot_depth_pct: float = 2.0,
    fast_period: int = 6,
    slow_period: int = 30,
    signal_window: int = 10,
    lookback_candles: int = 365,
    pattern_window: int = 10,
    marubozu_delta: float = 0.005,
    hammer_shadow_ratio: float = 2.0,
    enforce_trap_filter: bool = False,
    pattern_filter: str = "all",
    trendline_window: int = 10,
    sma_window: int = 10,
    rsi_period: int = 14,
    rsi_signal_ma_period: int = 9,
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
    rsi_window: int = 10,
    rsi_rule: str = "any_bullish",
) -> dict[str, Any]:
    if strategy == "pattern":
        techs = ["pattern"]
    elif strategy == "trendline":
        techs = ["trendline"]
    elif strategy == "sma":
        techs = ["sma"]
    elif strategy == "rsi":
        techs = ["rsi"]
    else:
        techs = enabled_techniques if enabled_techniques else ["pattern", "trendline", "sma", "rsi"]

    return analyze_confluence(
        candles,
        enabled_techniques=techs,
        confluence_mode=confluence_mode,
        swing_period=swing_period,
        min_pivot_gap=min_pivot_gap,
        trendline_window=trendline_window or signal_window,
        lookback_candles=lookback_candles,
        min_right_bars=min_right_bars,
        pivot_depth_bars=pivot_depth_bars,
        pivot_depth_pct=pivot_depth_pct,
        pattern_window=pattern_window or signal_window,
        pattern_filter=pattern_filter,
        marubozu_delta=marubozu_delta,
        hammer_shadow_ratio=hammer_shadow_ratio,
        enforce_trap_filter=enforce_trap_filter,
        fast_period=fast_period,
        slow_period=slow_period,
        sma_window=sma_window or signal_window,
        rsi_period=rsi_period,
        rsi_signal_ma_period=rsi_signal_ma_period,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        rsi_window=rsi_window or signal_window,
        rsi_rule=rsi_rule,
    )


def candles_for(
    symbol: str,
    source: Literal["yahoo", "csv"],
    lookback_days: int,
    lookback_candles: int = 365,
    timeframe: str = "1d",
    yahoo_cache: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    if timeframe == "1mo":
        mult = 32
    elif timeframe == "1w":
        mult = 7.5
    elif timeframe in ("5m", "15m", "30m"):
        mult = 0.05
    elif timeframe in ("1h", "60m"):
        mult = 0.2
    else:
        mult = 1.6
    fetch_days = max(lookback_days, int(lookback_candles * mult) + 2)

    if source == "csv":
        if symbol not in _manual_data:
            raise ValueError("No uploaded CSV candles for this symbol.")
        bars = _manual_data[symbol]
        return bars[-lookback_candles:]
    cache = yahoo_cache if yahoo_cache is not None else yahoo_history([symbol], fetch_days, timeframe)
    bars = cache.get(symbol) or cache.get(f"{symbol}.NS") or cache.get(f"{symbol}.BO")
    if not bars:
        raise ValueError("No Yahoo Finance candles returned for this symbol.")
    return bars[-lookback_candles:]


@app.get("/api/scan")
def scan(
    source: Literal["yahoo", "csv"] = "yahoo",
    strategy: str = "confluence",
    techniques: str = Query(default="pattern,trendline,sma,rsi"),
    confluence_mode: str = Query(default="all"),
    timeframe: str = Query(default="1d"),
    sort_by: str = Query(default="latest"),
    symbols: str = Query(default="", max_length=3000),
    swing_period: int = Query(default=30, ge=2, le=120),
    min_pivot_gap: int = Query(default=10, ge=1, le=60),
    min_right_bars: int = Query(default=3, ge=1, le=50),
    pivot_depth_bars: int = Query(default=5, ge=1, le=50),
    pivot_depth_pct: float = Query(default=2.0, ge=0.0, le=30.0),
    trendline_window: int = Query(default=10, ge=1, le=50),
    fast_period: int = Query(default=6, ge=2, le=100),
    slow_period: int = Query(default=30, ge=3, le=300),
    sma_window: int = Query(default=10, ge=1, le=50),
    lookback_candles: int = Query(default=365, ge=20, le=1200),
    lookback_days: int = Query(default=550, ge=1, le=4000),
    signal_window: int = Query(default=10, ge=1, le=50),
    pattern_window: int = Query(default=10, ge=1, le=50),
    marubozu_delta: float = Query(default=0.005, ge=0.001, le=0.05),
    hammer_shadow_ratio: float = Query(default=2.0, ge=1.0, le=5.0),
    enforce_trap_filter: bool = Query(default=False),
    pattern_filter: str = Query(default="bullish_marubozu,hammer"),
    rsi_period: int = Query(default=14, ge=2, le=50),
    rsi_signal_ma_period: int = Query(default=9, ge=2, le=30),
    rsi_oversold: float = Query(default=30.0, ge=10.0, le=45.0),
    rsi_overbought: float = Query(default=70.0, ge=55.0, le=90.0),
    rsi_window: int = Query(default=10, ge=1, le=50),
    rsi_rule: str = Query(default="any_bullish"),
) -> dict[str, Any]:
    if slow_period <= fast_period:
        raise HTTPException(status_code=400, detail="Slow SMA must be longer than the fast SMA.")
    requested = [_normal_symbol(s) for s in symbols.split(",") if s.strip()]
    if not requested:
        requested = sorted(_manual_data) if source == "csv" else get_nifty100_symbols()
    requested = list(dict.fromkeys(requested))[:100]
    if not requested:
        raise HTTPException(status_code=400, detail="Choose the Nifty 100 or upload candles / enter at least one symbol.")

    enabled_techs = [t.strip() for t in techniques.split(",") if t.strip()]
    if not enabled_techs:
        enabled_techs = ["pattern", "trendline", "sma", "rsi"]

    if timeframe == "1mo":
        mult = 32
    elif timeframe == "1w":
        mult = 7.5
    elif timeframe in ("5m", "15m", "30m"):
        mult = 0.05
    elif timeframe in ("1h", "60m"):
        mult = 0.2
    else:
        mult = 1.6
    fetch_days = max(lookback_days, int(lookback_candles * mult) + 2)

    yahoo_cache: dict[str, list[dict[str, Any]]] = {}
    if source == "yahoo":
        yahoo_cache = yahoo_history(requested, fetch_days, timeframe)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for symbol in requested:
        try:
            bars = candles_for(symbol, source, fetch_days, lookback_candles, timeframe, yahoo_cache)
            analysis = analyze(
                strategy=strategy,
                candles=bars,
                enabled_techniques=enabled_techs,
                confluence_mode=confluence_mode,
                swing_period=swing_period,
                min_pivot_gap=min_pivot_gap,
                min_right_bars=min_right_bars,
                pivot_depth_bars=pivot_depth_bars,
                pivot_depth_pct=pivot_depth_pct,
                fast_period=fast_period,
                slow_period=slow_period,
                signal_window=signal_window,
                lookback_candles=lookback_candles,
                pattern_window=pattern_window,
                marubozu_delta=marubozu_delta,
                hammer_shadow_ratio=hammer_shadow_ratio,
                enforce_trap_filter=enforce_trap_filter,
                pattern_filter=pattern_filter,
                trendline_window=trendline_window,
                sma_window=sma_window,
                rsi_period=rsi_period,
                rsi_signal_ma_period=rsi_signal_ma_period,
                rsi_oversold=rsi_oversold,
                rsi_overbought=rsi_overbought,
                rsi_window=rsi_window,
                rsi_rule=rsi_rule,
            )
            rows.append({
                "symbol": symbol,
                "last_date": analysis["last_date"],
                "close": analysis["close"],
                "latest_signal": analysis["latest_signal"],
                "is_confluence_signal": analysis.get("is_confluence_signal", False),
                "matched_count": analysis.get("matched_count", 0),
                "total_enabled": analysis.get("total_enabled", 0),
                "confluence_score": analysis.get("confluence_score", "0/0"),
                "matched_badges": analysis.get("matched_badges", []),
                "status_text": analysis.get("status_text"),
                "is_recent_breakout": analysis.get("is_recent_breakout", False),
                "fast_sma": analysis.get("fast_sma"),
                "slow_sma": analysis.get("slow_sma"),
                "rsi": analysis.get("rsi"),
                "rsi_signal": analysis.get("rsi_signal"),
                "resistance": analysis.get("resistance"),
                "support": analysis.get("support"),
                "distance_pct": analysis.get("distance_pct"),
                "pivot_count": len(analysis.get("swing_highs", [])),
                "is_broken_out": analysis.get("is_broken_out", False),
                "pattern_count": analysis.get("pattern_count", 0),
                "annotated_patterns": analysis.get("annotated_patterns", []),
            })
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    # Sort signals based on sort_by
    def row_sort_key(r: dict[str, Any]) -> tuple[Any, ...]:
        is_sig = 1 if r.get("is_confluence_signal") else 0
        bars_ago = r["latest_signal"]["bars_ago"] if r.get("latest_signal") else 999
        matched_count = r.get("matched_count", 0)
        sym = r["symbol"]

        if sort_by == "oldest":
            # Oldest breakout first (higher bars_ago at top)
            return (is_sig, bars_ago, sym)
        elif sort_by == "confluence":
            # Highest matches first, then lowest bars_ago
            return (is_sig, matched_count, -bars_ago, sym)
        elif sort_by == "symbol":
            # Alphabetical
            return (is_sig, -ord(sym[0]) if sym else 0)
        else:  # "latest" (default)
            # Lowest bars_ago at top
            return (is_sig, -bars_ago, sym)

    rows.sort(key=row_sort_key, reverse=True)

    signals_list = [r for r in rows if r.get("is_confluence_signal")]
    watching_list = [r for r in rows if not r.get("is_confluence_signal")]
    trendline_pivots_fulfilled = sum(1 for r in rows if r.get("pivot_count", 0) >= 2)

    return {
        "source": source,
        "strategy": strategy,
        "techniques": enabled_techs,
        "confluence_mode": confluence_mode,
        "timeframe": timeframe,
        "sort_by": sort_by,
        "scanned": len(rows),
        "requested": len(requested),
        "signals_count": len(signals_list),
        "trendline_pivots_fulfilled": trendline_pivots_fulfilled,
        "errors": errors,
        "parameters": {
            "swing_period": swing_period,
            "min_pivot_gap": min_pivot_gap,
            "min_right_bars": min_right_bars,
            "pivot_depth_bars": pivot_depth_bars,
            "pivot_depth_pct": pivot_depth_pct,
            "trendline_window": trendline_window,
            "fast_period": fast_period,
            "slow_period": slow_period,
            "sma_window": sma_window,
            "signal_window": signal_window,
            "lookback_candles": lookback_candles,
            "lookback_days": lookback_days,
            "timeframe": timeframe,
            "pattern_window": pattern_window,
            "marubozu_delta": marubozu_delta,
            "hammer_shadow_ratio": hammer_shadow_ratio,
            "enforce_trap_filter": enforce_trap_filter,
            "pattern_filter": pattern_filter,
            "rsi_period": rsi_period,
            "rsi_signal_ma_period": rsi_signal_ma_period,
            "rsi_oversold": rsi_oversold,
            "rsi_overbought": rsi_overbought,
            "rsi_window": rsi_window,
            "rsi_rule": rsi_rule,
            "techniques": enabled_techs,
            "confluence_mode": confluence_mode,
            "sort_by": sort_by,
        },
        "signals": signals_list,
        "watching": watching_list,
        "updated_at": datetime.now(IST).isoformat(timespec="seconds"),
    }


@app.get("/api/chart/{symbol}")
def chart(
    symbol: str,
    source: Literal["yahoo", "csv"] = "yahoo",
    strategy: str = "confluence",
    techniques: str = Query(default="pattern,trendline,sma,rsi"),
    confluence_mode: str = Query(default="all"),
    timeframe: str = Query(default="1d"),
    swing_period: int = Query(default=30, ge=2, le=120),
    min_pivot_gap: int = Query(default=10, ge=1, le=60),
    min_right_bars: int = Query(default=3, ge=1, le=50),
    pivot_depth_bars: int = Query(default=5, ge=1, le=50),
    pivot_depth_pct: float = Query(default=2.0, ge=0.0, le=30.0),
    trendline_window: int = Query(default=10, ge=1, le=50),
    fast_period: int = Query(default=6, ge=2, le=100),
    slow_period: int = Query(default=30, ge=3, le=300),
    sma_window: int = Query(default=10, ge=1, le=50),
    lookback_candles: int = Query(default=365, ge=20, le=1200),
    lookback_days: int = Query(default=550, ge=1, le=4000),
    signal_window: int = Query(default=10, ge=1, le=50),
    pattern_window: int = Query(default=10, ge=1, le=50),
    marubozu_delta: float = Query(default=0.005, ge=0.001, le=0.05),
    hammer_shadow_ratio: float = Query(default=2.0, ge=1.0, le=5.0),
    enforce_trap_filter: bool = Query(default=False),
    pattern_filter: str = Query(default="bullish_marubozu,hammer"),
    rsi_period: int = Query(default=14, ge=2, le=50),
    rsi_signal_ma_period: int = Query(default=9, ge=2, le=30),
    rsi_oversold: float = Query(default=30.0, ge=10.0, le=45.0),
    rsi_overbought: float = Query(default=70.0, ge=55.0, le=90.0),
    rsi_window: int = Query(default=10, ge=1, le=50),
    rsi_rule: str = Query(default="any_bullish"),
) -> dict[str, Any]:
    symbol = _normal_symbol(symbol)
    if slow_period <= fast_period:
        raise HTTPException(status_code=400, detail="Slow SMA must be longer than the fast SMA.")

    enabled_techs = [t.strip() for t in techniques.split(",") if t.strip()]
    if not enabled_techs:
        enabled_techs = ["pattern", "trendline", "sma", "rsi"]

    if timeframe == "1mo":
        mult = 32
    elif timeframe == "1w":
        mult = 7.5
    elif timeframe in ("5m", "15m", "30m"):
        mult = 0.05
    elif timeframe in ("1h", "60m"):
        mult = 0.2
    else:
        mult = 1.6
    fetch_days = max(lookback_days, int(lookback_candles * mult) + 2)

    try:
        cache = yahoo_history([symbol], fetch_days, timeframe) if source == "yahoo" else None
        bars = candles_for(symbol, source, fetch_days, lookback_candles, timeframe, cache)
        analysis = analyze(
            strategy=strategy,
            candles=bars,
            enabled_techniques=enabled_techs,
            confluence_mode=confluence_mode,
            swing_period=swing_period,
            min_pivot_gap=min_pivot_gap,
            min_right_bars=min_right_bars,
            pivot_depth_bars=pivot_depth_bars,
            pivot_depth_pct=pivot_depth_pct,
            fast_period=fast_period,
            slow_period=slow_period,
            signal_window=signal_window,
            lookback_candles=lookback_candles,
            pattern_window=pattern_window,
            marubozu_delta=marubozu_delta,
            hammer_shadow_ratio=hammer_shadow_ratio,
            enforce_trap_filter=enforce_trap_filter,
            pattern_filter=pattern_filter,
            trendline_window=trendline_window,
            sma_window=sma_window,
            rsi_period=rsi_period,
            rsi_signal_ma_period=rsi_signal_ma_period,
            rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought,
            rsi_window=rsi_window,
            rsi_rule=rsi_rule,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Could not analyze {symbol}: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data request failed for {symbol}: {exc}") from exc
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "analysis": analysis,
        "candles": [{"date": _day(bar["date"]), **{key: bar[key] for key in ("open", "high", "low", "close", "volume")}} for bar in bars],
        "chart_offset": 0,
    }
