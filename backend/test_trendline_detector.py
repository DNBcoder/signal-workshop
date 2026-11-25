"""Unit tests for Multi-Touch Diagonal Trendline & Breakout Detector
Tests:
1. Synthetic linear descending resistance with 4 known touches
2. Rejection upon single candle body violation
3. Wick breaches tolerance and limit rejection
4. Low volume vs. high volume breakout triggers
5. Ascending support (bearish breakdown) symmetry
6. Scale invariance across price scales
"""

import math
import numpy as np

from trendline_detector import (
    compute_atr,
    compute_volume_sma,
    extract_pivots,
    detect_trendlines_for_direction,
    analyze_multi_touch_trendlines,
)


def generate_synthetic_candles(
    n: int = 100,
    slope: float = -0.25,
    intercept: float = 100.0,
    pivot_bars: list[int] = [15, 35, 55, 75],
    k: int = 4,
    body_violation_bar: int | None = None,
    wick_breach_bars: list[int] = [],
    breakout_bar: int | None = None,
    breakout_volume_multiplier: float = 2.0,
    direction: str = "DESCENDING_RESISTANCE",
) -> list[dict]:
    """Create deterministic synthetic OHLCV data."""
    candles = []
    is_res = direction == "DESCENDING_RESISTANCE"

    for t in range(n):
        line_val = slope * t + intercept
        # Base body safely away from line
        if is_res:
            close_base = line_val - 2.5
            open_base = line_val - 3.0
            high_base = line_val - 1.5
            low_base = line_val - 4.5
        else:
            close_base = line_val + 2.5
            open_base = line_val + 3.0
            high_base = line_val + 4.5
            low_base = line_val + 1.5

        vol = 1000.0

        # Create swing pivot touch
        if t in pivot_bars:
            if is_res:
                high_val = line_val  # Exact touch
                open_val = line_val - 0.8
                close_val = line_val - 0.5
                low_val = line_val - 2.0
            else:
                low_val = line_val  # Exact touch
                open_val = line_val + 0.8
                close_val = line_val + 0.5
                high_val = line_val + 2.0
        elif any(abs(t - p) <= k for p in pivot_bars):
            # Neighborhood around pivot must be lower (for resistance) or higher (for support)
            dist = min(abs(t - p) for p in pivot_bars)
            drop = 1.0 + (k - dist) * 0.4
            if is_res:
                high_val = high_base - drop
                open_val = open_base - drop
                close_val = close_base - drop
                low_val = low_base - drop
            else:
                high_val = high_base + drop
                open_val = open_base + drop
                close_val = close_base + drop
                low_val = low_base + drop
        else:
            open_val = open_base
            close_val = close_base
            high_val = high_base
            low_val = low_base

        # Body violation candle injection
        if body_violation_bar is not None and t == body_violation_bar:
            if is_res:
                open_val = line_val + 1.5
                close_val = line_val + 2.0
                high_val = line_val + 2.5
            else:
                open_val = line_val - 1.5
                close_val = line_val - 2.0
                low_val = line_val - 2.5

        # Wick breach injection
        if t in wick_breach_bars:
            if is_res:
                high_val = line_val + 1.2  # Spike above line
                open_val = line_val - 1.5
                close_val = line_val - 1.0  # Body remains valid below
            else:
                low_val = line_val - 1.2
                open_val = line_val + 1.5
                close_val = line_val + 1.0

        # Breakout candle injection
        if breakout_bar is not None and t == breakout_bar:
            if is_res:
                open_val = line_val - 0.2
                close_val = line_val + 3.0  # Decisive close above
                high_val = line_val + 3.5
                low_val = line_val - 0.5
            else:
                open_val = line_val + 0.2
                close_val = line_val - 3.0  # Decisive close below
                low_val = line_val - 3.5
                high_val = line_val + 0.5
            vol = 1000.0 * breakout_volume_multiplier

        candles.append({
            "date": f"2026-01-{(t % 28) + 1:02d}",
            "open": round(open_val, 2),
            "high": round(high_val, 2),
            "low": round(low_val, 2),
            "close": round(close_val, 2),
            "volume": round(vol, 0),
        })
    return candles


def test_synthetic_descending_resistance_detection():
    """Verify clean 4-touch descending resistance line is identified with high score."""
    candles = generate_synthetic_candles(n=90, slope=-0.25, intercept=100.0, pivot_bars=[15, 35, 55, 75])
    result = analyze_multi_touch_trendlines(candles, direction="DESCENDING_RESISTANCE", k=4)

    assert result["selected"] is not None
    line = result["selected"]
    assert line["direction"] == "DESCENDING_RESISTANCE"
    assert math.isclose(line["slope"], -0.25, abs_tol=0.05)
    assert line["touch_count"] >= 3
    assert line["wick_breaches"] == 0
    assert line["score"] > 5.0
    print(f"Test 1 Passed: Detected descending line slope={line['slope']} touches={line['touch_count']} score={line['score']}")


def test_body_violation_rejection():
    """Verify candidate line is rejected if a single candle body breaches ceiling beyond tolerance."""
    # Bar 45 has candle body violating the envelope
    candles = generate_synthetic_candles(
        n=90, slope=-0.25, intercept=100.0, pivot_bars=[15, 35, 55, 75], body_violation_bar=45
    )
    result = analyze_multi_touch_trendlines(candles, direction="DESCENDING_RESISTANCE", k=4)

    # Line passing through 15 and 75 must be rejected because bar 45 violated envelope
    if result["selected"] is not None:
        anchors = result["selected"]["anchor_bars"]
        # Ensure the violated pair [15, 75] or [15, 55] spanning over 45 was not accepted
        assert not (anchors[0] < 45 < anchors[1]), "Envelope violation was not rejected!"
    print("Test 2 Passed: Body violation correctly rejected")


def test_wick_breaches_tolerance_and_rejection():
    """Verify that up to max_wick_breaches (2) are tolerated, but > 2 causes rejection."""
    # 1 wick breach is allowed
    candles_1 = generate_synthetic_candles(
        n=90, slope=-0.25, intercept=100.0, pivot_bars=[15, 35, 55, 75], wick_breach_bars=[25]
    )
    res_1 = analyze_multi_touch_trendlines(candles_1, direction="DESCENDING_RESISTANCE", k=4)
    assert res_1["selected"] is not None
    assert res_1["selected"]["wick_breaches"] == 1

    # 3 wick breaches exceeds default max_wick_breaches=2, so candidate line must be rejected
    candles_3 = generate_synthetic_candles(
        n=90, slope=-0.25, intercept=100.0, pivot_bars=[15, 35, 55, 75], wick_breach_bars=[25, 45, 65]
    )
    res_3 = analyze_multi_touch_trendlines(candles_3, direction="DESCENDING_RESISTANCE", k=4, max_wick_breaches=2)
    if res_3["selected"] is not None:
        anchors = res_3["selected"]["anchor_bars"]
        assert not (anchors[0] <= 15 and anchors[1] >= 75), "Excess wick breaches line was not rejected!"
    print("Test 3 Passed: Wick breaches tolerance & limit enforced")


def test_breakout_volume_confirmation():
    """Verify breakout confirmation requires volume multiplier >= lambda_vol (1.5)."""
    # Breakout at bar 85 with LOW volume (0.8x)
    candles_low_vol = generate_synthetic_candles(
        n=90, slope=-0.25, intercept=100.0, pivot_bars=[15, 35, 55, 75], breakout_bar=85, breakout_volume_multiplier=0.8
    )
    res_low = analyze_multi_touch_trendlines(candles_low_vol, direction="DESCENDING_RESISTANCE", k=4, trendline_window=10)
    assert res_low["selected"] is not None
    # Low volume breakout must NOT emit confirmed breakout
    assert res_low["is_recent_breakout"] is False

    # Breakout at bar 85 with HIGH volume (2.5x)
    candles_high_vol = generate_synthetic_candles(
        n=90, slope=-0.25, intercept=100.0, pivot_bars=[15, 35, 55, 75], breakout_bar=85, breakout_volume_multiplier=2.5
    )
    res_high = analyze_multi_touch_trendlines(candles_high_vol, direction="DESCENDING_RESISTANCE", k=4, trendline_window=10)
    assert res_high["selected"] is not None
    assert res_high["is_recent_breakout"] is True
    assert len(res_high["breakout_events"]) >= 1
    assert res_high["latest_breakout"]["volume_ratio"] >= 1.5
    print(f"Test 4 Passed: Low vol rejected, High vol confirmed (ratio={res_high['latest_breakout']['volume_ratio']})")


def test_ascending_support_symmetry():
    """Verify ascending support (bearish breakdown) detection."""
    candles = generate_synthetic_candles(
        n=90, slope=0.20, intercept=50.0, pivot_bars=[15, 35, 55, 75], direction="ASCENDING_SUPPORT", breakout_bar=85, breakout_volume_multiplier=2.2
    )
    result = analyze_multi_touch_trendlines(candles, direction="ASCENDING_SUPPORT", k=4, trendline_window=10)
    assert result["support"] is not None
    supp = result["support"]
    assert supp["direction"] == "ASCENDING_SUPPORT"
    assert math.isclose(supp["slope"], 0.20, abs_tol=0.05)
    assert supp["touch_count"] >= 3
    assert result["is_recent_breakout"] is True
    assert result["latest_breakout"]["type"] == "short_breakout"
    print(f"Test 5 Passed: Ascending support breakdown detected (slope={supp['slope']})")


def test_scale_invariance():
    """Verify detector works identically on small-cap ($10) and high-value ($10,000) assets."""
    # Scale 1: Base prices around 100
    c_1 = generate_synthetic_candles(n=90, slope=-0.25, intercept=100.0, pivot_bars=[15, 35, 55, 75])
    res_1 = analyze_multi_touch_trendlines(c_1, direction="DESCENDING_RESISTANCE", k=4)

    # Scale 2: Same geometry scaled by 100x (prices around 10,000)
    c_2 = []
    for bar in c_1:
        c_2.append({
            "date": bar["date"],
            "open": round(bar["open"] * 100.0, 2),
            "high": round(bar["high"] * 100.0, 2),
            "low": round(bar["low"] * 100.0, 2),
            "close": round(bar["close"] * 100.0, 2),
            "volume": bar["volume"],
        })
    res_2 = analyze_multi_touch_trendlines(c_2, direction="DESCENDING_RESISTANCE", k=4)

    assert res_1["selected"] is not None and res_2["selected"] is not None
    # Normalized slopes should match
    norm_slope_1 = res_1["selected"]["normalized_slope"]
    norm_slope_2 = res_2["selected"]["normalized_slope"]
    assert math.isclose(norm_slope_1, norm_slope_2, rel_tol=0.05)
    # Touch counts and anchors must be identical
    assert res_1["selected"]["touch_count"] == res_2["selected"]["touch_count"]
    assert res_1["selected"]["anchor_bars"] == res_2["selected"]["anchor_bars"]
    print(f"Test 6 Passed: Scale-invariance verified (norm_slope_1={norm_slope_1}, norm_slope_2={norm_slope_2})")


if __name__ == "__main__":
    test_synthetic_descending_resistance_detection()
    test_body_violation_rejection()
    test_wick_breaches_tolerance_and_rejection()
    test_breakout_volume_confirmation()
    test_ascending_support_symmetry()
    test_scale_invariance()
    print("ALL 6 RIGOROUS TECHNICAL SPECIFICATION UNIT TESTS PASSED!")
