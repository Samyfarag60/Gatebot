"""
Indicator & pattern-detection library:
  - RSI, MACD
  - Fair Value Gaps (FVG)
  - Order Blocks (SMC)
  - Swing structure (HH/HL/LH/LL) for trend bias
  - Fibonacci retracement zones
  - Volume Profile (POC / value area)

All functions take a pandas DataFrame with columns: open, high, low, close, quote_volume
and return either a scalar, a Series, or a list of dicts describing zones.
"""

import numpy as np
import pandas as pd

import config


# =====================================================================
# MOMENTUM INDICATORS
# =====================================================================
def rsi(df, period=config.RSI_PERIOD):
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.fillna(50)
    return rsi_val


def macd(df, fast=config.MACD_FAST, slow=config.MACD_SLOW, signal=config.MACD_SIGNAL):
    close = df["close"]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


# =====================================================================
# FAIR VALUE GAPS (FVG) - 3-candle ICT pattern
# =====================================================================
def find_fvgs(df, lookback=config.FVG_LOOKBACK):
    """
    Bullish FVG: low[i] > high[i-2]  -> gap zone = (high[i-2], low[i])
    Bearish FVG: high[i] < low[i-2]  -> gap zone = (high[i], low[i-2])

    Returns list of dicts: {type, top, bottom, index, filled}
    A gap is considered 'filled' if price has traded back into the zone since.
    """
    n = len(df)
    start = max(2, n - lookback)
    gaps = []

    highs = df["high"].values
    lows = df["low"].values

    for i in range(start, n):
        # Bullish FVG
        if lows[i] > highs[i - 2]:
            top, bottom = lows[i], highs[i - 2]
            filled = _zone_filled(df, i + 1, n, bottom, top)
            gaps.append({
                "type": "bullish", "top": top, "bottom": bottom,
                "index": i, "filled": filled
            })
        # Bearish FVG
        if highs[i] < lows[i - 2]:
            top, bottom = lows[i - 2], highs[i]
            filled = _zone_filled(df, i + 1, n, bottom, top)
            gaps.append({
                "type": "bearish", "top": top, "bottom": bottom,
                "index": i, "filled": filled
            })

    return gaps


def _zone_filled(df, start_idx, end_idx, bottom, top):
    """Check whether price has traded back into [bottom, top] after start_idx."""
    if start_idx >= end_idx:
        return False
    sub = df.iloc[start_idx:end_idx]
    touched = ((sub["low"] <= top) & (sub["high"] >= bottom)).any()
    return bool(touched)


# =====================================================================
# ORDER BLOCKS (simplified SMC definition)
# =====================================================================
def find_order_blocks(df, lookback=config.OB_LOOKBACK, impulse_mult=1.5):
    """
    Bullish OB: last bearish (down) candle before a strong bullish impulse candle
                that closes above the down candle's high.
    Bearish OB: last bullish (up) candle before a strong bearish impulse candle
                that closes below the up candle's low.

    'Strong impulse' = candle range > impulse_mult * average range of prior candles.

    Returns list of dicts: {type, top, bottom, index, mitigated}
    """
    n = len(df)
    start = max(5, n - lookback)
    blocks = []

    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    avg_range = (df["high"] - df["low"]).rolling(10).mean().values

    for i in range(start, n - 1):
        body_range = h[i] - l[i]
        if np.isnan(avg_range[i]) or avg_range[i] == 0:
            continue
        is_impulse = body_range > impulse_mult * avg_range[i]

        # Bullish OB: candle i-1 bearish, candle i bullish impulse closing above i-1 high
        if is_impulse and c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] > h[i - 1]:
            top, bottom = h[i - 1], l[i - 1]
            mitigated = _zone_filled(df, i + 1, n, bottom, top)
            blocks.append({
                "type": "bullish", "top": top, "bottom": bottom,
                "index": i - 1, "mitigated": mitigated
            })

        # Bearish OB: candle i-1 bullish, candle i bearish impulse closing below i-1 low
        if is_impulse and c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] < l[i - 1]:
            top, bottom = h[i - 1], l[i - 1]
            mitigated = _zone_filled(df, i + 1, n, bottom, top)
            blocks.append({
                "type": "bearish", "top": top, "bottom": bottom,
                "index": i - 1, "mitigated": mitigated
            })

    return blocks


# =====================================================================
# SWING STRUCTURE / TREND BIAS (HH-HL = bullish, LH-LL = bearish)
# =====================================================================
def swing_points(df, window=3):
    """
    Identify swing highs/lows using a simple fractal (window candles each side).
    Returns two lists of (index, price) tuples: highs, lows
    """
    highs, lows = [], []
    h = df["high"].values
    l = df["low"].values
    n = len(df)

    for i in range(window, n - window):
        if h[i] == max(h[i - window:i + window + 1]):
            highs.append((i, h[i]))
        if l[i] == min(l[i - window:i + window + 1]):
            lows.append((i, l[i]))

    return highs, lows


def trend_bias(df, lookback=config.FIB_LOOKBACK):
    """
    Returns 'bullish', 'bearish', or 'neutral' based on the last two
    swing highs and lows within the lookback window.
    """
    sub = df.iloc[-lookback:].reset_index(drop=True)
    highs, lows = swing_points(sub, window=2)

    if len(highs) < 2 or len(lows) < 2:
        # fallback: compare EMA20 vs EMA50 slope
        if len(df) >= 50:
            ema20 = df["close"].ewm(span=20).mean().iloc[-1]
            ema50 = df["close"].ewm(span=50).mean().iloc[-1]
            return "bullish" if ema20 > ema50 else "bearish"
        return "neutral"

    last_two_highs = [p for _, p in highs[-2:]]
    last_two_lows = [p for _, p in lows[-2:]]

    higher_high = last_two_highs[-1] > last_two_highs[-2]
    higher_low = last_two_lows[-1] > last_two_lows[-2]
    lower_high = last_two_highs[-1] < last_two_highs[-2]
    lower_low = last_two_lows[-1] < last_two_lows[-2]

    if higher_high and higher_low:
        return "bullish"
    if lower_high and lower_low:
        return "bearish"
    return "neutral"


# =====================================================================
# FIBONACCI RETRACEMENT
# =====================================================================
def fib_retracement_zone(df, lookback=config.FIB_LOOKBACK):
    """
    Find the most recent significant swing low -> swing high (for an uptrend)
    and return the 0.5 - 0.786 'golden zone' for long entries, plus the
    current price's position relative to it.

    Returns dict: {swing_low, swing_high, fib_50, fib_618, fib_786, in_golden_zone}
    """
    sub = df.iloc[-lookback:]
    swing_low = sub["low"].min()
    swing_high = sub["high"].max()
    low_idx = sub["low"].idxmin()
    high_idx = sub["high"].idxmax()

    current = df["close"].iloc[-1]
    diff = swing_high - swing_low
    if diff <= 0:
        return {
            "swing_low": swing_low, "swing_high": swing_high,
            "fib_50": None, "fib_618": None, "fib_786": None,
            "in_golden_zone": False, "valid_uptrend_structure": False
        }

    fib_50 = swing_high - 0.5 * diff
    fib_618 = swing_high - 0.618 * diff
    fib_786 = swing_high - 0.786 * diff

    # Golden zone for longs = between fib_786 (lower) and fib_50 (upper)
    in_golden_zone = fib_786 <= current <= fib_50

    # valid structure: the low should have occurred AFTER the high
    # (i.e. price made a high then pulled back) for a retracement-buy setup
    valid_uptrend_structure = low_idx > high_idx

    return {
        "swing_low": swing_low, "swing_high": swing_high,
        "fib_50": fib_50, "fib_618": fib_618, "fib_786": fib_786,
        "in_golden_zone": in_golden_zone,
        "valid_uptrend_structure": valid_uptrend_structure
    }


# =====================================================================
# VOLUME PROFILE
# =====================================================================
def volume_profile(df, bins=config.VOLUME_PROFILE_BINS, lookback=config.VOLUME_PROFILE_LOOKBACK):
    """
    Builds a simple volume profile over the lookback window.
    Returns dict: {poc, hvn_levels, lvn_levels, value_area_low, value_area_high}
      poc = Point of Control (price level with highest traded volume)
    """
    sub = df.iloc[-lookback:]
    price_min = sub["low"].min()
    price_max = sub["high"].max()

    if price_max <= price_min:
        return {"poc": sub["close"].iloc[-1], "value_area_low": price_min,
                "value_area_high": price_max}

    bin_edges = np.linspace(price_min, price_max, bins + 1)
    bin_vol = np.zeros(bins)

    for _, row in sub.iterrows():
        # distribute candle's volume across the bins it overlaps (typical-price approx)
        typical = (row["high"] + row["low"] + row["close"]) / 3
        bin_idx = np.clip(np.digitize(typical, bin_edges) - 1, 0, bins - 1)
        bin_vol[bin_idx] += row["quote_volume"]

    poc_idx = int(np.argmax(bin_vol))
    poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2

    # Value area = bins containing ~70% of volume, expanding from POC
    total_vol = bin_vol.sum()
    target = 0.70 * total_vol
    included = {poc_idx}
    acc = bin_vol[poc_idx]
    left, right = poc_idx - 1, poc_idx + 1
    while acc < target and (left >= 0 or right < bins):
        left_vol = bin_vol[left] if left >= 0 else -1
        right_vol = bin_vol[right] if right < bins else -1
        if right_vol >= left_vol:
            acc += right_vol
            included.add(right)
            right += 1
        else:
            acc += left_vol
            included.add(left)
            left -= 1

    va_low_idx = min(included)
    va_high_idx = max(included)

    return {
        "poc": poc_price,
        "value_area_low": bin_edges[va_low_idx],
        "value_area_high": bin_edges[va_high_idx + 1],
    }


# =====================================================================
# PRICE-IN-ZONE HELPERS
# =====================================================================
def price_in_zone(price, bottom, top, tolerance_pct=0.0015):
    """True if price is within [bottom, top] (with small tolerance)."""
    tol = price * tolerance_pct
    return (bottom - tol) <= price <= (top + tol)
