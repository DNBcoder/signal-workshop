"""Multi-Touch Diagonal Trendline & Breakout Detector
Technical Specification Implementation:
- Constrained boundary envelope (No-Violation rule for candle bodies)
- Scale-invariant ATR-normalized slope filter
- Volatility-normalized touch counting with cluster spacing
- Composite structural quality scoring
- Volume-confirmed decisive breakout detection
- Symmetry for Descending Resistance and Ascending Support
"""

from __future__ import annotations

import math
from typing import Any, Literal
import numpy as np


def compute_atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Compute Average True Range (ATR) with Wilder's smoothing.
    TR(t) = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
    """
    n = len(highs)
    if n == 0:
        return np.array([], dtype=float)

    tr = np.zeros(n, dtype=float)
    tr[0] = max(0.0, float(highs[0] - lows[0]))
    for i in range(1, n):
        tr[i] = max(
            float(highs[i] - lows[i]),
            abs(float(highs[i] - closes[i - 1])),
            abs(float(lows[i] - closes[i - 1])),
        )

    atr = np.zeros(n, dtype=float)
    if n < period:
        # Running cumulative mean for small series
        atr[:] = np.maximum(1e-6, np.cumsum(tr) / (np.arange(n) + 1))
        return atr

    # First ATR value is SMA over initial period
    atr[period - 1] = max(1e-6, float(np.mean(tr[:period])))
    for i in range(period - 1):
        atr[i] = max(1e-6, float(np.mean(tr[: i + 1])))

    # Wilder's smoothing for subsequent bars
    for i in range(period, n):
        atr[i] = max(1e-6, (atr[i - 1] * (period - 1) + tr[i]) / period)

    return atr


def compute_volume_sma(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    """Compute rolling Simple Moving Average (SMA) of volume."""
    n = len(volumes)
    sma = np.zeros(n, dtype=float)
    if n == 0:
        return sma

    cumsum = np.cumsum(volumes, dtype=float)
    for i in range(n):
        if i < period:
            sma[i] = cumsum[i] / (i + 1)
        else:
            sma[i] = (cumsum[i] - cumsum[i - period]) / period
    return sma


def extract_pivots(
    prices: np.ndarray,
    kind: Literal["high", "low"],
    k: int = 4,
    lookback_window: int = 120,
    t_now: int | None = None,
) -> list[int]:
    """Extract local swing pivots with no-lookahead constraint.
    Swing high: H(t_i) == max(H[t_i - k : t_i + k + 1])
    Swing low:  L(t_i) == min(L[t_i - k : t_i + k + 1])
    Constraint: t_now >= t_i + k (pivot confirmed on or before t_now).
    Lookback:   t_i >= t_now - lookback_window.
    """
    n = len(prices)
    if t_now is None:
        t_now = n - 1
    if t_now < 2 * k:
        return []

    min_t = max(k, t_now - lookback_window)
    max_t = t_now - k  # Confirmed without lookahead

    pivots: list[int] = []
    for i in range(min_t, max_t + 1):
        window = prices[i - k : i + k + 1]
        val = prices[i]
        if kind == "high":
            if val == np.max(window) and np.count_nonzero(window == val) == 1:
                pivots.append(i)
            elif val == np.max(window) and i == (i - k + int(np.argmax(window))):
                pivots.append(i)
        else:
            if val == np.min(window) and np.count_nonzero(window == val) == 1:
                pivots.append(i)
            elif val == np.min(window) and i == (i - k + int(np.argmin(window))):
                pivots.append(i)

    return pivots


def cluster_touches(raw_touches: list[int], errors: np.ndarray, min_space: int = 5) -> list[int]:
    """Greedily filter raw touches so consecutive touches satisfy t_{r+1} - t_r >= min_space.
    Within any cluster of touches within min_space, select the bar with minimum error.
    """
    if not raw_touches:
        return []

    clusters: list[list[int]] = []
    current_cluster: list[int] = [raw_touches[0]]

    for t in raw_touches[1:]:
        if t - current_cluster[-1] < min_space:
            current_cluster.append(t)
        else:
            clusters.append(current_cluster)
            current_cluster = [t]
    if current_cluster:
        clusters.append(current_cluster)

    chosen: list[int] = []
    for cl in clusters:
        # Pick the touch bar with minimum absolute distance to trendline
        best_bar = min(cl, key=lambda bar: float(errors[bar]))
        if not chosen:
            chosen.append(best_bar)
        else:
            if best_bar - chosen[-1] >= min_space:
                chosen.append(best_bar)
            else:
                # If adjacent cluster best bar is still closer than min_space, keep the better one
                if errors[best_bar] < errors[chosen[-1]]:
                    chosen[-1] = best_bar

    return chosen


def detect_trendlines_for_direction(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    atr_14: np.ndarray,
    vol_sma_20: np.ndarray,
    direction: Literal["DESCENDING_RESISTANCE", "ASCENDING_SUPPORT"] = "DESCENDING_RESISTANCE",
    t_now: int | None = None,
    # Hyperparameters from specification
    k: int = 4,
    lookback_window: int = 120,
    min_anchor_spacing: int = 10,
    min_norm_slope: float = 0.05,
    max_norm_slope: float = 0.40,
    breach_tolerance: float = 0.10,
    max_wick_breaches: int = 2,
    touch_tolerance: float = 0.25,
    min_touch_spacing: int = 5,
    min_touches: int = 3,
    breakout_buffer: float = 0.25,
    volume_multiplier: float = 1.5,
    score_weights: tuple[float, float, float, float] = (2.0, 0.5, 1.5, 0.75),
    require_freshness: bool = True,
) -> dict[str, Any] | None:
    """Evaluate all candidate lines for the specified direction and return the
    highest scoring line adhering to the constrained boundary envelope.
    """
    n = len(closes)
    if t_now is None:
        t_now = n - 1
    if t_now < 2 * k + min_anchor_spacing:
        return None

    w1, w2, w3, w4 = score_weights
    is_resistance = direction == "DESCENDING_RESISTANCE"

    # Step 1: Swing Pivot Extraction
    pivot_kind = "high" if is_resistance else "low"
    pivot_prices = highs if is_resistance else lows
    pivots = extract_pivots(pivot_prices, kind=pivot_kind, k=k, lookback_window=lookback_window, t_now=t_now)

    if len(pivots) < 2:
        return None

    body_max = np.maximum(opens, closes)
    body_min = np.minimum(opens, closes)

    candidate_results: list[dict[str, Any]] = []

    # Step 2: Iterate ordered candidate anchor pairs (t_a, t_b)
    for i in range(len(pivots)):
        t_a = pivots[i]
        p_a = float(pivot_prices[t_a])

        for j in range(i + 1, len(pivots)):
            t_b = pivots[j]
            p_b = float(pivot_prices[t_b])

            # Condition 1: Minimum anchor separation
            dt = t_b - t_a
            if dt < min_anchor_spacing:
                continue

            # Condition 2: Strict directional slope
            if is_resistance and p_b >= p_a:
                continue
            if (not is_resistance) and p_b <= p_a:
                continue

            m = (p_b - p_a) / float(dt)
            c = p_a - m * t_a

            # Mean ATR over active lookback window [t_a, t_now]
            window_atr = atr_14[t_a : t_now + 1]
            if len(window_atr) == 0:
                continue
            mean_atr = float(np.mean(window_atr))
            if mean_atr <= 1e-6 or np.isnan(mean_atr):
                continue

            # Step 3: Scale-Invariant Slope Filter
            m_norm = abs(m) / mean_atr
            if not (min_norm_slope <= m_norm <= max_norm_slope):
                continue

            # Identify if a breakout occurred after anchor t_b
            first_breakout_bar = None
            for k_bar in range(t_b + 1, t_now + 1):
                y_k = m * k_bar + c
                atr_k = float(atr_14[k_bar])
                vol_k = float(volumes[k_bar])
                vol_sma_k = float(vol_sma_20[k_bar]) if k_bar < len(vol_sma_20) else 0.0
                vol_ok = (vol_sma_k <= 0) or (vol_k >= volume_multiplier * vol_sma_k)
                if is_resistance:
                    if float(closes[k_bar]) > (y_k + breakout_buffer * atr_k) and vol_ok:
                        first_breakout_bar = k_bar
                        break
                else:
                    if float(closes[k_bar]) < (y_k - breakout_buffer * atr_k) and vol_ok:
                        first_breakout_bar = k_bar
                        break

            # The pre-breakout envelope must be strictly respected between t_a and min(t_now - 1, first_breakout_bar - 1)
            t_eval_limit = first_breakout_bar if first_breakout_bar is not None else t_now
            eval_indices = np.arange(t_a, t_eval_limit)
            if len(eval_indices) == 0:
                continue

            y_hat_eval = m * eval_indices + c
            atr_eval = atr_14[t_a:t_eval_limit]
            eps_eval = breach_tolerance * atr_eval

            # Step 4: Envelope Constraint (No-Violation Rule)
            if is_resistance:
                # Candle bodies must not violate ceiling beyond epsilon
                body_viol = body_max[t_a:t_eval_limit] > (y_hat_eval + eps_eval)
                if np.any(body_viol):
                    continue

                # Wick breaches: High exceeds ceiling + epsilon while body remains valid
                wick_breaches = int(np.sum(highs[t_a:t_eval_limit] > (y_hat_eval + eps_eval)))
                if wick_breaches > max_wick_breaches:
                    continue

                # Step 5: Volatility-Normalized Touch Counting
                diff = np.abs(highs[t_a:t_eval_limit] - y_hat_eval)
                touch_mask = diff <= (touch_tolerance * atr_eval)
            else:
                # Ascending Support: Candle bodies must not violate floor
                body_viol = body_min[t_a:t_eval_limit] < (y_hat_eval - eps_eval)
                if np.any(body_viol):
                    continue

                # Wick breaches: Low dips below floor - epsilon while body valid
                wick_breaches = int(np.sum(lows[t_a:t_eval_limit] < (y_hat_eval - eps_eval)))
                if wick_breaches > max_wick_breaches:
                    continue

                diff = np.abs(lows[t_a:t_eval_limit] - y_hat_eval)
                touch_mask = diff <= (touch_tolerance * atr_eval)

            raw_touch_bars = eval_indices[touch_mask].tolist()

            # Ensure anchor points t_a and t_b are included if valid
            if t_a not in raw_touch_bars:
                raw_touch_bars.insert(0, t_a)
            if t_b not in raw_touch_bars:
                raw_touch_bars.append(t_b)
            raw_touch_bars = sorted(set(raw_touch_bars))

            # Full error vector for clustering
            full_errors = np.abs((highs if is_resistance else lows) - (m * np.arange(n) + c))
            touches = cluster_touches(raw_touch_bars, full_errors, min_space=min_touch_spacing)

            touch_count = len(touches)
            if touch_count < min_touches:
                continue

            # Step 6: Composite Objective Scoring
            t_first = min(touches)
            t_last = max(touches)
            span = max(1, t_last - t_first)

            touch_prices = (highs if is_resistance else lows)[touches]
            y_hat_touches = m * np.array(touches, dtype=float) + c
            rmse_touches = float(np.sqrt(np.mean((touch_prices - y_hat_touches) ** 2)))
            touch_rmse_atr = rmse_touches / mean_atr

            score = (
                w1 * float(touch_count)
                + w2 * float(math.log(span))
                - w3 * touch_rmse_atr
                - w4 * float(wick_breaches)
            )

            # Step 7: Breakout Confirmation Trigger at t_now
            y_hat_now = m * t_now + c
            atr_now = float(atr_14[t_now])
            vol_now = float(volumes[t_now])
            vol_sma_now = float(vol_sma_20[t_now]) if t_now < len(vol_sma_20) else 0.0

            vol_ratio = (
                vol_now / max(vol_sma_now, 1e-6)
                if vol_sma_now > 0
                else 1.0  # Pass volume check if no volume data is provided
            )
            has_vol = (vol_sma_now <= 0) or (vol_now >= volume_multiplier * vol_sma_now)

            if is_resistance:
                is_breakout_now = float(closes[t_now]) > (y_hat_now + breakout_buffer * atr_now) and has_vol
                if require_freshness and is_breakout_now and t_now > 0:
                    y_hat_prev = m * (t_now - 1) + c
                    if float(closes[t_now - 1]) > (y_hat_prev + breakout_buffer * float(atr_14[t_now - 1])):
                        # Already broken out on previous bar
                        is_breakout_now = False
            else:
                is_breakout_now = float(closes[t_now]) < (y_hat_now - breakout_buffer * atr_now) and has_vol
                if require_freshness and is_breakout_now and t_now > 0:
                    y_hat_prev = m * (t_now - 1) + c
                    if float(closes[t_now - 1]) < (y_hat_prev - breakout_buffer * float(atr_14[t_now - 1])):
                        is_breakout_now = False

            candidate_results.append({
                "direction": direction,
                "slope": float(m),
                "intercept": float(c),
                "normalized_slope": round(float(m_norm), 4),
                "anchor_bars": [int(t_a), int(t_b)],
                "touch_bars": [int(t) for t in touches],
                "touch_count": int(touch_count),
                "touch_rmse_atr": round(float(touch_rmse_atr), 4),
                "wick_breaches": int(wick_breaches),
                "score": round(float(score), 4),
                "projected_price": round(float(y_hat_now), 4),
                "breakout_signal": bool(is_breakout_now),
                "volume_ratio": round(float(vol_ratio), 2),
                "mean_atr": round(float(mean_atr), 4),
                "t_now": int(t_now),
            })

    if not candidate_results:
        return None

    # Step 6: Select highest-scoring active trendline (m*, c*) = argmax S(m, c)
    best_line = max(candidate_results, key=lambda x: x["score"])
    return best_line


def scan_breakout_events_in_window(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    atr_14: np.ndarray,
    vol_sma_20: np.ndarray,
    best_line: dict[str, Any],
    window_bars: int = 10,
    breakout_buffer: float = 0.25,
    volume_multiplier: float = 1.5,
) -> list[dict[str, Any]]:
    """Scan the recent window of bars [t_now - window_bars + 1, t_now] to find
    all confirmed breakout crossings of the best line.
    """
    n = len(closes)
    t_now = best_line.get("t_now", n - 1)
    m = best_line["slope"]
    c = best_line["intercept"]
    is_resistance = best_line["direction"] == "DESCENDING_RESISTANCE"

    t_b = best_line["anchor_bars"][1]
    # Breakout can only happen after the second anchor pivot t_b
    start_k = max(t_b + 1, t_now - window_bars + 1)
    if start_k >= n:
        return []

    breakout_events: list[dict[str, Any]] = []

    for k_bar in range(start_k, t_now + 1):
        y_curr = m * k_bar + c
        y_prev = m * (k_bar - 1) + c
        atr_curr = float(atr_14[k_bar])
        atr_prev = float(atr_14[k_bar - 1]) if k_bar > 0 else atr_curr

        c_curr = float(closes[k_bar])
        c_prev = float(closes[k_bar - 1]) if k_bar > 0 else c_curr

        v_curr = float(volumes[k_bar])
        v_sma = float(vol_sma_20[k_bar]) if k_bar < len(vol_sma_20) else 0.0
        v_ratio = v_curr / max(v_sma, 1e-6) if v_sma > 0 else 1.0
        has_vol = (v_sma <= 0) or (v_curr >= volume_multiplier * v_sma)

        if is_resistance:
            # Bullish breakout: previous bar below line, current bar decisive close above
            is_breakout = (c_prev <= y_prev) and (c_curr > (y_curr + breakout_buffer * atr_curr)) and has_vol
            pct_above = ((c_curr - y_curr) / y_curr) * 100.0 if y_curr > 0 else 0.0
            if is_breakout:
                breakout_events.append({
                    "bar_index": int(k_bar),
                    "bars_ago": int(t_now - k_bar),
                    "line_price": round(float(y_curr), 4),
                    "close_price": round(float(c_curr), 4),
                    "breakout_pct": round(float(pct_above), 2),
                    "volume_ratio": round(float(v_ratio), 2),
                    "type": "long_breakout",
                })
        else:
            # Bearish breakout: previous bar above line, current bar decisive close below
            is_breakout = (c_prev >= y_prev) and (c_curr < (y_curr - breakout_buffer * atr_curr)) and has_vol
            pct_below = ((y_curr - c_curr) / y_curr) * 100.0 if y_curr > 0 else 0.0
            if is_breakout:
                breakout_events.append({
                    "bar_index": int(k_bar),
                    "bars_ago": int(t_now - k_bar),
                    "line_price": round(float(y_curr), 4),
                    "close_price": round(float(c_curr), 4),
                    "breakout_pct": round(float(pct_below), 2),
                    "volume_ratio": round(float(v_ratio), 2),
                    "type": "short_breakout",
                })

    return breakout_events


def analyze_multi_touch_trendlines(
    candles: list[dict[str, Any]],
    direction: Literal["BOTH", "DESCENDING_RESISTANCE", "ASCENDING_SUPPORT"] = "BOTH",
    k: int = 4,
    lookback_window: int = 120,
    min_anchor_spacing: int = 10,
    min_norm_slope: float = 0.05,
    max_norm_slope: float = 0.40,
    breach_tolerance: float = 0.10,
    max_wick_breaches: int = 2,
    touch_tolerance: float = 0.25,
    min_touch_spacing: int = 5,
    min_touches: int = 3,
    breakout_buffer: float = 0.25,
    volume_multiplier: float = 1.5,
    score_weights: tuple[float, float, float, float] = (2.0, 0.5, 1.5, 0.75),
    trendline_window: int = 10,
) -> dict[str, Any]:
    """Top-level multi-touch trendline analyzer conforming to Technical Specification.
    Returns:
    - resistance: Best descending resistance line (Bullish Breakout detector)
    - support: Best ascending support line (Bearish Breakout detector)
    - selected: The top active line for chart overlays and signals
    - breakout_events: List of confirmed breakout events in the recent window
    - is_recent_breakout: True if breakout event found within trendline_window
    """
    n = len(candles)
    if n == 0:
        return {"resistance": None, "support": None, "selected": None, "status_text": "No candle data"}

    opens = np.array([float(c["open"]) for c in candles], dtype=float)
    highs = np.array([float(c["high"]) for c in candles], dtype=float)
    lows = np.array([float(c["low"]) for c in candles], dtype=float)
    closes = np.array([float(c["close"]) for c in candles], dtype=float)
    volumes = np.array([float(c.get("volume", 0) or 0) for c in candles], dtype=float)

    atr_14 = compute_atr(highs, lows, closes, period=14)
    vol_sma_20 = compute_volume_sma(volumes, period=20)
    t_now = n - 1

    res_line = None
    supp_line = None

    if direction in ("BOTH", "DESCENDING_RESISTANCE"):
        res_line = detect_trendlines_for_direction(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            atr_14=atr_14,
            vol_sma_20=vol_sma_20,
            direction="DESCENDING_RESISTANCE",
            t_now=t_now,
            k=k,
            lookback_window=lookback_window,
            min_anchor_spacing=min_anchor_spacing,
            min_norm_slope=min_norm_slope,
            max_norm_slope=max_norm_slope,
            breach_tolerance=breach_tolerance,
            max_wick_breaches=max_wick_breaches,
            touch_tolerance=touch_tolerance,
            min_touch_spacing=min_touch_spacing,
            min_touches=min_touches,
            breakout_buffer=breakout_buffer,
            volume_multiplier=volume_multiplier,
            score_weights=score_weights,
        )

    if direction in ("BOTH", "ASCENDING_SUPPORT"):
        supp_line = detect_trendlines_for_direction(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            atr_14=atr_14,
            vol_sma_20=vol_sma_20,
            direction="ASCENDING_SUPPORT",
            t_now=t_now,
            k=k,
            lookback_window=lookback_window,
            min_anchor_spacing=min_anchor_spacing,
            min_norm_slope=min_norm_slope,
            max_norm_slope=max_norm_slope,
            breach_tolerance=breach_tolerance,
            max_wick_breaches=max_wick_breaches,
            touch_tolerance=touch_tolerance,
            min_touch_spacing=min_touch_spacing,
            min_touches=min_touches,
            breakout_buffer=breakout_buffer,
            volume_multiplier=volume_multiplier,
            score_weights=score_weights,
        )

    def _day_val(idx: int) -> str:
        if 0 <= idx < n:
            raw = candles[idx].get("date", "")
            return str(raw).split("T")[0]
        return ""

    def _enrich_line_geometry(line: dict[str, Any] | None) -> dict[str, Any] | None:
        if line is None:
            return None
        m = line["slope"]
        c = line["intercept"]
        start_price = float(m * 0 + c)
        end_price = float(m * (n - 1) + c)

        anchor_pivots = []
        for idx in line["anchor_bars"]:
            anchor_pivots.append({
                "index": int(idx),
                "date": _day_val(idx),
                "price": round(float(highs[idx] if line["direction"] == "DESCENDING_RESISTANCE" else lows[idx]), 4),
                "is_anchor": True,
            })

        touch_points = []
        for idx in line["touch_bars"]:
            touch_points.append({
                "index": int(idx),
                "date": _day_val(idx),
                "price": round(float(highs[idx] if line["direction"] == "DESCENDING_RESISTANCE" else lows[idx]), 4),
                "line_price": round(float(m * idx + c), 4),
                "is_anchor": idx in line["anchor_bars"],
            })

        line["start"] = {"index": 0, "date": _day_val(0), "price": round(start_price, 4)}
        line["end"] = {"index": n - 1, "date": _day_val(n - 1), "price": round(end_price, 4)}
        line["p1"] = anchor_pivots[0] if len(anchor_pivots) > 0 else None
        line["p2"] = anchor_pivots[1] if len(anchor_pivots) > 1 else None
        line["pivots"] = anchor_pivots
        line["touches"] = touch_points
        line["slope_per_bar"] = round(float(m), 5)
        return line

    res_line = _enrich_line_geometry(res_line)
    supp_line = _enrich_line_geometry(supp_line)

    # Choose primary active line: default to resistance (bullish breakout), or support if higher score
    selected_line = res_line
    if selected_line is None:
        selected_line = supp_line
    elif supp_line is not None and supp_line["score"] > selected_line["score"]:
        # If support has higher score and had breakout, or resistance had no breakout
        if supp_line.get("breakout_signal") and not selected_line.get("breakout_signal"):
            selected_line = supp_line

    breakout_events: list[dict[str, Any]] = []
    if selected_line is not None:
        raw_events = scan_breakout_events_in_window(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            atr_14=atr_14,
            vol_sma_20=vol_sma_20,
            best_line=selected_line,
            window_bars=trendline_window,
            breakout_buffer=breakout_buffer,
            volume_multiplier=volume_multiplier,
        )
        for ev in raw_events:
            idx = ev["bar_index"]
            ev["date"] = _day_val(idx)
            breakout_events.append(ev)

    is_recent_breakout = len(breakout_events) > 0 or bool(
        selected_line and selected_line.get("breakout_signal")
    )
    latest_event = breakout_events[-1] if breakout_events else None

    # Status text summary
    curr_close = float(closes[-1])
    if selected_line:
        proj_now = selected_line["projected_price"]
        dir_name = "Resistance" if selected_line["direction"] == "DESCENDING_RESISTANCE" else "Support"
        t_count = selected_line["touch_count"]
        rmse = selected_line["touch_rmse_atr"]
        score = selected_line["score"]

        if latest_event:
            status_text = (
                f"{dir_name} Breakout on {latest_event['date']} ({latest_event['bars_ago']}b ago, "
                f"+{latest_event['breakout_pct']}%, Vol: {latest_event['volume_ratio']}x, {t_count} touches, Score: {score})"
            )
        else:
            diff_pct = round(((curr_close - proj_now) / proj_now) * 100.0, 2)
            status_text = (
                f"{dir_name} ({t_count} touches, Score: {score}, RMSE: {rmse} ATR): "
                f"{abs(diff_pct)}% {'above' if diff_pct > 0 else 'below'} line"
            )
    else:
        status_text = "No valid multi-touch trendline found meeting envelope & touch constraints"

    return {
        "resistance": res_line,
        "support": supp_line,
        "selected": selected_line,
        "breakout_events": breakout_events,
        "latest_breakout": latest_event,
        "is_recent_breakout": is_recent_breakout,
        "status_text": status_text,
    }
