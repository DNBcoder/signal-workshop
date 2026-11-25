from __future__ import annotations

from datetime import date, datetime
from typing import Any

from trendline_detector import analyze_multi_touch_trendlines


def _day(d: Any) -> str:
    if isinstance(d, datetime):
        if d.hour != 0 or d.minute != 0:
            return d.strftime("%Y-%m-%d %H:%M")
        return d.strftime("%Y-%m-%d")
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    s = str(d)
    return s[:16] if len(s) > 10 and ":" in s else s[:10]


def detect_patterns_for_candle(
    c: dict[str, Any],
    delta: float = 0.005,
    min_range_pct: float = 0.01,
    max_range_pct: float = 0.10,
    hammer_shadow_ratio: float = 2.0,
    hammer_max_body_pct: float = 0.02,
    hammer_max_upper_shadow_ratio: float = 0.10,
) -> list[dict[str, Any]]:
    """Evaluate a single candlestick for Marubozu, Hammer, and Shooting Star patterns
    using mathematical definitions provided by the user.
    """
    O = float(c["open"])
    H = float(c["high"])
    L = float(c["low"])
    C = float(c["close"])

    if O <= 0 or H <= 0 or L <= 0 or C <= 0:
        return []

    rng = H - L
    body = abs(C - O)
    upper_shadow = H - max(O, C)
    lower_shadow = min(O, C) - L

    # Candle Length Filter (Trade Trap Rule): 0.01 <= (H - L)/O <= 0.10
    range_ratio = rng / O
    passes_trap_filter = (min_range_pct <= range_ratio <= max_range_pct)
    trap_status = "Pass" if passes_trap_filter else ("Subdued (<1%)" if range_ratio < min_range_pct else "Giant (>10%)")

    patterns: list[dict[str, Any]] = []

    # 1. Bullish Marubozu:
    # C > O and (H - C)/H <= delta and (O - L)/L <= delta
    if C > O and H > 0 and L > 0:
        upper_shadow_ratio = (H - C) / H
        lower_shadow_ratio = (O - L) / L
        if upper_shadow_ratio <= delta and lower_shadow_ratio <= delta:
            patterns.append({
                "type": "bullish_marubozu",
                "name": "Bullish Marubozu",
                "bias": "bullish",
                "passes_trap_filter": passes_trap_filter,
                "trap_status": trap_status,
                "body_pct": round((body / O) * 100, 2),
                "upper_shadow_pct": round(upper_shadow_ratio * 100, 2),
                "lower_shadow_pct": round(lower_shadow_ratio * 100, 2),
                "details": f"Body={round(body/O*100, 1)}%, Upper={round(upper_shadow_ratio*100, 2)}%, Lower={round(lower_shadow_ratio*100, 2)}%",
            })

    # 2. Bearish Marubozu:
    # O > C and (H - O)/H <= delta and (C - L)/L <= delta
    elif O > C and H > 0 and L > 0:
        upper_shadow_ratio = (H - O) / H
        lower_shadow_ratio = (C - L) / L
        if upper_shadow_ratio <= delta and lower_shadow_ratio <= delta:
            patterns.append({
                "type": "bearish_marubozu",
                "name": "Bearish Marubozu",
                "bias": "bearish",
                "passes_trap_filter": passes_trap_filter,
                "trap_status": trap_status,
                "body_pct": round((body / O) * 100, 2),
                "upper_shadow_pct": round(upper_shadow_ratio * 100, 2),
                "lower_shadow_pct": round(lower_shadow_ratio * 100, 2),
                "details": f"Body={round(body/O*100, 1)}%, Upper={round(upper_shadow_ratio*100, 2)}%, Lower={round(lower_shadow_ratio*100, 2)}%",
            })

    # 3. Hammer:
    # LowerShadow >= 2 * Body and |C - O|/O <= 0.02 and UpperShadow / Range <= 0.10
    if rng > 0:
        body_pct = body / O
        upper_shadow_ratio_rng = upper_shadow / rng
        if (lower_shadow >= hammer_shadow_ratio * body) and (body_pct <= hammer_max_body_pct) and (upper_shadow_ratio_rng <= hammer_max_upper_shadow_ratio):
            patterns.append({
                "type": "hammer",
                "name": "Hammer",
                "bias": "bullish",
                "passes_trap_filter": passes_trap_filter,
                "trap_status": trap_status,
                "body_pct": round(body_pct * 100, 2),
                "lower_shadow": round(lower_shadow, 2),
                "upper_shadow_ratio": round(upper_shadow_ratio_rng * 100, 1),
                "details": f"LowerShadow={round(lower_shadow, 1)} (vs 2xBody={round(hammer_shadow_ratio*body, 1)}), UpperShadow%={round(upper_shadow_ratio_rng*100, 1)}%",
            })

    # 4. Inverted Hammer / Shooting Star:
    # UpperShadow >= 2 * Body and |C - O|/O <= 0.02 and LowerShadow / Range <= 0.10
    if rng > 0:
        body_pct = body / O
        lower_shadow_ratio_rng = lower_shadow / rng
        if (upper_shadow >= hammer_shadow_ratio * body) and (body_pct <= hammer_max_body_pct) and (lower_shadow_ratio_rng <= hammer_max_upper_shadow_ratio):
            pat_name = "Inverted Hammer" if C >= O else "Shooting Star"
            pat_type = "inverted_hammer" if C >= O else "shooting_star"
            bias = "bullish" if C >= O else "bearish"
            patterns.append({
                "type": pat_type,
                "name": pat_name,
                "bias": bias,
                "passes_trap_filter": passes_trap_filter,
                "trap_status": trap_status,
                "body_pct": round(body_pct * 100, 2),
                "upper_shadow": round(upper_shadow, 2),
                "lower_shadow_ratio": round(lower_shadow_ratio_rng * 100, 1),
                "details": f"UpperShadow={round(upper_shadow, 1)} (vs 2xBody={round(hammer_shadow_ratio*body, 1)}), LowerShadow%={round(lower_shadow_ratio_rng*100, 1)}%",
            })

    return patterns


def analyze_candlestick_patterns(
    candles: list[dict[str, Any]],
    pattern_window: int = 10,
    marubozu_delta: float = 0.005,
    hammer_shadow_ratio: float = 2.0,
    enforce_trap_filter: bool = False,
    pattern_filter: str | list[str] = "all",
) -> dict[str, Any]:
    """Scan the last pattern_window candles for studied candlestick patterns.
    Supports multiple patterns with OR-logic (e.g. 'bullish_marubozu,hammer').
    """
    if not candles:
        raise ValueError("Need at least one candle to analyze patterns.")

    # Parse pattern_filter into a clean set of requested pattern types
    if isinstance(pattern_filter, str):
        selected_types = [t.strip().lower() for t in pattern_filter.split(",") if t.strip()]
    elif isinstance(pattern_filter, (list, tuple, set)):
        selected_types = [str(t).strip().lower() for t in pattern_filter if str(t).strip()]
    else:
        selected_types = ["all"]

    allow_all = ("all" in selected_types) or (not selected_types)

    n = len(candles)
    start_idx = max(0, n - pattern_window)
    found_events: list[dict[str, Any]] = []

    for i in range(start_idx, n):
        c = candles[i]
        candle_patterns = detect_patterns_for_candle(
            c,
            delta=marubozu_delta,
            hammer_shadow_ratio=hammer_shadow_ratio,
        )
        for p in candle_patterns:
            if enforce_trap_filter and not p["passes_trap_filter"]:
                continue

            # OR-logic: presence of ANY selected pattern triggers positive result
            if not allow_all:
                p_type = p["type"].lower()
                matches_any = (
                    p_type in selected_types
                    or (("marubozu" in selected_types) and "marubozu" in p_type)
                    or (("hammer" in selected_types) and "hammer" in p_type)
                )
                if not matches_any:
                    continue

            O = float(c["open"])
            H = float(c["high"])
            L = float(c["low"])
            C = float(c["close"])
            found_events.append({
                "type": p["type"],
                "name": p["name"],
                "bias": p["bias"],
                "date": _day(c["date"]),
                "bar_index": i,
                "bars_ago": n - 1 - i,
                "open": O,
                "high": H,
                "low": L,
                "close": C,
                "range_pct": round(((H - L) / O) * 100, 2),
                "trap_status": p["trap_status"],
                "passes_trap_filter": p["passes_trap_filter"],
                "details": p["details"],
            })

    found_events.sort(key=lambda ev: ev["bars_ago"])
    latest_event = found_events[0] if found_events else None
    last = candles[-1]
    prev = candles[-2] if len(candles) > 1 else last

    annotated = [
        {
            "bar_index": ev["bar_index"],
            "name": ev["name"],
            "bias": ev["bias"],
            "date": ev["date"],
            "type": ev["type"],
            "bars_ago": ev["bars_ago"],
            "details": ev["details"],
            "trap_status": ev["trap_status"],
            "passes_trap_filter": ev["passes_trap_filter"],
        }
        for ev in found_events
    ]

    filter_desc = "All Patterns" if allow_all else " OR ".join(selected_types)
    return {
        "last_date": _day(last["date"]),
        "close": float(last["close"]),
        "previous_close": float(prev["close"]),
        "signals": found_events,
        "latest_signal": latest_event,
        "pattern_count": len(found_events),
        "annotated_patterns": annotated,
        "selected_patterns": selected_types if not allow_all else ["all"],
        "status_text": f"{latest_event['name']} ({latest_event['bars_ago']}b ago)" if latest_event else f"No matching pattern ({filter_desc}) in window",
    }


def find_body_swing_highs(
    candles: list[dict[str, Any]],
    swing_period: int = 30,
    min_gap: int = 10,
    min_right_bars: int = 3,
    pivot_depth_bars: int = 5,
    pivot_depth_pct: float = 2.0,
) -> list[dict[str, Any]]:
    """Identify confirmed swing highs on candle body tips (max(open, close)).
    Conditions:
    1. Higher than preceding swing_period candles.
    2. Has already fallen back down (higher than all subsequent candles up to swing_period,
       with at least min_right_bars of lower closed candles to the right).
    3. The current market price cannot be chosen as a swing high (i <= len - 1 - min_right_bars).
    4. Depth / Prominence condition:
       In N candles before and after the pivot, the price lowest (low) must be at least
       x percent less than the pivot point price.
    5. Separated from adjacent swing highs by at least min_gap candles.
    """
    n = len(candles)
    if n < swing_period + min_right_bars + 1:
        return []

    body_highs = [max(float(c["open"]), float(c["close"])) for c in candles]
    lows = [float(c["low"]) for c in candles]
    raw_highs: list[dict[str, Any]] = []

    # Current market price cannot be swing high: i <= n - 1 - min_right_bars
    for i in range(swing_period, n - min_right_bars):
        val = body_highs[i]
        if val <= 0:
            continue

        # 1. Higher than preceding swing_period candles
        left = body_highs[max(0, i - swing_period) : i]
        if not left or val <= max(left):
            continue

        # 2. Must have fallen back down (higher than all subsequent candles up to swing_period)
        right_end = min(n, i + swing_period + 1)
        right = body_highs[i + 1 : right_end]
        if not right or val <= max(right):
            continue

        # 3. Depth / Prominence check:
        # N candles before and after pivot, the price lowest must be at least x% less than pivot price
        left_drop_val = 0.0
        right_drop_val = 0.0
        if pivot_depth_bars > 0 and pivot_depth_pct > 0:
            target_drop = val * (1.0 - pivot_depth_pct / 100.0)

            # Left depth check (up to pivot_depth_bars before index i)
            left_depth_start = max(0, i - pivot_depth_bars)
            left_window_lows = lows[left_depth_start : i]
            if not left_window_lows:
                continue
            min_left_low = min(left_window_lows)
            if min_left_low > target_drop:
                continue
            left_drop_val = round(((val - min_left_low) / val) * 100, 2)

            # Right depth check (up to pivot_depth_bars after index i)
            right_depth_end = min(n, i + pivot_depth_bars + 1)
            right_window_lows = lows[i + 1 : right_depth_end]
            if not right_window_lows:
                continue
            min_right_low = min(right_window_lows)
            if min_right_low > target_drop:
                continue
            right_drop_val = round(((val - min_right_low) / val) * 100, 2)

        close = float(candles[i]["close"])
        open_price = float(candles[i]["open"])
        raw_highs.append({
            "index": i,
            "date": _day(candles[i]["date"]),
            "price": val,
            "high": float(candles[i]["high"]),
            "low": float(candles[i]["low"]),
            "open": open_price,
            "close": close,
            "tip_type": "close" if close >= open_price else "open",
            "bars_ago": n - 1 - i,
            "left_drop_pct": left_drop_val,
            "right_drop_pct": right_drop_val,
        })

    # Filter so each swing high is separated by at least min_gap candles (keeping higher if too close)
    filtered: list[dict[str, Any]] = []
    for cand in raw_highs:
        if not filtered:
            filtered.append(cand)
        elif cand["index"] - filtered[-1]["index"] < min_gap:
            if cand["price"] > filtered[-1]["price"]:
                filtered[-1] = cand
        else:
            filtered.append(cand)

    return filtered


def _trendline_payload(
    p1: dict[str, Any],
    p2: dict[str, Any],
    total_bars: int,
    candles: list[dict[str, Any]],
    p3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate extended trendline passing through p1 and p2 (touching body tips).
    Extended in both directions (from bar 0 to last bar total_bars - 1).
    """
    dx = p2["index"] - p1["index"]
    slope = (p2["price"] - p1["price"]) / dx if dx > 0 else 0.0

    last_idx = total_bars - 1
    price_at_start = p1["price"] + slope * (0 - p1["index"])
    price_at_end = p1["price"] + slope * (last_idx - p1["index"])

    pivots_used = [p1, p2]
    if p3 is not None:
        pivots_used.append(p3)

    return {
        "start": {"index": 0, "date": _day(candles[0]["date"]), "price": price_at_start},
        "end": {"index": last_idx, "date": _day(candles[last_idx]["date"]), "price": price_at_end},
        "p1": p1,
        "p2": p2,
        "p3": p3,
        "slope_per_bar": slope,
        "pivot_dates": [p["date"] for p in pivots_used],
        "pivot_count": len(pivots_used),
    }


def analyze_candles(
    candles: list[dict[str, Any]],
    swing_period: int = 30,
    min_pivot_gap: int = 10,
    signal_window: int = 10,
    lookback_candles: int = 365,
    min_right_bars: int = 3,
    pivot_depth_bars: int = 5,
    pivot_depth_pct: float = 2.0,
    trendline_k: int | None = None,
    min_touches: int = 3,
    breach_tolerance: float = 0.10,
    touch_tolerance: float = 0.25,
    max_wick_breaches: int = 2,
    volume_multiplier: float = 1.5,
    **kwargs: Any,
) -> dict[str, Any]:
    """Multi-Touch Diagonal Trendline & Breakout Detector (Technical Specification).
    - Constrained boundary envelope (No-Violation Rule for candle bodies)
    - Scale-invariant ATR-normalized slope filter
    - Volatility-normalized touch counting with cluster spacing (N_touches >= 3)
    - Composite structural quality scoring S(m, c)
    - Volume-confirmed decisive breakout detection at t_now or recent window
    """
    if "strength" in kwargs and swing_period == 40:
        swing_period = int(kwargs["strength"])

    if len(candles) > lookback_candles:
        candles = candles[-lookback_candles:]

    if len(candles) < 25:
        raise ValueError(f"Need at least 25 candles for multi-touch trendline analysis (have {len(candles)}).")

    # Determine k (pivot half-window)
    if trendline_k is not None and trendline_k >= 2:
        k_val = trendline_k
    elif swing_period <= 8:
        k_val = max(2, swing_period)
    else:
        k_val = max(3, min(6, swing_period // 6))

    min_space = max(5, min_pivot_gap)
    lookback_w = min(len(candles) - 1, max(60, min(lookback_candles, 180)))

    # Run multi-touch trendline detector
    res = analyze_multi_touch_trendlines(
        candles,
        direction="BOTH",
        k=k_val,
        lookback_window=lookback_w,
        min_anchor_spacing=min_space,
        min_norm_slope=0.05,
        max_norm_slope=0.40,
        breach_tolerance=breach_tolerance,
        max_wick_breaches=max_wick_breaches,
        touch_tolerance=touch_tolerance,
        min_touch_spacing=5,
        min_touches=min_touches,
        breakout_buffer=0.25,
        volume_multiplier=volume_multiplier,
        trendline_window=signal_window,
    )

    # Fallback to min_touches=2 if 3 touches were not found
    if res.get("selected") is None and min_touches > 2:
        res = analyze_multi_touch_trendlines(
            candles,
            direction="BOTH",
            k=k_val,
            lookback_window=lookback_w,
            min_anchor_spacing=min_space,
            min_norm_slope=0.05,
            max_norm_slope=0.40,
            breach_tolerance=breach_tolerance,
            max_wick_breaches=max_wick_breaches,
            touch_tolerance=touch_tolerance,
            min_touch_spacing=5,
            min_touches=2,
            breakout_buffer=0.25,
            volume_multiplier=volume_multiplier,
            trendline_window=signal_window,
        )

    last = candles[-1]
    previous = candles[-2] if len(candles) > 1 else last
    curr_close = float(last["close"])
    prev_close = float(previous["close"])

    selected = res.get("selected")
    if not selected:
        status_msg = (
            f"No trendline: No candidate lines met envelope & touch constraints "
            f"(k={k_val}, min touches: {min_touches}, breach tol: {breach_tolerance} ATR, "
            f"max wick breaches: {max_wick_breaches})."
        )
        return {
            "last_date": _day(last["date"]),
            "close": curr_close,
            "previous_close": prev_close,
            "resistance": None,
            "support": None,
            "resistance_line": None,
            "support_line": None,
            "swing_highs": [],
            "all_swing_highs": [],
            "swing_lows": [],
            "signals": [],
            "latest_signal": None,
            "status_text": status_msg,
            "distance_pct": None,
            "is_broken_out": False,
            "is_recent_breakout": False,
            "multi_touch_meta": None,
        }

    # Format touch points as swing highs with P1, P2... labels for SVG chart
    touches = selected.get("touches", [])
    swing_pivots = []
    for idx, pt in enumerate(touches):
        swing_pivots.append({
            "index": pt["index"],
            "date": pt["date"],
            "price": pt["price"],
            "high": pt["price"],
            "low": pt["price"],
            "open": pt["price"],
            "close": pt["price"],
            "label": f"P{idx + 1}" + ("*" if pt.get("is_anchor") else ""),
            "is_anchor": pt.get("is_anchor", False),
            "bars_ago": len(candles) - 1 - pt["index"],
        })

    curr_line = selected["projected_price"]
    is_res = selected["direction"] == "DESCENDING_RESISTANCE"
    is_broken_out = curr_close > curr_line if is_res else curr_close < curr_line

    dist_pct = round(((curr_line - curr_close) / curr_close) * 100, 2) if curr_close > 0 else 0.0

    breakout_events = res.get("breakout_events", [])
    latest_sig = res.get("latest_breakout")
    is_recent_breakout = res.get("is_recent_breakout", False)

    return {
        "last_date": _day(last["date"]),
        "close": curr_close,
        "previous_close": prev_close,
        "resistance": curr_line if is_res else None,
        "support": curr_line if not is_res else None,
        "resistance_line": selected if is_res else None,
        "support_line": selected if not is_res else res.get("support"),
        "swing_highs": swing_pivots if is_res else [],
        "swing_lows": swing_pivots if not is_res else [],
        "all_swing_highs": swing_pivots,
        "signals": breakout_events,
        "latest_signal": latest_sig,
        "is_recent_breakout": is_recent_breakout,
        "distance_pct": dist_pct,
        "is_broken_out": is_broken_out,
        "status_text": res.get("status_text", ""),
        "multi_touch_meta": selected,
        "touch_count": selected.get("touch_count", 0),
        "score": selected.get("score", 0.0),
    }


def analyze_sma(
    candles: list[dict[str, Any]],
    fast_period: int = 6,
    slow_period: int = 30,
    signal_window: int = 10,
) -> dict[str, Any]:
    """Tutorial strategy: close-confirmed fast/slow SMA crossovers."""
    if fast_period < 2 or slow_period <= fast_period:
        raise ValueError("Slow SMA must be longer than the fast SMA.")
    if len(candles) < slow_period + 2:
        raise ValueError(f"Need at least {slow_period + 2} daily candles for these SMA periods.")

    closes = [float(c["close"]) for c in candles]
    fast: list[float | None] = [None] * len(candles)
    slow: list[float | None] = [None] * len(candles)
    fast_sum = 0.0
    slow_sum = 0.0
    for i, close in enumerate(closes):
        fast_sum += close
        slow_sum += close
        if i >= fast_period:
            fast_sum -= closes[i - fast_period]
        if i >= slow_period:
            slow_sum -= closes[i - slow_period]
        if i >= fast_period - 1:
            fast[i] = fast_sum / fast_period
        if i >= slow_period - 1:
            slow[i] = slow_sum / slow_period

    first = max(slow_period, len(candles) - signal_window)
    events: list[dict[str, Any]] = []
    for i in range(first, len(candles)):
        if fast[i - 1] is None or slow[i - 1] is None or fast[i] is None or slow[i] is None:
            continue
        if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            events.append({"type": "bullish_cross", "date": _day(candles[i]["date"]), "close": closes[i], "line": fast[i]})
        elif fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
            events.append({"type": "bearish_cross", "date": _day(candles[i]["date"]), "close": closes[i], "line": fast[i]})

    events.sort(key=lambda event: event["date"], reverse=True)
    return {
        "last_date": _day(candles[-1]["date"]),
        "close": closes[-1],
        "previous_close": closes[-2],
        "fast_sma": fast[-1],
        "slow_sma": slow[-1],
        "fast_sma_series": fast,
        "slow_sma_series": slow,
        "signals": events,
        "latest_signal": events[0] if events else None,
    }


def compute_rsi(
    candles: list[dict[str, Any]],
    period: int = 14,
    signal_ma_period: int = 9,
) -> tuple[list[float | None], list[float | None]]:
    """Compute Wilder's RSI and its Signal Moving Average (SMA of RSI)."""
    n = len(candles)
    if n < period + 1:
        return [None] * n, [None] * n

    closes = [float(c["close"]) for c in candles]
    rsi: list[float | None] = [None] * n

    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0.0:
        rsi[period] = 100.0 if avg_gain > 0.0 else 50.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = round(100.0 - (100.0 / (1.0 + rs)), 2)

    for i in range(period + 1, n):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0.0:
            rsi[i] = 100.0 if avg_gain > 0.0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = round(100.0 - (100.0 / (1.0 + rs)), 2)

    rsi_signal: list[float | None] = [None] * n
    if signal_ma_period > 0:
        for i in range(n):
            if i >= period + signal_ma_period - 1:
                window_vals = [rsi[j] for j in range(i - signal_ma_period + 1, i + 1) if rsi[j] is not None]
                if len(window_vals) == signal_ma_period:
                    rsi_signal[i] = round(sum(window_vals) / signal_ma_period, 2)

    return rsi, rsi_signal


def analyze_rsi(
    candles: list[dict[str, Any]],
    period: int = 14,
    signal_ma_period: int = 9,
    oversold_threshold: float = 30.0,
    overbought_threshold: float = 70.0,
    signal_window: int = 10,
    rsi_rule: str = "any_bullish",
) -> dict[str, Any]:
    """Analyze RSI for Bullish and Bearish indicator crossover / threshold behaviors:
    1. Oversold Bounce: RSI crosses above oversold_threshold (e.g. 30).
    2. Midline Cross: RSI crosses above 50 (bullish) or below 50 (bearish).
    3. Signal MA Cross: RSI crosses above Signal MA (bullish) or below (bearish).
    4. Any Bullish: Matches if oversold bounce, midline cross, or MA cross occurred recently.
    """
    n = len(candles)
    if n < period + 2:
        raise ValueError(f"Need at least {period + 2} candles to calculate RSI({period}).")

    rsi_series, rsi_signal_series = compute_rsi(candles, period=period, signal_ma_period=signal_ma_period)

    first_idx = max(period + 1, n - signal_window)
    events: list[dict[str, Any]] = []

    for i in range(first_idx, n):
        cur_rsi = rsi_series[i]
        prev_rsi = rsi_series[i - 1]
        if cur_rsi is None or prev_rsi is None:
            continue

        c_date = _day(candles[i]["date"])
        c_close = float(candles[i]["close"])
        bars_ago = n - 1 - i

        is_oversold_bounce = (prev_rsi <= oversold_threshold) and (cur_rsi > oversold_threshold)
        is_overbought_drop = (prev_rsi >= overbought_threshold) and (cur_rsi < overbought_threshold)
        is_midline_bullish = (prev_rsi <= 50.0) and (cur_rsi > 50.0)
        is_midline_bearish = (prev_rsi >= 50.0) and (cur_rsi < 50.0)

        cur_sig = rsi_signal_series[i]
        prev_sig = rsi_signal_series[i - 1]
        is_ma_bullish = (cur_sig is not None and prev_sig is not None) and (prev_rsi <= prev_sig) and (cur_rsi > cur_sig)
        is_ma_bearish = (cur_sig is not None and prev_sig is not None) and (prev_rsi >= prev_sig) and (cur_rsi < cur_sig)

        if rsi_rule == "midline_cross":
            if is_midline_bullish:
                events.append({
                    "type": "rsi_bullish_midline",
                    "name": "RSI Bullish Midline Cross",
                    "bias": "bullish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI crossed above 50 ({prev_rsi:.1f} → {cur_rsi:.1f})",
                })
            elif is_midline_bearish:
                events.append({
                    "type": "rsi_bearish_midline",
                    "name": "RSI Bearish Midline Cross",
                    "bias": "bearish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI crossed below 50 ({prev_rsi:.1f} → {cur_rsi:.1f})",
                })
        elif rsi_rule == "ma_cross":
            if is_ma_bullish:
                events.append({
                    "type": "rsi_bullish_ma_cross",
                    "name": "RSI Bullish MA Cross",
                    "bias": "bullish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI {cur_rsi:.1f} crossed above Signal MA {cur_sig:.1f}",
                })
            elif is_ma_bearish:
                events.append({
                    "type": "rsi_bearish_ma_cross",
                    "name": "RSI Bearish MA Cross",
                    "bias": "bearish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI {cur_rsi:.1f} crossed below Signal MA {cur_sig:.1f}",
                })
        elif rsi_rule == "oversold_bounce":
            if is_oversold_bounce:
                events.append({
                    "type": "rsi_oversold_bounce",
                    "name": "RSI Oversold Bounce",
                    "bias": "bullish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI bounced out of oversold ({prev_rsi:.1f} → {cur_rsi:.1f})",
                })
            elif is_overbought_drop:
                events.append({
                    "type": "rsi_overbought_drop",
                    "name": "RSI Overbought Drop",
                    "bias": "bearish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI dropped out of overbought ({prev_rsi:.1f} → {cur_rsi:.1f})",
                })
        else:  # "any_bullish" (default)
            if is_oversold_bounce:
                events.append({
                    "type": "rsi_oversold_bounce",
                    "name": "RSI Oversold Bounce",
                    "bias": "bullish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI bounced out of oversold ({prev_rsi:.1f} → {cur_rsi:.1f})",
                })
            elif is_midline_bullish:
                events.append({
                    "type": "rsi_bullish_midline",
                    "name": "RSI Bullish Midline Cross",
                    "bias": "bullish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI crossed above 50 ({prev_rsi:.1f} → {cur_rsi:.1f})",
                })
            elif is_ma_bullish:
                events.append({
                    "type": "rsi_bullish_ma_cross",
                    "name": "RSI Bullish MA Cross",
                    "bias": "bullish",
                    "date": c_date,
                    "bar_index": i,
                    "bars_ago": bars_ago,
                    "close": c_close,
                    "rsi": cur_rsi,
                    "prev_rsi": prev_rsi,
                    "details": f"RSI {cur_rsi:.1f} crossed above Signal MA {cur_sig:.1f}",
                })

    events.sort(key=lambda ev: ev["bars_ago"])
    latest_event = events[0] if events else None
    last = candles[-1]
    prev = candles[-2] if len(candles) > 1 else last
    curr_rsi = rsi_series[-1]

    status_text = (
        f"{latest_event['name']} ({latest_event['bars_ago']}b ago, RSI={latest_event['rsi']})"
        if latest_event
        else f"RSI({period})={curr_rsi if curr_rsi is not None else '—'} (No cross in {signal_window}b)"
    )

    return {
        "last_date": _day(last["date"]),
        "close": float(last["close"]),
        "previous_close": float(prev["close"]),
        "rsi": curr_rsi,
        "rsi_signal": rsi_signal_series[-1],
        "rsi_series": rsi_series,
        "rsi_signal_series": rsi_signal_series,
        "signals": events,
        "latest_signal": latest_event,
        "status_text": status_text,
    }


def analyze_confluence(
    candles: list[dict[str, Any]],
    enabled_techniques: list[str],
    confluence_mode: str = "all",
    # Trendline settings
    swing_period: int = 30,
    min_pivot_gap: int = 10,
    trendline_window: int = 10,
    lookback_candles: int = 365,
    min_right_bars: int = 3,
    pivot_depth_bars: int = 5,
    pivot_depth_pct: float = 2.0,
    trendline_k: int = 4,
    min_touches: int = 3,
    breach_tolerance: float = 0.10,
    touch_tolerance: float = 0.25,
    max_wick_breaches: int = 2,
    volume_multiplier: float = 1.5,
    # Candlestick Pattern settings
    pattern_window: int = 10,
    pattern_filter: str | list[str] = "all",
    marubozu_delta: float = 0.005,
    hammer_shadow_ratio: float = 2.0,
    enforce_trap_filter: bool = False,
    # SMA settings
    fast_period: int = 6,
    slow_period: int = 30,
    sma_window: int = 10,
    # RSI settings
    rsi_period: int = 14,
    rsi_signal_ma_period: int = 9,
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
    rsi_window: int = 10,
    rsi_rule: str = "any_bullish",
) -> dict[str, Any]:
    """Scan and mix multiple techniques: Multi-Touch Trendline Breakout, Candlestick Patterns, SMA Crossover, and RSI.
    Supports matching ALL enabled techniques (Strict Confluence) or ANY enabled technique.
    """
    if not enabled_techniques:
        enabled_techniques = ["pattern", "trendline", "sma", "rsi"]

    trendline_res: dict[str, Any] = {}
    pattern_res: dict[str, Any] = {}
    sma_res: dict[str, Any] = {}
    rsi_res: dict[str, Any] = {}
    matches: dict[str, bool] = {}
    matched_badges: list[dict[str, Any]] = []

    if "trendline" in enabled_techniques:
        try:
            trendline_res = analyze_candles(
                candles,
                swing_period=swing_period,
                min_pivot_gap=min_pivot_gap,
                signal_window=trendline_window,
                lookback_candles=lookback_candles,
                min_right_bars=min_right_bars,
                pivot_depth_bars=pivot_depth_bars,
                pivot_depth_pct=pivot_depth_pct,
                trendline_k=trendline_k,
                min_touches=min_touches,
                breach_tolerance=breach_tolerance,
                touch_tolerance=touch_tolerance,
                max_wick_breaches=max_wick_breaches,
                volume_multiplier=volume_multiplier,
            )
            is_breakout = trendline_res.get("is_recent_breakout", False)
            matches["trendline"] = is_breakout
            if is_breakout and trendline_res.get("latest_signal"):
                sig = trendline_res["latest_signal"]
                v_ratio = sig.get("volume_ratio", 1.0)
                t_count = trendline_res.get("touch_count", 0)
                matched_badges.append({
                    "tech": "trendline",
                    "type": "breakout",
                    "label": "Trendline Breakout",
                    "date": sig.get("date"),
                    "bars_ago": sig.get("bars_ago", 0),
                    "details": f"+{sig.get('breakout_pct', 0)}% | {t_count} touches | Vol: {v_ratio}x",
                })
        except Exception:
            matches["trendline"] = False

    if "pattern" in enabled_techniques:
        try:
            pattern_res = analyze_candlestick_patterns(
                candles,
                pattern_window=pattern_window,
                marubozu_delta=marubozu_delta,
                hammer_shadow_ratio=hammer_shadow_ratio,
                enforce_trap_filter=enforce_trap_filter,
                pattern_filter=pattern_filter,
            )
            has_pattern = bool(pattern_res.get("latest_signal"))
            matches["pattern"] = has_pattern
            if has_pattern and pattern_res.get("latest_signal"):
                sig = pattern_res["latest_signal"]
                matched_badges.append({
                    "tech": "pattern",
                    "type": sig.get("type"),
                    "label": sig.get("name"),
                    "date": sig.get("date"),
                    "bars_ago": sig.get("bars_ago", 0),
                    "details": sig.get("details", ""),
                    "trap_status": sig.get("trap_status", ""),
                })
        except Exception:
            matches["pattern"] = False

    if "sma" in enabled_techniques:
        try:
            sma_res = analyze_sma(
                candles,
                fast_period=fast_period,
                slow_period=slow_period,
                signal_window=sma_window,
            )
            has_sma = bool(sma_res.get("latest_signal"))
            matches["sma"] = has_sma
            if has_sma and sma_res.get("latest_signal"):
                sig = sma_res["latest_signal"]
                label = "Bullish SMA Cross" if sig.get("type") == "bullish_cross" else "Bearish SMA Cross"
                matched_badges.append({
                    "tech": "sma",
                    "type": sig.get("type"),
                    "label": label,
                    "date": sig.get("date"),
                    "bars_ago": (len(candles) - 1 - candles.index(next(c for c in candles if _day(c["date"]) == sig.get("date")))) if any(_day(c["date"]) == sig.get("date") for c in candles) else 0,
                    "details": f"Fast: {round(sig.get('line', 0), 1)}",
                })
        except Exception:
            matches["sma"] = False

    if "rsi" in enabled_techniques:
        try:
            rsi_res = analyze_rsi(
                candles,
                period=rsi_period,
                signal_ma_period=rsi_signal_ma_period,
                oversold_threshold=rsi_oversold,
                overbought_threshold=rsi_overbought,
                signal_window=rsi_window,
                rsi_rule=rsi_rule,
            )
            has_rsi = bool(rsi_res.get("latest_signal"))
            matches["rsi"] = has_rsi
            if has_rsi and rsi_res.get("latest_signal"):
                sig = rsi_res["latest_signal"]
                matched_badges.append({
                    "tech": "rsi",
                    "type": sig.get("type"),
                    "label": sig.get("name"),
                    "date": sig.get("date"),
                    "bars_ago": sig.get("bars_ago", 0),
                    "details": sig.get("details", ""),
                    "rsi": sig.get("rsi"),
                })
        except Exception:
            matches["rsi"] = False

    matched_count = sum(1 for m in matches.values() if m)
    total_enabled = len(enabled_techniques)

    if confluence_mode == "all":
        is_signal = (matched_count == total_enabled) and (total_enabled > 0)
    else:  # "any"
        is_signal = (matched_count > 0)

    # Sort badges so the latest trigger is first
    if matched_badges:
        matched_badges.sort(key=lambda b: b.get("bars_ago", 999))
    latest_sig = matched_badges[0] if matched_badges else None

    last = candles[-1]
    prev = candles[-2] if len(candles) > 1 else last

    status_parts = [b["label"] for b in matched_badges]
    status_text = " + ".join(status_parts) if status_parts else "Watching"

    return {
        "last_date": _day(last["date"]),
        "close": float(last["close"]),
        "previous_close": float(prev["close"]),
        "is_confluence_signal": is_signal,
        "matched_count": matched_count,
        "total_enabled": total_enabled,
        "confluence_score": f"{matched_count}/{total_enabled}",
        "matched_badges": matched_badges,
        "latest_signal": latest_sig,
        "status_text": status_text,
        # Trendline overlay
        "resistance_line": trendline_res.get("resistance_line"),
        "support_line": trendline_res.get("support_line"),
        "swing_highs": trendline_res.get("swing_highs", []),
        "swing_lows": trendline_res.get("swing_lows", []),
        "resistance": trendline_res.get("resistance"),
        "distance_pct": trendline_res.get("distance_pct"),
        "is_broken_out": trendline_res.get("is_broken_out", False),
        "is_recent_breakout": matches.get("trendline", False),
        "multi_touch_meta": trendline_res.get("multi_touch_meta"),
        # Candlestick pattern overlay
        "annotated_patterns": pattern_res.get("annotated_patterns", []),
        "pattern_count": pattern_res.get("pattern_count", 0),
        # SMA overlay
        "fast_sma_series": sma_res.get("fast_sma_series", []),
        "slow_sma_series": sma_res.get("slow_sma_series", []),
        "fast_sma": sma_res.get("fast_sma"),
        "slow_sma": sma_res.get("slow_sma"),
        # RSI overlay
        "rsi": rsi_res.get("rsi"),
        "rsi_signal": rsi_res.get("rsi_signal"),
        "rsi_series": rsi_res.get("rsi_series", []),
        "rsi_signal_series": rsi_res.get("rsi_signal_series", []),
    }

