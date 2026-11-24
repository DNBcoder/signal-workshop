import { useCallback, useEffect, useMemo, useState } from "react";

const TIMEFRAME_CONFIGS = {
  "5m": {
    label: "5 Min (5M)",
    defaultLookback: 250,
    minLookback: 50,
    maxLookback: 600,
    defaultPeriod: 15,
    defaultGap: 6,
    defaultRightBars: 3,
    hint: "5-minute intraday bars (~3 to 8 trading days)",
  },
  "15m": {
    label: "15 Min (15M)",
    defaultLookback: 250,
    minLookback: 40,
    maxLookback: 800,
    defaultPeriod: 15,
    defaultGap: 6,
    defaultRightBars: 3,
    hint: "15-minute intraday bars (~10 to 25 trading days)",
  },
  "1h": {
    label: "1 Hour (1H)",
    defaultLookback: 200,
    minLookback: 30,
    maxLookback: 600,
    defaultPeriod: 12,
    defaultGap: 5,
    defaultRightBars: 3,
    hint: "1-hour intraday bars (~30 to 90 trading days)",
  },
  "1d": {
    label: "Daily (1D)",
    defaultLookback: 365,
    minLookback: 60,
    maxLookback: 1000,
    defaultPeriod: 30,
    defaultGap: 10,
    defaultRightBars: 3,
    hint: "Daily completed candles (up to 2 years)",
  },
  "1w": {
    label: "Weekly (1W)",
    defaultLookback: 104,
    minLookback: 26,
    maxLookback: 400,
    defaultPeriod: 12,
    defaultGap: 5,
    defaultRightBars: 2,
    hint: "Weekly candles (1 to 5 years)",
  },
  "1mo": {
    label: "Monthly (1M)",
    defaultLookback: 48,
    minLookback: 24,
    maxLookback: 140,
    defaultPeriod: 4,
    defaultGap: 3,
    defaultRightBars: 1,
    hint: "Monthly candles (3 to 10 years)",
  },
};

const PATTERN_OPTIONS = [
  { id: "bullish_marubozu", label: "Bullish Marubozu", bias: "Bullish" },
  { id: "hammer", label: "Hammer", bias: "Bullish" },
  { id: "inverted_hammer", label: "Inverted Hammer", bias: "Bullish" },
  { id: "bearish_marubozu", label: "Bearish Marubozu", bias: "Bearish" },
  { id: "shooting_star", label: "Shooting Star", bias: "Bearish" },
];

const DEFAULTS = {
  // Trendlines
  swing_period: 30,
  min_pivot_gap: 10,
  min_right_bars: 3,
  pivot_depth_bars: 5,
  pivot_depth_pct: 2.0,
  trendline_window: 10,
  lookback_candles: 365,
  lookback_days: 550,
  // Patterns
  pattern_window: 10,
  marubozu_delta: 0.005,
  hammer_shadow_ratio: 2.0,
  enforce_trap_filter: false,
  pattern_filter: "bullish_marubozu,hammer",
  // SMA
  fast_period: 6,
  slow_period: 30,
  sma_window: 10,
  // RSI
  rsi_period: 14,
  rsi_signal_ma_period: 9,
  rsi_oversold: 30,
  rsi_overbought: 70,
  rsi_window: 10,
  rsi_rule: "any_bullish",
  // Signal window general
  signal_window: 10,
  // Confluence & Sort
  confluence_mode: "all",
  sort_by: "latest",
};

const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 }));

const API_BASE = (
  (typeof process !== "undefined" && process.env?.BACKEND_URL) ||
  import.meta.env.VITE_API_BASE ||
  ""
).replace(/\/$/, "");

async function api(path, options = {}) {
  const targetUrl = path.startsWith("http") ? path : `${API_BASE}${path}`;
  let response;
  try {
    response = await fetch(targetUrl, options);
  } catch (err) {
    throw new Error("Cannot connect to server. Please ensure the backend server is reachable.");
  }
  const text = await response.text();
  let data = {};
  try { data = JSON.parse(text); } catch {}
  if (!response.ok) {
    if (response.status === 500) {
      if (text.includes("ECONNREFUSED") || !data.detail) {
        throw new Error("Backend API on port 8000 is not reachable yet. Please ensure the Backend window is running.");
      }
    }
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return data;
}

function SliderField({ label, sublabel, min, max, step = 1, value, onChange, unit = "" }) {
  return (
    <div className="slider-field">
      <div className="slider-label-row">
        <div>
          <span className="slider-title">{label}</span>
          {sublabel && <small className="slider-subtitle">{sublabel}</small>}
        </div>
        <input
          type="number"
          className="slider-num-input"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => {
            const val = Number(e.target.value);
            if (!isNaN(val)) onChange(val);
          }}
        />
      </div>
      <div className="slider-track-row">
        <input
          type="range"
          className="slider-range-input"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <span className="slider-unit-text">{value}{unit}</span>
      </div>
    </div>
  );
}

function LineChart({ data, techniques = ["pattern", "trendline", "sma", "rsi"], timeframe, entryPrice, exitPrice }) {
  const candles = data?.candles || [];
  if (!candles.length) return <div className="chart-empty">Choose a row to inspect its signals.</div>;

  const hasTrendline = techniques.includes("trendline");
  const hasPattern = techniques.includes("pattern");
  const hasSma = techniques.includes("sma");
  const hasRsi = techniques.includes("rsi") && Boolean(data.analysis?.rsi_series?.some(Number.isFinite));

  const width = 940;
  const height = hasRsi ? 440 : 340;
  const priceHeight = hasRsi ? 300 : height;
  const pad = { top: 26, right: 24, bottom: 34, left: 62 };

  const smaValues = hasSma
    ? [...(data.analysis?.fast_sma_series || []), ...(data.analysis?.slow_sma_series || [])].filter(Number.isFinite)
    : [];

  const lineValues = [];
  if (hasTrendline && data.analysis?.resistance_line) {
    const rl = data.analysis.resistance_line;
    if (Number.isFinite(rl.start?.price)) lineValues.push(rl.start.price);
    if (Number.isFinite(rl.end?.price)) lineValues.push(rl.end.price);
  }
  if (hasTrendline) {
    (data.analysis?.swing_highs || []).forEach((p) => {
      if (Number.isFinite(p.price)) lineValues.push(p.price);
    });
  }
  if (Number.isFinite(entryPrice) && entryPrice > 0) lineValues.push(entryPrice);
  if (Number.isFinite(exitPrice) && exitPrice > 0) lineValues.push(exitPrice);

  const candlePrices = candles.flatMap((c) => [c.low, c.high]);
  const allPrices = candlePrices.concat(smaValues).concat(lineValues);
  const lo = Math.min(...allPrices);
  const hi = Math.max(...allPrices);
  const span = hi - lo || 1;

  const x = (i) => pad.left + (i / Math.max(1, candles.length - 1)) * (width - pad.left - pad.right);
  const y = (v) => pad.top + ((hi - v) / span) * (priceHeight - pad.top - (hasRsi ? 20 : pad.bottom));
  const absIndex = (idx) => idx - (data.chart_offset || 0);

  // RSI scales
  const rsiTop = priceHeight + 12;
  const rsiBottom = height - pad.bottom;
  const rsiSpan = rsiBottom - rsiTop;
  const yRsi = (v) => rsiTop + ((100 - v) / 100) * rsiSpan;

  function averagePath(series) {
    if (!series?.length) return "";
    const visible = series.slice(data.chart_offset || 0, (data.chart_offset || 0) + candles.length);
    let path = "", drawing = false;
    visible.forEach((value, i) => {
      if (!Number.isFinite(value)) { drawing = false; return; }
      path += `${drawing ? "L" : "M"}${x(i)},${y(value)} `;
      drawing = true;
    });
    return path;
  }

  function rsiPath(series) {
    if (!series?.length) return "";
    const visible = series.slice(data.chart_offset || 0, (data.chart_offset || 0) + candles.length);
    let path = "", drawing = false;
    visible.forEach((value, i) => {
      if (!Number.isFinite(value)) { drawing = false; return; }
      path += `${drawing ? "L" : "M"}${x(i)},${yRsi(value)} `;
      drawing = true;
    });
    return path;
  }

  // Extended trendline in both directions
  const resLine = data.analysis?.resistance_line;
  const trendlinePath = useMemo(() => {
    if (!hasTrendline || !resLine || !resLine.start || !resLine.end) return null;
    const x0 = x(0);
    const y0 = y(resLine.start.price);
    const x1 = x(candles.length - 1);
    const y1 = y(resLine.end.price);
    return `M${x0},${y0} L${x1},${y1}`;
  }, [hasTrendline, resLine, candles.length, hi, lo]);

  const swingHighs = hasTrendline
    ? (data.analysis?.swing_highs || [])
        .filter((p) => absIndex(p.index) >= 0 && absIndex(p.index) < candles.length)
        .map((p, idx) => ({ ...p, i: absIndex(p.index), label: `P${idx + 1}` }))
    : [];

  const annotatedPatterns = hasPattern
    ? (data.analysis?.annotated_patterns || [])
        .filter((p) => absIndex(p.bar_index) >= 0 && absIndex(p.bar_index) < candles.length)
        .map((p) => ({ ...p, i: absIndex(p.bar_index) }))
    : [];

  const labels = [0, Math.floor((candles.length - 1) / 2), candles.length - 1];
  const barWidth = Math.max(1.5, Math.min(14, ((width - pad.left - pad.right) / candles.length) * 0.65));

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${data.symbol} price chart`}>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => {
        const value = hi - f * span;
        return (
          <g key={f}>
            <line className="gridline" x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} />
            <text className="axis-label" x={pad.left - 9} y={y(value) + 4} textAnchor="end">{fmt(value)}</text>
          </g>
        );
      })}

      {/* Candlestick bars: Bullish (Blue, C >= O), Bearish (Red, C < O) */}
      {candles.map((c, i) => {
        const cx = x(i);
        const isUp = c.close >= c.open;
        const topBody = Math.max(c.open, c.close);
        const botBody = Math.min(c.open, c.close);
        const yTop = y(topBody);
        const yBot = y(botBody);
        const bHeight = Math.max(1.2, yBot - yTop);
        const strokeColor = isUp ? "#2563eb" : "#ef4444";
        const fillColor = isUp ? "#2563eb" : "#ef4444";

        return (
          <g key={c.date || i}>
            <line x1={cx} x2={cx} y1={y(c.high)} y2={y(c.low)} stroke={strokeColor} strokeWidth="1" opacity="0.8" />
            <rect
              x={cx - barWidth / 2}
              y={yTop}
              width={barWidth}
              height={bHeight}
              fill={fillColor}
              opacity={isUp ? 0.9 : 0.85}
              rx="0.5"
            />
          </g>
        );
      })}

      {/* SMA Overlays */}
      {hasSma && (
        <>
          <path d={averagePath(data.analysis?.fast_sma_series)} className="sma-fast" />
          <path d={averagePath(data.analysis?.slow_sma_series)} className="sma-slow" />
        </>
      )}

      {/* Trendline Overlays */}
      {hasTrendline && (
        <>
          {trendlinePath && <path d={trendlinePath} className="trend-resistance-extended" />}
          {swingHighs.map((p) => (
            <g key={`h${p.index}`}>
              <circle cx={x(p.i)} cy={y(p.price)} r="4.5" className="pivot-high-body" />
              <text x={x(p.i)} y={y(p.price) - 8} className="pivot-badge-label" textAnchor="middle">{p.label}</text>
            </g>
          ))}
        </>
      )}

      {/* Candlestick Pattern Pins / Badges */}
      {hasPattern &&
        annotatedPatterns.map((p, idx) => {
          const c = candles[p.i];
          if (!c) return null;
          const cx = x(p.i);
          const isBull = p.bias === "bullish";
          const badgeY = isBull
            ? Math.min(height - pad.bottom - 4, y(c.low) + 16 + (idx % 2) * 13)
            : Math.max(pad.top + 10, y(c.high) - 16 - (idx % 2) * 13);
          const shortName =
            p.name === "Bullish Marubozu"
              ? "B-MARU"
              : p.name === "Bearish Marubozu"
              ? "BR-MARU"
              : p.name === "Inverted Hammer"
              ? "INV-HAM"
              : p.name === "Shooting Star"
              ? "STAR"
              : "HAMMER";

          return (
            <g key={`pat-${p.i}-${p.type}-${idx}`}>
              <line
                x1={cx}
                y1={isBull ? y(c.low) : y(c.high)}
                x2={cx}
                y2={badgeY + (isBull ? -6 : 6)}
                stroke={isBull ? "#2563eb" : "#dc2626"}
                strokeWidth="1"
                strokeDasharray="2 2"
                opacity="0.85"
              />
              <rect
                x={cx - 24}
                y={badgeY - 7}
                width={48}
                height={14}
                rx="3"
                className={isBull ? "pattern-box-bullish" : "pattern-box-bearish"}
              />
              <text
                x={cx}
                y={badgeY + 3.5}
                className="pattern-annotation-text"
                fill={isBull ? "#1d4ed8" : "#b91c1c"}
              >
                {shortName}
              </text>
            </g>
          );
        })}

      {/* Watchlist Entry Level Line & Badge */}
      {Number.isFinite(entryPrice) && entryPrice > 0 && (
        <g className="chart-level-entry">
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={y(entryPrice)}
            y2={y(entryPrice)}
            stroke="#059669"
            strokeWidth="1.5"
            strokeDasharray="5 4"
          />
          <rect
            x={width - pad.right - 96}
            y={Math.max(pad.top - 6, Math.min(priceHeight - (hasRsi ? 28 : pad.bottom) - 16, y(entryPrice) - 9))}
            width={92}
            height={18}
            rx="3"
            fill="#059669"
          />
          <text
            x={width - pad.right - 50}
            y={Math.max(pad.top - 6, Math.min(priceHeight - (hasRsi ? 28 : pad.bottom) - 16, y(entryPrice) - 9)) + 12}
            textAnchor="middle"
            fill="#ffffff"
            fontSize="9"
            fontWeight="700"
            fontFamily="'DM Mono', monospace"
          >
            ENTRY ₹{fmt(entryPrice)}
          </text>
        </g>
      )}

      {/* Watchlist Exit Target Level Line & Badge */}
      {Number.isFinite(exitPrice) && exitPrice > 0 && (
        <g className="chart-level-exit">
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={y(exitPrice)}
            y2={y(exitPrice)}
            stroke={exitPrice >= (entryPrice || 0) ? "#2563eb" : "#dc2626"}
            strokeWidth="1.5"
            strokeDasharray="5 4"
          />
          <rect
            x={width - pad.right - 146}
            y={Math.max(pad.top - 6, Math.min(priceHeight - (hasRsi ? 28 : pad.bottom) - 16, y(exitPrice) - 9))}
            width={142}
            height={18}
            rx="3"
            fill={exitPrice >= (entryPrice || 0) ? "#2563eb" : "#dc2626"}
          />
          <text
            x={width - pad.right - 75}
            y={Math.max(pad.top - 6, Math.min(priceHeight - (hasRsi ? 28 : pad.bottom) - 16, y(exitPrice) - 9)) + 12}
            textAnchor="middle"
            fill="#ffffff"
            fontSize="9"
            fontWeight="700"
            fontFamily="'DM Mono', monospace"
          >
            EXIT ₹{fmt(exitPrice)} ({entryPrice ? `${exitPrice >= entryPrice ? '+' : ''}${fmt(((exitPrice - entryPrice) / entryPrice) * 100)}%` : ''})
          </text>
        </g>
      )}

      {/* RSI Sub-Chart Pane */}
      {hasRsi && (
        <g className="chart-rsi-pane">
          {/* Subtle separator */}
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={priceHeight - 6}
            y2={priceHeight - 6}
            stroke="#cbd5e1"
            strokeWidth="1.5"
            strokeDasharray="4 3"
          />

          {/* 30-70 Normal Band Background */}
          <rect
            x={pad.left}
            y={yRsi(70)}
            width={width - pad.left - pad.right}
            height={Math.max(1, yRsi(30) - yRsi(70))}
            fill="rgba(139, 92, 246, 0.05)"
          />

          {/* 70 Overbought Line */}
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={yRsi(70)}
            y2={yRsi(70)}
            stroke="#f43f5e"
            strokeWidth="1"
            strokeDasharray="4 3"
            opacity="0.6"
          />
          <text
            x={pad.left - 9}
            y={yRsi(70) + 3}
            textAnchor="end"
            fill="#f43f5e"
            fontSize="9"
            fontFamily="'DM Mono', monospace"
          >
            70
          </text>

          {/* 50 Midline */}
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={yRsi(50)}
            y2={yRsi(50)}
            stroke="#94a3b8"
            strokeWidth="1"
            strokeDasharray="2 2"
            opacity="0.6"
          />
          <text
            x={pad.left - 9}
            y={yRsi(50) + 3}
            textAnchor="end"
            fill="#94a3b8"
            fontSize="9"
            fontFamily="'DM Mono', monospace"
          >
            50
          </text>

          {/* 30 Oversold Line */}
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={yRsi(30)}
            y2={yRsi(30)}
            stroke="#10b981"
            strokeWidth="1"
            strokeDasharray="4 3"
            opacity="0.6"
          />
          <text
            x={pad.left - 9}
            y={yRsi(30) + 3}
            textAnchor="end"
            fill="#10b981"
            fontSize="9"
            fontFamily="'DM Mono', monospace"
          >
            30
          </text>

          {/* RSI Curve */}
          <path
            d={rsiPath(data.analysis?.rsi_series)}
            fill="none"
            stroke="#8b5cf6"
            strokeWidth="1.8"
          />

          {/* RSI Signal Line */}
          {data.analysis?.rsi_signal_series && (
            <path
              d={rsiPath(data.analysis?.rsi_signal_series)}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="1.3"
              strokeDasharray="3 2"
            />
          )}

          {/* Live RSI Indicator Header Label */}
          <text
            x={pad.left + 8}
            y={rsiTop + 12}
            fill="#7c3aed"
            fontSize="9"
            fontWeight="700"
            fontFamily="'DM Mono', monospace"
          >
            RSI({data.analysis?.rsi != null ? `14: ${fmt(data.analysis.rsi)}` : "14"})
            {data.analysis?.rsi_signal != null ? ` · Sig MA: ${fmt(data.analysis.rsi_signal)}` : ""}
          </text>
        </g>
      )}

      {labels.map((i) => (
        <text key={i} className="axis-label" x={x(i)} y={height - 9} textAnchor={i === 0 ? "start" : i === candles.length - 1 ? "end" : "middle"}>
          {candles[i]?.date}
        </text>
      ))}
    </svg>
  );
}

function SignalBadge({ type, label: customLabel }) {
  const labels = {
    breakout: ["breakout", "Trendline Breakout"],
    breakdown: ["breakdown", "Support breakdown"],
    bullish_cross: ["breakout", "Bullish SMA cross"],
    bearish_cross: ["breakdown", "Bearish SMA cross"],
    bullish_marubozu: ["bullish-pattern", "Bullish Marubozu"],
    bearish_marubozu: ["bearish-pattern", "Bearish Marubozu"],
    hammer: ["bullish-pattern", "Hammer"],
    inverted_hammer: ["bullish-pattern", "Inverted Hammer"],
    shooting_star: ["bearish-pattern", "Shooting Star"],
    rsi_oversold_bounce: ["bullish-rsi", "RSI Oversold Bounce"],
    rsi_overbought_drop: ["bearish-rsi", "RSI Overbought Drop"],
    rsi_bullish_midline: ["bullish-rsi", "RSI Midline Cross"],
    rsi_bearish_midline: ["bearish-rsi", "RSI Midline Drop"],
    rsi_bullish_ma_cross: ["bullish-rsi", "RSI MA Cross"],
    rsi_bearish_ma_cross: ["bearish-rsi", "RSI MA Breakdown"],
  };
  if (!type || !labels[type]) {
    return <span className="badge neutral">{customLabel || "Watching"}</span>;
  }
  const [style, defaultLabel] = labels[type];
  return <span className={`badge ${style}`}>{customLabel || defaultLabel}</span>;
}

function WatchlistModal({ item, onClose, onSave }) {
  const [entry, setEntry] = useState(item?.entryAmount ?? item?.currentPrice ?? 0);
  const [exit, setExit] = useState(
    item?.exitAmount ?? (item?.currentPrice ? Math.round(item.currentPrice * 1.08 * 100) / 100 : 0)
  );
  const [qty, setQty] = useState(item?.quantity || 1);
  const [notes, setNotes] = useState(item?.notes || "");

  const entryNum = parseFloat(entry) || 0;
  const exitNum = parseFloat(exit) || 0;
  const qtyNum = parseInt(qty) || 1;

  const targetPlPct = entryNum > 0 ? ((exitNum - entryNum) / entryNum) * 100 : 0;
  const plPerShare = exitNum - entryNum;
  const totalInvested = entryNum * qtyNum;
  const totalReturn = exitNum * qtyNum;
  const totalPl = totalReturn - totalInvested;

  const currentPrice = item?.currentPrice || entryNum;
  const currentPlPct = entryNum > 0 ? ((currentPrice - entryNum) / entryNum) * 100 : 0;

  function handleSubmit(e) {
    e.preventDefault();
    if (entryNum <= 0 || exitNum <= 0) {
      alert("Please enter valid entry and exit amounts greater than 0.");
      return;
    }
    onSave({
      symbol: item.symbol,
      timeframe: item.timeframe || "1d",
      entryAmount: entryNum,
      exitAmount: exitNum,
      quantity: qtyNum,
      currentPrice: currentPrice,
      targetPlPct: Math.round(targetPlPct * 100) / 100,
      currentPlPct: Math.round(currentPlPct * 100) / 100,
      notes: notes.trim(),
      addedAt: item.addedAt || new Date().toISOString(),
    });
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>⭐ {item.addedAt ? "Edit Watchlist Setup" : "Add Graph to Watchlist"}</h3>
            <p className="modal-subtitle">
              Tracking <strong>{item.symbol}</strong> ({item.timeframe ? item.timeframe.toUpperCase() : "1D"}) · CMP: ₹{fmt(currentPrice)}
            </p>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-grid">
            <label className="modal-field">
              <span>Entry Amount / Price (₹)</span>
              <input
                type="number"
                step="any"
                min="0.01"
                required
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
                placeholder="e.g. 4500"
              />
              <small>Your planned buy / entry level</small>
            </label>

            <label className="modal-field">
              <span>Exit Target Amount (₹)</span>
              <input
                type="number"
                step="any"
                min="0.01"
                required
                value={exit}
                onChange={(e) => setExit(e.target.value)}
                placeholder="e.g. 5100"
              />
              <small>Your planned profit target or exit level</small>
            </label>

            <label className="modal-field">
              <span>Quantity / Shares</span>
              <input
                type="number"
                step="1"
                min="1"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
              <small>For calculating total capital outlay</small>
            </label>

            <label className="modal-field">
              <span>Setup Notes / Trigger Reason</span>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Breakout retest with Hammer pattern"
              />
              <small>Personal note for this trade progress</small>
            </label>
          </div>

          {/* Dynamic P/L Calculation Card */}
          <div className={`modal-pl-preview ${targetPlPct >= 0 ? "profit" : "loss"}`}>
            <div className="pl-preview-row">
              <div>
                <span className="pl-preview-label">Projected Target P/L</span>
                <strong className="pl-preview-pct">
                  {targetPlPct >= 0 ? "+" : ""}{fmt(targetPlPct)}%
                </strong>
              </div>
              <div style={{ textAlign: "right" }}>
                <span className="pl-preview-label">Target Profit / Loss</span>
                <strong className="pl-preview-val">
                  {plPerShare >= 0 ? "+₹" : "-₹"}{fmt(Math.abs(plPerShare))} / share
                </strong>
                <small style={{ display: "block", color: "#64748b", fontSize: "10px" }}>
                  Total: {totalPl >= 0 ? "+₹" : "-₹"}{fmt(Math.abs(totalPl))} ({qtyNum} shares)
                </small>
              </div>
            </div>
            <div className="pl-summary-strip">
              <span>Outlay: ₹{fmt(totalInvested)}</span>
              <span>•</span>
              <span>Target Value: ₹{fmt(totalReturn)}</span>
              <span>•</span>
              <span>Live CMP: ₹{fmt(currentPrice)} ({currentPlPct >= 0 ? "+" : ""}{fmt(currentPlPct)}%)</span>
            </div>
          </div>

          <div className="modal-actions">
            <button type="button" className="button button-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="button scan-button">
              Save Setup to Watchlist
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function WatchlistDesk({
  watchlist,
  onEditItem,
  onRemoveItem,
  onAddNewManual,
  onBackToScanner,
  api,
  fmt,
  techniques,
  params,
}) {
  const [selectedSymbol, setSelectedSymbol] = useState(watchlist[0]?.symbol || "");
  const [chartData, setChartData] = useState(null);
  const [loadingChart, setLoadingChart] = useState(false);
  const [chartError, setChartError] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("added");

  // Inline quick adjustment inputs for the right-hand chart
  const [quickEntry, setQuickEntry] = useState("");
  const [quickExit, setQuickExit] = useState("");
  const [savedSuccess, setSavedSuccess] = useState(false);

  const selectedItem = useMemo(() => {
    return watchlist.find((item) => item.symbol === selectedSymbol) || watchlist[0] || null;
  }, [watchlist, selectedSymbol]);

  useEffect(() => {
    if (selectedItem) {
      setQuickEntry(selectedItem.entryAmount);
      setQuickExit(selectedItem.exitAmount);
      loadChart(selectedItem);
    } else {
      setChartData(null);
    }
  }, [selectedItem?.symbol, selectedItem?.timeframe]);

  async function loadChart(item) {
    if (!item) return;
    setLoadingChart(true);
    setChartError("");
    try {
      const tf = item.timeframe || "1d";
      const query = new URLSearchParams({
        ...params,
        strategy: "confluence",
        techniques: techniques.join(","),
        confluence_mode: "any",
        timeframe: tf,
      });
      const res = await api(`/api/chart/${encodeURIComponent(item.symbol)}?${query}`);
      setChartData(res);
      // Update live CMP if different
      if (res.analysis?.close && Math.abs(res.analysis.close - (item.currentPrice || 0)) > 0.05) {
        const newClose = res.analysis.close;
        const newCurPl = item.entryAmount > 0 ? Math.round(((newClose - item.entryAmount) / item.entryAmount) * 10000) / 100 : 0;
        onEditItem({
          ...item,
          currentPrice: newClose,
          currentPlPct: newCurPl,
        }, false);
      }
    } catch (err) {
      setChartError(err.message);
    } finally {
      setLoadingChart(false);
    }
  }

  function handleSaveQuickLevels() {
    const e = parseFloat(quickEntry);
    const x = parseFloat(quickExit);
    if (!e || !x || e <= 0 || x <= 0) return;
    const targetPl = Math.round(((x - e) / e) * 10000) / 100;
    const curPrice = selectedItem.currentPrice || e;
    const curPl = e > 0 ? Math.round(((curPrice - e) / e) * 10000) / 100 : 0;
    onEditItem({
      ...selectedItem,
      entryAmount: e,
      exitAmount: x,
      targetPlPct: targetPl,
      currentPlPct: curPl,
    });
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2200);
  }

  const displayItems = useMemo(() => {
    let list = [...watchlist];
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((item) => item.symbol.toLowerCase().includes(q) || (item.notes || "").toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      if (sortBy === "targetPl") return (b.targetPlPct || 0) - (a.targetPlPct || 0);
      if (sortBy === "currentPl") return (b.currentPlPct || 0) - (a.currentPlPct || 0);
      if (sortBy === "symbol") return a.symbol.localeCompare(b.symbol);
      return new Date(b.addedAt || 0) - new Date(a.addedAt || 0);
    });
    return list;
  }, [watchlist, search, sortBy]);

  const totalTracked = watchlist.length;
  const avgTargetPl = totalTracked > 0 ? watchlist.reduce((acc, i) => acc + (i.targetPlPct || 0), 0) / totalTracked : 0;
  const avgCurrentPl = totalTracked > 0 ? watchlist.reduce((acc, i) => acc + (i.currentPlPct || 0), 0) / totalTracked : 0;
  const inProfitCount = watchlist.filter((i) => (i.currentPlPct || 0) > 0).length;

  return (
    <div className="watchlist-page-container">
      {/* Page Header */}
      <section className="intro-row">
        <div>
          <p className="eyebrow">SAVED SETUPS & PROGRESS DESK</p>
          <h1>Tracked Watchlist.<br /><em>Monitor Entry, Exit & P/L.</em></h1>
          <p className="intro-copy">
            Every graph you save is tracked with your custom entry amount and exit target. The live profit/loss % updates with current market prices, with levels drawn directly onto the candlestick charts.
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button type="button" className="button button-secondary" onClick={onAddNewManual}>
            + Add Stock Manually
          </button>
          <button type="button" className="button scan-button" onClick={onBackToScanner}>
            🔍 Back to Strategy Scanner →
          </button>
        </div>
      </section>

      {/* Summary Metrics */}
      <div className="metric-row" style={{ marginTop: "16px" }}>
        <div className="metric-card">
          <span>Tracked Setups</span>
          <strong>{totalTracked}</strong>
          <small>{inProfitCount} currently in profit</small>
        </div>
        <div className="metric-card green">
          <span>Average Target P/L</span>
          <strong>{avgTargetPl >= 0 ? "+" : ""}{fmt(avgTargetPl)}%</strong>
          <small>Planned target gain across all setups</small>
        </div>
        <div className={`metric-card ${avgCurrentPl >= 0 ? "green" : "red"}`}>
          <span>Average Current P/L</span>
          <strong>{avgCurrentPl >= 0 ? "+" : ""}{fmt(avgCurrentPl)}%</strong>
          <small>Live unrealized return based on latest close</small>
        </div>
        <div className="metric-card">
          <span>Tracked Capital Outlay</span>
          <strong>₹{fmt(watchlist.reduce((sum, i) => sum + (i.entryAmount * (i.quantity || 1)), 0))}</strong>
          <small>Projected return: ₹{fmt(watchlist.reduce((sum, i) => sum + (i.exitAmount * (i.quantity || 1)), 0))}</small>
        </div>
      </div>

      {watchlist.length === 0 ? (
        <div className="empty-watchlist-card">
          <div className="empty-icon">⭐</div>
          <h3>Your Tracked Watchlist is Empty</h3>
          <p>
            You haven't added any charts to your watchlist yet. Run scans on the Strategy Scanner, view any graph you like, and click <strong>"⭐ Add to Watchlist"</strong> to set your Entry and Exit targets and track your progress here!
          </p>
          <div style={{ display: "flex", gap: "10px", justifyContent: "center", marginTop: "14px" }}>
            <button type="button" className="button scan-button" onClick={onBackToScanner}>
              🔍 Go to Strategy Scanner →
            </button>
            <button type="button" className="button button-secondary" onClick={onAddNewManual}>
              + Add First Stock Manually
            </button>
          </div>
        </div>
      ) : (
        <div className="watchlist-desk-grid">
          {/* Left Column: Progress Tracking Table */}
          <div className="table-card">
            <div className="table-top">
              <div>
                <strong>Tracked Positions & Progress Table</strong>
                <small>Select any position to inspect its graph with live Entry & Exit overlays</small>
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <input
                  type="text"
                  className="search-input"
                  placeholder="Filter symbols or notes..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <select
                  className="sort-select"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  <option value="added">Recently Added</option>
                  <option value="targetPl">Highest Target P/L %</option>
                  <option value="currentPl">Highest Current P/L %</option>
                  <option value="symbol">Symbol A → Z</option>
                </select>
              </div>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Entry Amount</th>
                    <th>Exit Target</th>
                    <th>Target P/L %</th>
                    <th>Live Close</th>
                    <th>Current P/L %</th>
                    <th>Notes / Setup</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {displayItems.map((item) => {
                    const isSelected = selectedItem?.symbol === item.symbol;
                    const isTargetProfitable = (item.targetPlPct || 0) >= 0;
                    const isCurrentProfitable = (item.currentPlPct || 0) >= 0;
                    return (
                      <tr
                        key={item.symbol}
                        className={isSelected ? "selected" : ""}
                        onClick={() => setSelectedSymbol(item.symbol)}
                      >
                        <td>
                          <strong>{item.symbol}</strong>
                          <small style={{ color: "#0284c7", fontWeight: 600 }}>
                            {item.timeframe ? item.timeframe.toUpperCase() : "1D"}
                          </small>
                        </td>
                        <td>
                          <b style={{ color: "#059669", fontFamily: "'DM Mono', monospace" }}>
                            ₹{fmt(item.entryAmount)}
                          </b>
                          {item.quantity > 1 && (
                            <small style={{ display: "block", color: "#64748b" }}>
                              x{item.quantity} (₹{fmt(item.entryAmount * item.quantity)})
                            </small>
                          )}
                        </td>
                        <td>
                          <b style={{ color: isTargetProfitable ? "#2563eb" : "#dc2626", fontFamily: "'DM Mono', monospace" }}>
                            ₹{fmt(item.exitAmount)}
                          </b>
                          {item.quantity > 1 && (
                            <small style={{ display: "block", color: "#64748b" }}>
                              x{item.quantity} (₹{fmt(item.exitAmount * item.quantity)})
                            </small>
                          )}
                        </td>
                        <td>
                          <span className={`pl-badge ${isTargetProfitable ? "positive" : "negative"}`}>
                            {isTargetProfitable ? "+" : ""}{fmt(item.targetPlPct)}%
                          </span>
                        </td>
                        <td>
                          <span style={{ fontFamily: "'DM Mono', monospace" }}>
                            ₹{fmt(item.currentPrice)}
                          </span>
                        </td>
                        <td>
                          <span className={`pl-badge ${isCurrentProfitable ? "positive" : "negative"}`}>
                            {isCurrentProfitable ? "+" : ""}{fmt(item.currentPlPct)}%
                          </span>
                        </td>
                        <td>
                          <span style={{ fontSize: "10px", color: "#475569" }}>
                            {item.notes || "—"}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: "6px" }}>
                            <button
                              type="button"
                              className="action-btn-small edit"
                              onClick={(e) => {
                                e.stopPropagation();
                                onEditItem(item);
                              }}
                              title="Edit Entry/Exit amounts"
                            >
                              ✎ Edit
                            </button>
                            <button
                              type="button"
                              className="action-btn-small remove"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (confirm(`Remove ${item.symbol} from watchlist?`)) {
                                  onRemoveItem(item.symbol);
                                }
                              }}
                              title="Remove from watchlist"
                            >
                              ✕
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Right Column: Chart Review with Levels */}
          <div className="chart-card">
            <div className="chart-heading">
              <div>
                <span className="step">⭐</span>
                <div>
                  <strong>{selectedItem ? selectedItem.symbol : "Saved Graph"}</strong>
                  <small>
                    {selectedItem
                      ? `Tracked Setup · Entry: ₹${fmt(selectedItem.entryAmount)} · Target: ₹${fmt(selectedItem.exitAmount)}`
                      : "Select a stock from the progress table to view its graph"}
                  </small>
                </div>
              </div>
              {selectedItem && (
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <button
                    type="button"
                    className="button-secondary"
                    style={{ padding: "4px 8px", fontSize: "10px", borderRadius: "4px" }}
                    onClick={() => onEditItem(selectedItem)}
                  >
                    ✎ Edit Position
                  </button>
                  <span className="chart-interval">
                    {(selectedItem.timeframe || "1d").toUpperCase()} CANDLES
                  </span>
                </div>
              )}
            </div>

            {loadingChart && (
              <div className="chart-loading-overlay">
                <span className="spinner" /> Loading graph for {selectedItem?.symbol}…
              </div>
            )}

            {chartError && (
              <div className="chart-error-banner">
                {chartError}
              </div>
            )}

            {chartData && selectedItem ? (
              <>
                <LineChart
                  data={chartData}
                  techniques={techniques}
                  timeframe={selectedItem.timeframe || "1d"}
                  entryPrice={selectedItem.entryAmount}
                  exitPrice={selectedItem.exitAmount}
                />
                <div className="legend">
                  <span><i className="legend-candle-blue" />Bullish</span>
                  <span><i className="legend-candle-down" />Bearish</span>
                  <span><i className="legend-entry-line" />Entry Level</span>
                  <span><i className="legend-exit-line" />Exit Target</span>
                  {techniques.includes("trendline") && <span><i className="legend-trendline-ext" />Trendline</span>}
                  {techniques.includes("sma") && <span><i className="legend-fast" />SMA</span>}
                  {techniques.includes("rsi") && <span><i className="legend-rsi" />RSI (14)</span>}
                </div>

                {/* Progress & Level Values Row */}
                <div className="line-values">
                  <div>
                    <small>Entry Level</small>
                    <b style={{ color: "#059669" }}>₹{fmt(selectedItem.entryAmount)}</b>
                  </div>
                  <div>
                    <small>Exit Target</small>
                    <b style={{ color: "#2563eb" }}>₹{fmt(selectedItem.exitAmount)}</b>
                  </div>
                  <div>
                    <small>Target P/L</small>
                    <b style={{ color: selectedItem.targetPlPct >= 0 ? "#059669" : "#dc2626" }}>
                      {selectedItem.targetPlPct >= 0 ? "+" : ""}{fmt(selectedItem.targetPlPct)}%
                    </b>
                  </div>
                  <div>
                    <small>Live CMP</small>
                    <b>₹{fmt(selectedItem.currentPrice || chartData.analysis?.close)}</b>
                  </div>
                  <div>
                    <small>Current P/L</small>
                    <b style={{ color: selectedItem.currentPlPct >= 0 ? "#059669" : "#dc2626" }}>
                      {selectedItem.currentPlPct >= 0 ? "+" : ""}{fmt(selectedItem.currentPlPct)}%
                    </b>
                  </div>
                  {techniques.includes("rsi") && chartData?.analysis?.rsi != null && (
                    <div>
                      <small>RSI (14)</small>
                      <b style={{ color: (chartData.analysis.rsi || 0) >= 50 ? "#059669" : "#dc2626" }}>
                        {fmt(chartData.analysis.rsi)}
                      </b>
                    </div>
                  )}
                </div>

                {/* Inline Quick Level Adjuster */}
                <div className="quick-level-adjuster">
                  <div className="quick-adjuster-header">
                    <strong>Quick Adjust Levels for {selectedItem.symbol}</strong>
                    {savedSuccess && <span className="save-success-tag">✓ Updated Graph & Table!</span>}
                  </div>
                  <div className="quick-adjuster-inputs">
                    <label>
                      <span>Entry Amount:</span>
                      <input
                        type="number"
                        step="any"
                        value={quickEntry}
                        onChange={(e) => setQuickEntry(e.target.value)}
                      />
                    </label>
                    <label>
                      <span>Exit Target:</span>
                      <input
                        type="number"
                        step="any"
                        value={quickExit}
                        onChange={(e) => setQuickExit(e.target.value)}
                      />
                    </label>
                    <div className="quick-preview">
                      <span>Target P/L:</span>
                      <strong className={((parseFloat(quickExit) - parseFloat(quickEntry)) >= 0) ? "text-green" : "text-red"}>
                        {parseFloat(quickEntry) > 0 ? `${fmt(((parseFloat(quickExit) - parseFloat(quickEntry)) / parseFloat(quickEntry)) * 100)}%` : "—"}
                      </strong>
                    </div>
                    <button
                      type="button"
                      className="button scan-button"
                      style={{ padding: "6px 14px", fontSize: "11px" }}
                      onClick={handleSaveQuickLevels}
                    >
                      Update Levels
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="chart-placeholder">
                <div className="chart-scribble">⭐╱╲⭐</div>
                <span>SELECT A POSITION FROM THE TABLE TO REVIEW ITS GRAPH AND TRACK PROGRESS</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [activePage, setActivePage] = useState("scanner"); // "scanner" | "watchlist"
  const [watchlist, setWatchlist] = useState(() => {
    try {
      const s = localStorage.getItem("signal_workshop_watchlist");
      return s ? JSON.parse(s) : [];
    } catch {
      return [];
    }
  });
  const [watchlistModal, setWatchlistModal] = useState(null);
  const [toastMsg, setToastMsg] = useState("");

  const [status, setStatus] = useState(null);
  const [timeframe, setTimeframe] = useState("1d");
  const [params, setParams] = useState(DEFAULTS);
  const [techniques, setTechniques] = useState(["pattern", "trendline", "sma", "rsi"]);
  const [confluenceMode, setConfluenceMode] = useState("all");
  const [sortBy, setSortBy] = useState("latest");
  const [source, setSource] = useState("yahoo");
  const [customSymbols, setCustomSymbols] = useState("");
  const [manualSymbols, setManualSymbols] = useState([]);
  const [result, setResult] = useState(null);
  const [chart, setChart] = useState(null);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("signals");

  function showToast(msg) {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(""), 3000);
  }

  function handleSaveWatchlistItem(item, showFeedback = true) {
    setWatchlist((prev) => {
      const idx = prev.findIndex((i) => i.symbol === item.symbol);
      let updated;
      if (idx >= 0) {
        updated = [...prev];
        updated[idx] = item;
      } else {
        updated = [item, ...prev];
      }
      try {
        localStorage.setItem("signal_workshop_watchlist", JSON.stringify(updated));
      } catch {}
      return updated;
    });
    setWatchlistModal(null);
    if (showFeedback) {
      showToast(`⭐ Saved ${item.symbol} (${item.targetPlPct >= 0 ? "+" : ""}${fmt(item.targetPlPct)}% Target P/L)`);
    }
  }

  function handleRemoveWatchlistItem(sym) {
    setWatchlist((prev) => {
      const updated = prev.filter((i) => i.symbol !== sym);
      try {
        localStorage.setItem("signal_workshop_watchlist", JSON.stringify(updated));
      } catch {}
      return updated;
    });
    showToast(`Removed ${sym} from Watchlist`);
  }

  function openWatchlistModal(sym, tf = timeframe, currentPrice = null, existing = null) {
    if (existing) {
      setWatchlistModal(existing);
    } else {
      const found = watchlist.find((i) => i.symbol === sym);
      if (found) {
        setWatchlistModal(found);
      } else {
        const cPrice = currentPrice || (chart?.analysis?.close ?? 100);
        setWatchlistModal({
          symbol: sym,
          timeframe: tf,
          currentPrice: cPrice,
          entryAmount: cPrice,
          exitAmount: Math.round(cPrice * 1.08 * 100) / 100,
          quantity: 1,
          notes: "",
        });
      }
    }
  }

  function handleAddManualStock() {
    const sym = prompt("Enter Stock Ticker Symbol to add (e.g. RELIANCE, TCS, INFY):");
    if (!sym || !sym.trim()) return;
    const cleanSym = sym.trim().toUpperCase().replace(/[^A-Z0-9&._-]/g, "");
    openWatchlistModal(cleanSym, timeframe, 1000);
  }

  const tfConfig = TIMEFRAME_CONFIGS[timeframe] || TIMEFRAME_CONFIGS["1d"];

  function handleTimeframeChange(newTf) {
    setTimeframe(newTf);
    const cfg = TIMEFRAME_CONFIGS[newTf];
    setParams((prev) => ({
      ...prev,
      lookback_candles: cfg.defaultLookback,
      swing_period: cfg.defaultPeriod,
      min_pivot_gap: cfg.defaultGap,
      min_right_bars: cfg.defaultRightBars || 3,
    }));
  }

  function toggleTechnique(tech) {
    setTechniques((prev) => {
      if (prev.includes(tech)) {
        if (prev.length === 1) return prev; // Keep at least one technique
        return prev.filter((t) => t !== tech);
      } else {
        return [...prev, tech];
      }
    });
  }

  function applyPreset(list, mode = "all") {
    setTechniques(list);
    setConfluenceMode(mode);
  }

  function togglePattern(id) {
    const current = (params.pattern_filter || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    let updated;
    if (current.includes("all")) {
      updated = [id];
    } else if (current.includes(id)) {
      if (current.length === 1) return; // Keep at least one pattern
      updated = current.filter((p) => p !== id);
    } else {
      updated = [...current, id];
    }
    setParams((prev) => ({ ...prev, pattern_filter: updated.join(",") }));
  }

  function setPatternPreset(presetStr) {
    setParams((prev) => ({ ...prev, pattern_filter: presetStr }));
  }

  const refreshStatus = useCallback(async (retriesLeft = 4) => {
    try {
      const next = await api("/api/status");
      setStatus(next);
      setManualSymbols(next.manual_symbols || []);
      setError("");
    } catch (e) {
      if (retriesLeft > 0) {
        setTimeout(() => refreshStatus(retriesLeft - 1), 1500);
      } else {
        setError(e.message);
      }
    }
  }, []);

  useEffect(() => { refreshStatus(); }, [refreshStatus]);

  async function uploadCsv(event) {
    const files = [...(event.target.files || [])];
    event.target.value = "";
    if (!files.length) return;
    setUploading(true); setError("");
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    try {
      const response = await api("/api/data/upload", { method: "POST", body: form });
      setManualSymbols(response.symbols || []);
      setSource("csv");
    } catch (e) { setError(e.message); }
    finally { setUploading(false); }
  }

  async function clearCsv() {
    setError("");
    try {
      const response = await api("/api/data/upload", { method: "DELETE" });
      setManualSymbols(response.symbols || []);
      setResult(null);
      setChart(null);
    } catch (e) { setError(e.message); }
  }

  async function scan() {
    setBusy(true); setError(""); setResult(null); setChart(null); setSelected("");
    const query = new URLSearchParams({
      ...params,
      strategy: "confluence",
      techniques: techniques.join(","),
      confluence_mode: confluenceMode,
      sort_by: sortBy,
      source,
      timeframe,
    });
    if (customSymbols.trim()) query.set("symbols", customSymbols.trim());
    try {
      const res = await api(`/api/scan?${query}`);
      setResult(res);
      // Strictly remain on the signals desk - do not auto-switch to watching
      setTab("signals");
      if (res.signals && res.signals.length > 0) {
        openChart(res.signals[0].symbol, timeframe);
      } else {
        setSelected("");
        setChart(null);
      }
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function openChart(symbol, currentTf = timeframe) {
    setSelected(symbol); setChart(null); setError("");
    const query = new URLSearchParams({
      ...params,
      strategy: "confluence",
      techniques: techniques.join(","),
      confluence_mode: confluenceMode,
      source,
      timeframe: currentTf,
    });
    try {
      setChart(await api(`/api/chart/${encodeURIComponent(symbol)}?${query}`));
    } catch (e) { setError(e.message); }
  }

  // Client-side instant sort for smooth UI interaction
  const sortedCurrentRows = useMemo(() => {
    const raw = tab === "signals" ? result?.signals || [] : result?.watching || [];
    const copy = [...raw];
    copy.sort((a, b) => {
      const aBars = a.latest_signal?.bars_ago ?? 999;
      const bBars = b.latest_signal?.bars_ago ?? 999;
      if (sortBy === "oldest") {
        return bBars - aBars; // Higher bars ago first
      } else if (sortBy === "confluence") {
        const diff = (b.matched_count || 0) - (a.matched_count || 0);
        return diff !== 0 ? diff : aBars - bBars;
      } else if (sortBy === "symbol") {
        return a.symbol.localeCompare(b.symbol);
      } else {
        // "latest" default
        return aBars - bBars; // 0 bars ago (latest) first
      }
    });
    return copy;
  }, [result, tab, sortBy]);

  const canScan = !busy && !uploading && (source === "yahoo" || manualSymbols.length > 0);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">S</div>
          <div>
            <strong>Signal Workshop</strong>
            <small>Multi-Factor Confluence Scanner · Intraday 5M/15M/1H · Tracked Watchlist</small>
          </div>
        </div>

        {/* Primary Page Navigation */}
        <nav className="main-nav">
          <button
            type="button"
            className={`nav-btn ${activePage === "scanner" ? "active" : ""}`}
            onClick={() => setActivePage("scanner")}
          >
            <span className="nav-icon">🔍</span>
            <span>Strategy Scanner</span>
          </button>
          <button
            type="button"
            className={`nav-btn ${activePage === "watchlist" ? "active" : ""}`}
            onClick={() => setActivePage("watchlist")}
          >
            <span className="nav-icon">⭐</span>
            <span>Tracked Watchlist</span>
            {watchlist.length > 0 && <span className="nav-count-badge">{watchlist.length}</span>}
          </button>
        </nav>

        <div className="account-area">
          <span className="free-chip"><i />Free Data · No API Key</span>
        </div>
      </header>

      {toastMsg && <div className="toast-notification">{toastMsg}</div>}

      {watchlistModal && (
        <WatchlistModal
          item={watchlistModal}
          onClose={() => setWatchlistModal(null)}
          onSave={handleSaveWatchlistItem}
        />
      )}

      {activePage === "watchlist" ? (
        <WatchlistDesk
          watchlist={watchlist}
          onEditItem={(item) => openWatchlistModal(item.symbol, item.timeframe, item.currentPrice, item)}
          onRemoveItem={handleRemoveWatchlistItem}
          onAddNewManual={handleAddManualStock}
          onBackToScanner={() => setActivePage("scanner")}
          api={api}
          fmt={fmt}
          techniques={techniques}
          params={params}
        />
      ) : (
        <>
          <section className="intro-row">
        <div>
          <p className="eyebrow">MULTI-FACTOR TECHNICAL CONFLUENCE ENGINE</p>
          <h1>Keep the classic.<br /><em>Build your own.</em></h1>
          <p className="intro-copy">
            Mix and match Candlestick Patterns, Body-Tip Swing Trendlines, and SMA Crossovers. Scan across Intraday (5m, 15m, 1h), Daily, Weekly, and Monthly charts with dual sliders and numeric inputs.
          </p>
        </div>
        <div className="intro-meta">
          <span className="pulse" />Intraday 5M/15M/1H <span className="meta-divider">/</span> Multi-Strategy Confluence <span className="meta-divider">/</span> Dual Sliders
        </div>
      </section>

      {error && <div className="error-banner"><span>!</span>{error}<button onClick={() => setError("")}>×</button></div>}

      <section className="control-card">
        <div className="card-heading">
          <div><span className="step">01</span><h2>1. Select Active Techniques & Timeframe</h2></div>
          <span className="connection is-on"><i />Ready to scan</span>
        </div>

        {/* Quick Presets */}
        <div className="preset-pills">
          <span style={{ fontSize: "10px", fontWeight: 600, color: "#5a6d62", marginRight: "4px" }}>Quick Presets:</span>
          <button
            className={`preset-pill ${techniques.length === 4 && confluenceMode === "all" ? "active" : ""}`}
            onClick={() => applyPreset(["pattern", "trendline", "sma", "rsi"], "all")}
          >
            ★ All 4 (Strict Confluence)
          </button>
          <button
            className={`preset-pill ${techniques.length === 2 && techniques.includes("sma") && techniques.includes("rsi") && !techniques.includes("pattern") && !techniques.includes("trendline") ? "active" : ""}`}
            onClick={() => applyPreset(["sma", "rsi"], confluenceMode)}
          >
            ⚡ SMA + RSI
          </button>
          <button
            className={`preset-pill ${techniques.length === 2 && techniques.includes("pattern") && techniques.includes("sma") && !techniques.includes("trendline") && !techniques.includes("rsi") ? "active" : ""}`}
            onClick={() => applyPreset(["pattern", "sma"], confluenceMode)}
          >
            Pattern + SMA
          </button>
          <button
            className={`preset-pill ${techniques.length === 2 && techniques.includes("trendline") && techniques.includes("sma") && !techniques.includes("pattern") && !techniques.includes("rsi") ? "active" : ""}`}
            onClick={() => applyPreset(["trendline", "sma"], confluenceMode)}
          >
            Trendline + SMA
          </button>
          <button
            className={`preset-pill ${techniques.length === 1 && techniques.includes("rsi") ? "active" : ""}`}
            onClick={() => applyPreset(["rsi"], "any")}
          >
            Only RSI
          </button>
          <button
            className={`preset-pill ${techniques.length === 1 && techniques.includes("pattern") ? "active" : ""}`}
            onClick={() => applyPreset(["pattern"], "any")}
          >
            Only Patterns
          </button>
          <button
            className={`preset-pill ${techniques.length === 1 && techniques.includes("trendline") ? "active" : ""}`}
            onClick={() => applyPreset(["trendline"], "any")}
          >
            Only Trendlines
          </button>
          <button
            className={`preset-pill ${techniques.length === 1 && techniques.includes("sma") ? "active" : ""}`}
            onClick={() => applyPreset(["sma"], "any")}
          >
            Only SMA
          </button>
        </div>

        {/* Interactive Technique Mixer Cards */}
        <div className="technique-mixer-bar">
          <div
            className={`technique-card ${techniques.includes("pattern") ? "selected" : ""}`}
            onClick={() => toggleTechnique("pattern")}
          >
            <div className="technique-header">
              <b>01. Candlestick Patterns</b>
              <span className="technique-badge">{techniques.includes("pattern") ? "ACTIVE" : "OFF"}</span>
            </div>
            <small>Marubozu · Hammer · Shooting Star · Trap Rule Filter (1%–10%)</small>
          </div>

          <div
            className={`technique-card ${techniques.includes("trendline") ? "selected" : ""}`}
            onClick={() => toggleTechnique("trendline")}
          >
            <div className="technique-header">
              <b>02. Swing Trendlines</b>
              <span className="technique-badge">{techniques.includes("trendline") ? "ACTIVE" : "OFF"}</span>
            </div>
            <small>Confirmed Body-Tip Pivots · Nearest to Date · Extended Line Breakout</small>
          </div>

          <div
            className={`technique-card ${techniques.includes("sma") ? "selected" : ""}`}
            onClick={() => toggleTechnique("sma")}
          >
            <div className="technique-header">
              <b>03. SMA Crossover</b>
              <span className="technique-badge">{techniques.includes("sma") ? "ACTIVE" : "OFF"}</span>
            </div>
            <small>Fast vs Slow Simple Moving Average completed crossover</small>
          </div>

          <div
            className={`technique-card ${techniques.includes("rsi") ? "selected" : ""}`}
            onClick={() => toggleTechnique("rsi")}
          >
            <div className="technique-header">
              <b>04. RSI Momentum</b>
              <span className="technique-badge">{techniques.includes("rsi") ? "ACTIVE" : "OFF"}</span>
            </div>
            <small>Wilder's RSI(14) · Oversold Bounce (30) · Midline 50 Cross · Signal MA</small>
          </div>
        </div>

        {/* Confluence Mode & Timeframe Bar */}
        <div className="confluence-mode-row">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span className="confluence-mode-label">Confluence Matching Rule:</span>
            <div className="confluence-mode-buttons">
              <button
                className={confluenceMode === "all" ? "active" : ""}
                onClick={() => setConfluenceMode("all")}
              >
                ● Strict Confluence (Match ALL Active)
              </button>
              <button
                className={confluenceMode === "any" ? "active" : ""}
                onClick={() => setConfluenceMode("any")}
              >
                ○ Match ANY Active Technique
              </button>
            </div>
          </div>
          <span style={{ fontSize: "10px", color: "#64748b" }}>
            {confluenceMode === "all"
              ? `Stock must trigger all ${techniques.length} selected technique(s)`
              : `Stock triggers if any of the ${techniques.length} selected technique(s) match`}
          </span>
        </div>

        {/* Multi-Timeframe Selector with Intraday (5m, 15m, 1h) */}
        <div className="timeframe-row">
          <span className="control-label">Chart Timeframe:</span>
          <div className="timeframe-switch">
            <button className={timeframe === "5m" ? "active" : ""} onClick={() => handleTimeframeChange("5m")}>
              <b>5m</b> 5 Min
            </button>
            <button className={timeframe === "15m" ? "active" : ""} onClick={() => handleTimeframeChange("15m")}>
              <b>15m</b> 15 Min
            </button>
            <button className={timeframe === "1h" ? "active" : ""} onClick={() => handleTimeframeChange("1h")}>
              <b>1H</b> 1 Hour
            </button>
            <button className={timeframe === "1d" ? "active" : ""} onClick={() => handleTimeframeChange("1d")}>
              <b>1D</b> Daily
            </button>
            <button className={timeframe === "1w" ? "active" : ""} onClick={() => handleTimeframeChange("1w")}>
              <b>1W</b> Weekly
            </button>
            <button className={timeframe === "1mo" ? "active" : ""} onClick={() => handleTimeframeChange("1mo")}>
              <b>1M</b> Monthly
            </button>
          </div>
          <span className="timeframe-hint">{tfConfig.hint}</span>
        </div>

        {/* Data Source Selection */}
        <div className="source-row">
          <div className="source-choice">
            <span className="control-label">Data source</span>
            <button className={source === "yahoo" ? "selected" : ""} onClick={() => setSource("yahoo")}>
              Yahoo Finance <small>free · no key</small>
            </button>
            <button className={source === "csv" ? "selected" : ""} onClick={() => setSource("csv")}>
              My CSV <small>local file</small>
            </button>
          </div>
          {source === "csv" ? (
            <div className="csv-control">
              <label className="button upload-button">
                {uploading ? "Reading CSV…" : "Choose candle CSV"}
                <input type="file" accept=".csv,text/csv" multiple onChange={uploadCsv} disabled={uploading} />
              </label>
              {manualSymbols.length > 0 ? (
                <span className="csv-summary">
                  {manualSymbols.length} symbols loaded: {manualSymbols.slice(0, 5).join(", ")}{manualSymbols.length > 5 ? " …" : ""}{" "}
                  <button onClick={clearCsv}>Clear</button>
                </span>
              ) : (
                <span className="csv-summary muted">Date/Timestamp, Open, High, Low, Close.</span>
              )}
            </div>
          ) : (
            <div className="data-note">Free history via yfinance <span>Personal research use</span></div>
          )}
        </div>

        {/* Dynamic Sliders and Settings Grid */}
        <div style={{ marginTop: "16px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 2fr", gap: "16px" }}>
            {/* Universe column */}
            <label className="field field-universe">
              <span>Universe <small>{source === "yahoo" ? "Nifty 100 by default, or override" : "Uploaded symbols"}</small></span>
              <div className="universe-pill">
                <span className="universe-icon">{source === "yahoo" ? "100" : "CSV"}</span>
                <b>{source === "yahoo" ? "Nifty 100" : "Uploaded candles"}</b>
                <small>{source === "yahoo" ? "Current NSE Indices" : `${manualSymbols.length} symbols`}</small>
              </div>
              <span className="or-label">or enter symbols</span>
              <textarea
                value={customSymbols}
                onChange={(e) => setCustomSymbols(e.target.value)}
                placeholder="TITAN, ICICIBANK, AXISBANK, INFY, RELIANCE, TCS"
                rows="3"
              />
            </label>

            {/* General lookback slider */}
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <SliderField
                label="Total Lookback Candles"
                sublabel={`History window for ${timeframe.toUpperCase()} chart`}
                min={tfConfig.minLookback}
                max={tfConfig.maxLookback}
                step={5}
                value={params.lookback_candles}
                onChange={(val) => setParams({ ...params, lookback_candles: val })}
                unit=" bars"
              />
            </div>
          </div>

          {/* Technique 01: Candlestick Pattern Sliders */}
          {techniques.includes("pattern") && (
            <div style={{ marginTop: "16px", padding: "14px", background: "#f8faf9", borderRadius: "10px", border: "1px solid #e1e9e3" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
                <strong style={{ fontSize: "12px", color: "#164638" }}>01. Candlestick Pattern Settings</strong>
                <label className="checkbox-label" style={{ margin: 0 }}>
                  <input
                    type="checkbox"
                    checked={params.enforce_trap_filter}
                    onChange={(e) => setParams({ ...params, enforce_trap_filter: e.target.checked })}
                  />
                  <span>Enforce Trade Trap Rule (0.01 ≤ Range/Open ≤ 0.10)</span>
                </label>
              </div>
              <div className="controls-grid" style={{ padding: "0 0 6px" }}>
                <SliderField
                  label="Pattern Scan Window"
                  sublabel="Look for patterns in last N bars"
                  min={1}
                  max={50}
                  value={params.pattern_window}
                  onChange={(val) => setParams({ ...params, pattern_window: val })}
                  unit=" bars"
                />
                <SliderField
                  label="Marubozu Shadow Delta (δ)"
                  sublabel="Max upper/lower shadow ratio"
                  min={0.001}
                  max={0.020}
                  step={0.001}
                  value={params.marubozu_delta}
                  onChange={(val) => setParams({ ...params, marubozu_delta: val })}
                />
                <SliderField
                  label="Hammer Shadow Multiplier"
                  sublabel="Lower shadow vs body ratio"
                  min={1.0}
                  max={5.0}
                  step={0.1}
                  value={params.hammer_shadow_ratio}
                  onChange={(val) => setParams({ ...params, hammer_shadow_ratio: val })}
                  unit="x"
                />
              </div>

              {/* Multiple Pattern Selection with OR-Logic */}
              <div className="pattern-multi-select-box">
                <div className="pattern-multi-select-header">
                  <div>
                    <span className="pattern-multi-title">Pattern Selection (OR Logic)</span>
                    <small className="pattern-multi-sub">Presence of ANY checked pattern triggers positive result</small>
                  </div>
                  <div className="pattern-preset-btns">
                    <button
                      type="button"
                      className={`mini-preset-btn ${params.pattern_filter === "bullish_marubozu,hammer" ? "active" : ""}`}
                      onClick={() => setPatternPreset("bullish_marubozu,hammer")}
                    >
                      ★ Hammer OR Bullish Marubozu
                    </button>
                    <button
                      type="button"
                      className={`mini-preset-btn ${params.pattern_filter === "bullish_marubozu,hammer,inverted_hammer" ? "active" : ""}`}
                      onClick={() => setPatternPreset("bullish_marubozu,hammer,inverted_hammer")}
                    >
                      Bullish Only
                    </button>
                    <button
                      type="button"
                      className={`mini-preset-btn ${params.pattern_filter === "all" ? "active" : ""}`}
                      onClick={() => setPatternPreset("all")}
                    >
                      All Patterns
                    </button>
                  </div>
                </div>

                <div className="pattern-chips-row">
                  {PATTERN_OPTIONS.map((opt) => {
                    const activeList = (params.pattern_filter || "").split(",").map((s) => s.trim().toLowerCase());
                    const isChecked = activeList.includes("all") || activeList.includes(opt.id);
                    return (
                      <button
                        type="button"
                        key={opt.id}
                        className={`pattern-chip-btn ${isChecked ? "active" : ""}`}
                        onClick={() => togglePattern(opt.id)}
                      >
                        <span className="chip-check">{isChecked ? "✓" : "+"}</span>
                        <span className="chip-label">{opt.label}</span>
                        <span className={`chip-bias ${opt.bias.toLowerCase()}`}>{opt.bias}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Technique 02: Swing Trendline Sliders */}
          {techniques.includes("trendline") && (
            <div style={{ marginTop: "14px", padding: "14px", background: "#f8faf9", borderRadius: "10px", border: "1px solid #e1e9e3" }}>
              <div style={{ marginBottom: "10px" }}>
                <strong style={{ fontSize: "12px", color: "#164638" }}>02. Swing Trendline Settings</strong>
              </div>
              <div className="controls-grid" style={{ padding: "0 0 6px" }}>
                <SliderField
                  label="Swing Period (Highest Swing in N Candles)"
                  sublabel="Body tip higher than N prior/next bars"
                  min={2}
                  max={80}
                  value={params.swing_period}
                  onChange={(val) => setParams({ ...params, swing_period: val })}
                  unit=" bars"
                />
                <SliderField
                  label="Min Pivot Gap (Between Two Swings)"
                  sublabel="Gap before checking next swing point"
                  min={1}
                  max={50}
                  value={params.min_pivot_gap}
                  onChange={(val) => setParams({ ...params, min_pivot_gap: val })}
                  unit=" bars"
                />
                <SliderField
                  label="Min Candles Away from Current Price"
                  sublabel="Bars before current price to confirm swing high"
                  min={1}
                  max={30}
                  value={params.min_right_bars}
                  onChange={(val) => setParams({ ...params, min_right_bars: val })}
                  unit=" bars"
                />
                <SliderField
                  label="Pivot Depth Window (N Bars Before & After)"
                  sublabel="Bars before & after pivot to check lowest price"
                  min={1}
                  max={50}
                  value={params.pivot_depth_bars}
                  onChange={(val) => setParams({ ...params, pivot_depth_bars: val })}
                  unit=" bars"
                />
                <SliderField
                  label="Min Pivot Price Drop (x% Below Pivot)"
                  sublabel="Lowest price must be at least x% less than pivot body"
                  min={0.0}
                  max={20.0}
                  step={0.5}
                  value={params.pivot_depth_pct}
                  onChange={(val) => setParams({ ...params, pivot_depth_pct: val })}
                  unit="%"
                />
                <SliderField
                  label="Trendline Breakout Window"
                  sublabel="Breakout within last N candles"
                  min={1}
                  max={50}
                  value={params.trendline_window}
                  onChange={(val) => setParams({ ...params, trendline_window: val, signal_window: val })}
                  unit=" bars"
                />
              </div>
            </div>
          )}

          {/* Technique 03: SMA Crossover Sliders */}
          {techniques.includes("sma") && (
            <div style={{ marginTop: "14px", padding: "14px", background: "#f8faf9", borderRadius: "10px", border: "1px solid #e1e9e3" }}>
              <div style={{ marginBottom: "10px" }}>
                <strong style={{ fontSize: "12px", color: "#164638" }}>03. SMA Crossover Settings</strong>
              </div>
              <div className="controls-grid" style={{ padding: "0 0 6px" }}>
                <SliderField
                  label="Fast SMA Period"
                  sublabel="Short moving average length"
                  min={2}
                  max={50}
                  value={params.fast_period}
                  onChange={(val) => setParams({ ...params, fast_period: val })}
                  unit=" bars"
                />
                <SliderField
                  label="Slow SMA Period"
                  sublabel="Long moving average length"
                  min={params.fast_period + 1}
                  max={200}
                  value={params.slow_period}
                  onChange={(val) => setParams({ ...params, slow_period: val })}
                  unit=" bars"
                />
                <SliderField
                  label="SMA Crossover Window"
                  sublabel="Crossover within last N bars"
                  min={1}
                  max={50}
                  value={params.sma_window}
                  onChange={(val) => setParams({ ...params, sma_window: val })}
                  unit=" bars"
                />
              </div>
            </div>
          )}

          {/* Technique 04: RSI Sliders */}
          {techniques.includes("rsi") && (
            <div style={{ marginTop: "14px", padding: "14px", background: "#f8faf9", borderRadius: "10px", border: "1px solid #e1e9e3" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px", flexWrap: "wrap", gap: "10px" }}>
                <strong style={{ fontSize: "12px", color: "#164638" }}>04. RSI Momentum Settings</strong>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "11px", fontWeight: 600, color: "#334155" }}>Trigger Rule:</span>
                  <select
                    className="sort-select"
                    style={{ padding: "4px 8px", fontSize: "11px" }}
                    value={params.rsi_rule}
                    onChange={(e) => setParams({ ...params, rsi_rule: e.target.value })}
                  >
                    <option value="any_bullish">★ Any Bullish Trigger (Bounce, Midline or MA)</option>
                    <option value="oversold_bounce">Oversold Bounce (Cross above Oversold Level)</option>
                    <option value="midline_cross">Midline Crossover (Cross above 50)</option>
                    <option value="ma_cross">RSI Signal MA Cross (RSI crosses Signal MA)</option>
                  </select>
                </div>
              </div>
              <div className="controls-grid" style={{ padding: "0 0 6px" }}>
                <SliderField
                  label="RSI Lookback Period"
                  sublabel="Number of candles for Wilder's RSI"
                  min={2}
                  max={50}
                  value={params.rsi_period}
                  onChange={(val) => setParams({ ...params, rsi_period: val })}
                  unit=" bars"
                />
                <SliderField
                  label="RSI Oversold Level"
                  sublabel="Lower threshold for bullish rebound"
                  min={10}
                  max={45}
                  value={params.rsi_oversold}
                  onChange={(val) => setParams({ ...params, rsi_oversold: val })}
                  unit="%"
                />
                <SliderField
                  label="RSI Overbought Level"
                  sublabel="Upper threshold for bearish drop"
                  min={55}
                  max={90}
                  value={params.rsi_overbought}
                  onChange={(val) => setParams({ ...params, rsi_overbought: val })}
                  unit="%"
                />
                <SliderField
                  label="RSI Signal Window"
                  sublabel="Crossover occurred within last N bars"
                  min={1}
                  max={50}
                  value={params.rsi_window}
                  onChange={(val) => setParams({ ...params, rsi_window: val })}
                  unit=" bars"
                />
                <SliderField
                  label="RSI Signal MA Period"
                  sublabel="Moving average smoothing of RSI"
                  min={2}
                  max={30}
                  value={params.rsi_signal_ma_period}
                  onChange={(val) => setParams({ ...params, rsi_signal_ma_period: val })}
                  unit=" bars"
                />
              </div>
            </div>
          )}
        </div>

        <div className="control-footer">
          <p>
            {source === "yahoo"
              ? `Free data via Yahoo Finance on ${timeframe.toUpperCase()} timeframe. Mixing: ${techniques.join(" + ")} (${confluenceMode === "all" ? "Strict All" : "Any Match"}).`
              : "CSV data stays in this local app session."}
          </p>
          <button className="button scan-button" disabled={!canScan} onClick={scan}>
            {busy ? <><span className="spinner" />Scanning…</> : <>Run {timeframe.toUpperCase()} confluence scan <span>→</span></>}
          </button>
        </div>
      </section>

      <section className="workspace">
        <div className="workspace-title">
          <div>
            <span className="step">02</span>
            <h2>{timeframe.toUpperCase()} Multi-Technique Confluence Desk</h2>
          </div>
          {result && <span className="last-updated">Updated {new Date(result.updated_at).toLocaleTimeString()}</span>}
        </div>

        {/* Metrics Row */}
        <div className="metric-row">
          <div className="metric-card">
            <span>Signals Triggered ({confluenceMode === "all" ? "All Matched" : "Any Matched"})</span>
            <strong>{result ? result.signals.length : "—"}</strong>
            <small>{result ? `${result.scanned} symbols scanned` : "Run scan to begin"}</small>
          </div>
          <div className="metric-card green">
            <span>Active Techniques</span>
            <strong>{techniques.length}</strong>
            <small>{techniques.join(" · ")}</small>
          </div>
          <div className="metric-card red">
            <span>Watching (No Confluence)</span>
            <strong>{result ? result.watching.length : "—"}</strong>
            <small>Candidates not meeting active criteria</small>
          </div>
        </div>

        {/* Results Desk Tabs */}
        <div className="desk-tabs">
          <button className={tab === "signals" ? "active" : ""} onClick={() => setTab("signals")}>
            Triggered signals ({confluenceMode === "all" ? "Strict Confluence" : "Any match"}) <span>{result?.signals.length ?? 0}</span>
          </button>
          <button className={tab === "watching" ? "active" : ""} onClick={() => setTab("watching")}>
            Watching (Failed criteria) <span>{result?.watching.length ?? 0}</span>
          </button>
        </div>

        <div className="desk-grid">
          <div className="table-card">
            {!result ? (
              <div className="empty-state">
                <div className="empty-icon">↗</div>
                <strong>Ready to scan</strong>
                <p>Adjust your sliders and click 'Run {timeframe.toUpperCase()} confluence scan'.</p>
              </div>
            ) : (
              <>
                <div className="table-top">
                  <div>
                    <strong>
                      {tab === "signals"
                        ? `Confluence Signals (${confluenceMode === "all" ? "Matched ALL" : "Matched ANY"} active techniques)`
                        : "Watching Candidates (Failed active confluence criteria — NOT NOTIFIED)"}
                    </strong>
                    <small>
                      {tab === "signals"
                        ? "Only stocks fulfilling all active requirements appear here"
                        : "These candidates failed one or more active conditions and are NOT pinged"}
                    </small>
                  </div>
                  {/* Sort Order Selector */}
                  <div className="sort-control-bar">
                    <span style={{ fontSize: "10px", color: "#64748b", fontWeight: 600 }}>Sort by:</span>
                    <select
                      className="sort-select"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value)}
                    >
                      <option value="latest">Latest Breakout / Signal First</option>
                      <option value="oldest">Oldest Breakout in Window First</option>
                      <option value="confluence">Highest Confluence Score First</option>
                      <option value="symbol">Symbol A → Z</option>
                    </select>
                  </div>
                </div>

                {tab === "signals" && sortedCurrentRows.length === 0 ? (
                  <div className="no-signals-box">
                    <div className="no-signals-badge">0 OF {result.scanned} STOCKS QUALIFIED</div>
                    <h3>None fulfilled all active requirements</h3>
                    <p className="no-signals-desc">
                      {confluenceMode === "all"
                        ? `None of the ${result.scanned} scanned stocks met all ${techniques.length} active techniques (${techniques.map((t) => t.toUpperCase()).join(" + ")}). Zero stocks qualify for alert.`
                        : `None of the ${result.scanned} scanned stocks met any active criteria.`}
                    </p>
                    {techniques.includes("trendline") && (
                      <div className="trendline-pivot-callout">
                        <strong>Trendline Pivot Notice:</strong>{" "}
                        {result.trendline_pivots_fulfilled === 0
                          ? `No stocks fulfilled the body-tip pivot point conditions (radius: ${params.swing_period}b, min gap: ${params.min_pivot_gap}b, clearance: ${params.min_right_bars}b, depth: ≥${params.pivot_depth_pct}% drop in ±${params.pivot_depth_bars}b). None could form a valid trendline.`
                          : `Valid body-tip trendlines were identified for ${result.trendline_pivots_fulfilled} stocks, but none had an active breakout crossing within the last ${params.trendline_window} candles.`}
                      </div>
                    )}
                    <p className="no-signals-footer">
                      Stocks with partial matches (e.g. 2/{techniques.length} or 1/{techniques.length}) are <strong>NOT</strong> pinged. To review non-qualifying candidates that did not meet all criteria, switch to the{" "}
                      <button
                        type="button"
                        className="inline-tab-link"
                        onClick={() => setTab("watching")}
                      >
                        Watching (Failed criteria)
                      </button>{" "}
                      tab.
                    </p>
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>Techniques Matched</th>
                          <th>Latest Trigger</th>
                          <th>Close</th>
                          <th>Measurements / Status</th>
                          <th>Confluence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedCurrentRows.map((row) => (
                          <tr
                            key={row.symbol}
                            className={selected === row.symbol ? "selected" : ""}
                            onClick={() => openChart(row.symbol, timeframe)}
                          >
                            <td>
                              <strong>
                                {row.symbol}
                                {watchlist.some((i) => i.symbol === row.symbol) && (
                                  <span className="watched-star" title="Tracked in Watchlist">★</span>
                                )}
                              </strong>
                              <small>{row.last_date}</small>
                            </td>
                            <td>
                              <div className="badge-flow">
                                {row.matched_badges?.length > 0 ? (
                                  row.matched_badges.map((b, bIdx) => (
                                    <SignalBadge key={bIdx} type={b.type} label={b.label} />
                                  ))
                                ) : (
                                  <SignalBadge type={null} label="Failed criteria" />
                                )}
                              </div>
                            </td>
                            <td>
                              <strong>{row.latest_signal?.date || "—"}</strong>
                              {row.latest_signal?.bars_ago != null && (
                                <small style={{ display: "block", color: "#64748b" }}>
                                  {row.latest_signal.bars_ago === 0 ? "Latest bar" : `${row.latest_signal.bars_ago} bars ago`}
                                </small>
                              )}
                            </td>
                            <td>₹{fmt(row.close)}</td>
                            <td>
                              <span style={{ fontSize: "9px", color: "#475569" }}>
                                {row.status_text || "—"}
                              </span>
                            </td>
                            <td>
                              <span className={`confluence-pill ${!row.is_confluence_signal ? "failed" : ""}`}>
                                {row.confluence_score || `${row.matched_count || 0}/${row.total_enabled || techniques.length}`}
                                {!row.is_confluence_signal && " (Failed)"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {result.errors?.length > 0 && (
                  <details className="scan-errors">
                    <summary>{result.errors.length} symbols could not be scanned</summary>
                    {result.errors.slice(0, 10).map((e) => <p key={e.symbol}><b>{e.symbol}</b> — {e.error}</p>)}
                  </details>
                )}
              </>
            )}
          </div>

          <div className="chart-card">
            <div className="chart-heading">
              <div>
                <span className="step">03</span>
                <div>
                  <strong>{chart ? chart.symbol : "Chart review"}</strong>
                  <small>
                    {chart
                      ? `${chart.analysis.last_date} close · Unified multi-technique overlay`
                      : "Select a stock from the table to review chart"}
                  </small>
                </div>
              </div>
              {chart && (
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  {(() => {
                    const watched = watchlist.find((i) => i.symbol === chart.symbol);
                    if (watched) {
                      return (
                        <button
                          type="button"
                          className="watchlist-header-btn watched"
                          onClick={() => openWatchlistModal(chart.symbol, timeframe, chart.analysis.close, watched)}
                          title="Click to edit entry/exit levels in watchlist"
                        >
                          ★ In Watchlist ({watched.targetPlPct >= 0 ? "+" : ""}{fmt(watched.targetPlPct)}%)
                        </button>
                      );
                    } else {
                      return (
                        <button
                          type="button"
                          className="watchlist-header-btn"
                          onClick={() => openWatchlistModal(chart.symbol, timeframe, chart.analysis.close)}
                        >
                          ⭐ Add to Watchlist
                        </button>
                      );
                    }
                  })()}
                  <span className="chart-interval">{timeframe.toUpperCase()} CANDLES</span>
                </div>
              )}
            </div>

            {chart ? (
              <>
                {techniques.includes("trendline") && (chart.analysis.swing_highs?.length || 0) < 2 && (
                  <div className="chart-pivot-alert">
                    <span className="alert-badge">Notice</span>
                    None fulfilled pivot conditions for {chart.symbol} (found {chart.analysis.swing_highs?.length || 0} valid pivots; need at least 2 meeting ±{params.pivot_depth_bars}b, -{params.pivot_depth_pct}% depth). No trendline drawn.
                  </div>
                )}
                <LineChart
                  data={chart}
                  techniques={techniques}
                  timeframe={timeframe}
                  entryPrice={watchlist.find((i) => i.symbol === chart.symbol)?.entryAmount}
                  exitPrice={watchlist.find((i) => i.symbol === chart.symbol)?.exitAmount}
                />
                <div className="legend">
                  <span><i className="legend-candle-blue" />Bullish (C ≥ O)</span>
                  <span><i className="legend-candle-down" />Bearish (C &lt; O)</span>
                  {watchlist.some((i) => i.symbol === chart.symbol) && (
                    <>
                      <span><i className="legend-entry-line" />Entry Level</span>
                      <span><i className="legend-exit-line" />Exit Target</span>
                    </>
                  )}
                  {techniques.includes("trendline") && (
                    <>
                      <span><i className="legend-trendline-ext" />Extended Trendline</span>
                      <span><i className="legend-pivot-marker" />Body Tip Pivot (P1, P2)</span>
                    </>
                  )}
                  {techniques.includes("pattern") && (
                    <span><i className="legend-pattern-pin" />PIN Pattern Badge</span>
                  )}
                  {techniques.includes("sma") && (
                    <>
                      <span><i className="legend-fast" />Fast SMA</span>
                      <span><i className="legend-slow" />Slow SMA</span>
                    </>
                  )}
                  {techniques.includes("rsi") && (
                    <>
                      <span><i className="legend-rsi" />RSI ({params.rsi_period || 14})</span>
                      <span><i className="legend-rsi-signal" />RSI Signal MA</span>
                    </>
                  )}
                </div>
                <div className="line-values">
                  <div>
                    <small>Current Close</small>
                    <b>₹{fmt(chart.analysis.close)}</b>
                  </div>
                  {(() => {
                    const watched = watchlist.find((i) => i.symbol === chart.symbol);
                    if (!watched) return null;
                    return (
                      <>
                        <div>
                          <small>Tracked Entry</small>
                          <b style={{ color: "#059669" }}>₹{fmt(watched.entryAmount)}</b>
                        </div>
                        <div>
                          <small>Exit Target</small>
                          <b style={{ color: "#2563eb" }}>₹{fmt(watched.exitAmount)}</b>
                        </div>
                        <div>
                          <small>Target P/L</small>
                          <b style={{ color: watched.targetPlPct >= 0 ? "#059669" : "#dc2626" }}>
                            {watched.targetPlPct >= 0 ? "+" : ""}{fmt(watched.targetPlPct)}%
                          </b>
                        </div>
                        <div>
                          <small>Current P/L</small>
                          <b style={{ color: watched.currentPlPct >= 0 ? "#059669" : "#dc2626" }}>
                            {watched.currentPlPct >= 0 ? "+" : ""}{fmt(watched.currentPlPct)}%
                          </b>
                        </div>
                      </>
                    );
                  })()}
                  {techniques.includes("trendline") && (
                    <div>
                      <small>Trendline Level</small>
                      <b>{chart.analysis.resistance ? `₹${fmt(chart.analysis.resistance)}` : "—"}</b>
                    </div>
                  )}
                  {techniques.includes("pattern") && (
                    <div>
                      <small>Pattern Detected</small>
                      <b>{chart.analysis.latest_signal?.name || "None in window"}</b>
                    </div>
                  )}
                  {techniques.includes("sma") && (
                    <div>
                      <small>Fast / Slow SMA</small>
                      <b>{fmt(chart.analysis.fast_sma)} / {fmt(chart.analysis.slow_sma)}</b>
                    </div>
                  )}
                  {techniques.includes("rsi") && chart.analysis?.rsi != null && (
                    <div>
                      <small>RSI ({params.rsi_period || 14})</small>
                      <b style={{ color: (chart.analysis.rsi || 0) >= 50 ? "#059669" : "#dc2626" }}>
                        {fmt(chart.analysis.rsi)}
                      </b>
                    </div>
                  )}
                  <div>
                    <small>Confluence Score</small>
                    <b style={{ color: "#164638" }}>{chart.analysis.confluence_score || "—"}</b>
                  </div>
                </div>
              </>
            ) : (
              <div className="chart-placeholder">
                <div className="chart-scribble">╱╲╱╲</div>
                <span>
                  {result && result.signals?.length === 0
                    ? `0 STOCKS QUALIFIED AS CONFLUENCE SIGNALS · SELECT A CANDIDATE FROM "WATCHING" OR ADJUST SLIDERS`
                    : `${timeframe.toUpperCase()} CANDLESTICKS → MULTI-TECHNIQUE OVERLAYS → DUAL SLIDERS`}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="method-note">
          <span>CONFLUENCE ENGINE & MULTI-TIMEFRAME RULES</span>
          <p>
            Supports Intraday (5m, 15m, 1h), Daily (1D), Weekly (1W), and Monthly (1M) charts. Mix any combination of:
            (1) Candlestick Patterns (Bullish/Bearish Marubozu, Hammer, Shooting Star with Trade Trap Rule);
            (2) Body-Tip Swing Trendlines touching candle closes/starts closest to current date and extended in both directions;
            (3) Fast/Slow SMA Crossovers. All sliders include dual numeric inputs for precise user calibration, and results can be sorted by latest or oldest breakout.
          </p>
        </div>
      </section>
      </>
      )}

      <footer>
        <span>SIGNAL WORKSHOP <b>•</b> MULTI-FACTOR RESEARCH TOOL</span>
        <span>Yahoo data is for personal research <b>·</b> CSV data remains local</span>
      </footer>
    </main>
  );
}
