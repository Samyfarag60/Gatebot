"""
Signal Engine: combines 4h bias + 15m entry triggers into a confluence score
for LONG setups using SMC, ICT (FVG/OB), Volume Profile, MACD, RSI, Fibonacci.
"""

import config
import indicators as ind


def analyze_htf(df_4h):
    """
    Analyze the 4h chart for directional bias.
    Returns dict with bias info and 2 boolean checks for the long score.
    """
    bias = ind.trend_bias(df_4h, lookback=config.FIB_LOOKBACK)
    macd_line, signal_line, hist = ind.macd(df_4h)

    macd_bullish = bool(macd_line.iloc[-1] > signal_line.iloc[-1])
    macd_hist_rising = bool(hist.iloc[-1] > hist.iloc[-2]) if len(hist) > 1 else False

    return {
        "bias": bias,
        "macd_bullish": macd_bullish,
        "macd_hist_rising": macd_hist_rising,
        "macd_hist": float(hist.iloc[-1]),
    }


def analyze_ltf(df_15m):
    """
    Analyze the 15m chart for entry-trigger confluence.
    Returns dict with all component checks + raw values for reporting.
    """
    price = float(df_15m["close"].iloc[-1])

    rsi_series = ind.rsi(df_15m)
    rsi_val = float(rsi_series.iloc[-1])
    rsi_prev = float(rsi_series.iloc[-2]) if len(rsi_series) > 1 else rsi_val

    macd_line, signal_line, hist = ind.macd(df_15m)
    macd_bullish = bool(macd_line.iloc[-1] > signal_line.iloc[-1])
    macd_cross_up = bool(
        macd_line.iloc[-2] <= signal_line.iloc[-2] and macd_line.iloc[-1] > signal_line.iloc[-1]
    ) if len(macd_line) > 1 else False

    fvgs = ind.find_fvgs(df_15m)
    bullish_fvgs = [g for g in fvgs if g["type"] == "bullish" and not g["filled"]]
    in_bullish_fvg = any(ind.price_in_zone(price, g["bottom"], g["top"]) for g in bullish_fvgs)
    near_bullish_fvg = any(
        g["bottom"] <= price <= g["top"] * 1.01 for g in bullish_fvgs
    )

    obs = ind.find_order_blocks(df_15m)
    bullish_obs = [b for b in obs if b["type"] == "bullish" and not b["mitigated"]]
    in_bullish_ob = any(ind.price_in_zone(price, b["bottom"], b["top"]) for b in bullish_obs)

    fib = ind.fib_retracement_zone(df_15m)
    in_golden_zone = bool(fib.get("in_golden_zone") and fib.get("valid_uptrend_structure"))

    vp = ind.volume_profile(df_15m)
    poc = vp["poc"]
    va_low = vp["value_area_low"]
    va_high = vp["value_area_high"]
    near_poc_support = bool(va_low <= price <= va_high)

    return {
        "price": price,
        "rsi": rsi_val,
        "rsi_prev": rsi_prev,
        "rsi_favorable": bool(rsi_val < config.RSI_MAX and (rsi_val > rsi_prev or rsi_val < config.RSI_OVERSOLD + 10)),
        "macd_bullish": macd_bullish,
        "macd_cross_up": macd_cross_up,
        "bullish_fvgs": bullish_fvgs,
        "in_bullish_fvg": in_bullish_fvg or near_bullish_fvg,
        "bullish_obs": bullish_obs,
        "in_bullish_ob": in_bullish_ob,
        "fib": fib,
        "in_golden_zone": in_golden_zone,
        "volume_profile": vp,
        "near_poc_support": near_poc_support,
    }


def score_long_setup(htf, ltf):
    """
    Combine HTF + LTF checks into a confluence score (0-8) for a LONG setup.
    Returns (score, breakdown_dict)
    """
    checks = {
        "4h Trend Bullish (HH/HL)": htf["bias"] == "bullish",
        "4h MACD Bullish": htf["macd_bullish"],
        "4h MACD Histogram Rising": htf["macd_hist_rising"],
        "15m RSI Favorable (<{} & recovering)".format(config.RSI_MAX): ltf["rsi_favorable"],
        "15m MACD Bullish / Cross Up": ltf["macd_bullish"] or ltf["macd_cross_up"],
        "Price in Bullish FVG": ltf["in_bullish_fvg"],
        "Price in Bullish Order Block": ltf["in_bullish_ob"],
        "Fib Golden Zone (0.5-0.786 retrace)": ltf["in_golden_zone"],
        "Near Volume Profile Support (POC/VA)": ltf["near_poc_support"],
    }

    score = sum(1 for v in checks.values() if v)
    return score, checks


def build_signal(pair, htf, ltf, score, checks):
    """Construct a structured signal dict ready for formatting/alerting."""
    price = ltf["price"]
    fib = ltf["fib"]

    # Suggested SL: below nearest bullish OB/FVG bottom or recent swing low
    sl_candidates = [price * 0.985]  # default fallback ~1.5% below
    if ltf["bullish_obs"]:
        sl_candidates.append(min(b["bottom"] for b in ltf["bullish_obs"]) * 0.998)
    if ltf["bullish_fvgs"]:
        sl_candidates.append(min(g["bottom"] for g in ltf["bullish_fvgs"]) * 0.998)
    if fib.get("swing_low"):
        sl_candidates.append(fib["swing_low"] * 0.998)
    stop_loss = min(sl_candidates)

    risk = price - stop_loss
    if risk <= 0:
        risk = price * 0.01

    tp1 = price + risk * 1.5
    tp2 = price + risk * 2.5
    tp3 = price + risk * 4.0

    # Cap TP3 near the recent swing high / fib extension as a sanity check,
    # but never let it drop below TP2 (keep TP ladder monotonic).
    if fib.get("swing_high"):
        tp3 = max(tp2, min(tp3, fib["swing_high"] * 1.02))

    return {
        "pair": pair,
        "score": score,
        "max_score": config.MAX_SCORE,
        "entry": price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rr1": round((tp1 - price) / risk, 2),
        "rr2": round((tp2 - price) / risk, 2),
        "rr3": round((tp3 - price) / risk, 2),
        "checks": checks,
        "htf": htf,
        "ltf": ltf,
    }
