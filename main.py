"""
Gate.io Spot LONG Signal Scanner
=================================
Scans all USDT spot pairs on Gate.io using a multi-timeframe confluence
strategy combining:
  - SMC / ICT market structure (trend bias, order blocks)
  - Fair Value Gaps (FVG)
  - Fibonacci retracement (golden zone)
  - Volume Profile (POC / value area)
  - MACD & RSI momentum

4h = directional bias, 15m = entry trigger.

Usage:
    python main.py            # run continuously (loop every SCAN_INTERVAL_SECONDS)
    python main.py --once     # run a single scan pass and exit
    python main.py --pair BTC_USDT --once   # debug a single pair
    python main.py --top 30   # only scan top 30 pairs by 24h volume
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import config
from gateio_client import GateIOClient
import signal_engine as engine
import telegram_notify as tg


# Tracks last alert time per pair to respect cooldown
_last_alert = {}


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def get_candidate_pairs(client, top_n=None):
    """Get USDT spot pairs filtered by min 24h volume, optionally top-N by volume."""
    all_pairs = set(client.get_spot_pairs())
    tickers = client.get_tickers()

    candidates = []
    for pair in all_pairs:
        t = tickers.get(pair)
        if not t:
            continue
        if t["quote_volume_24h"] < config.MIN_24H_VOLUME_USDT:
            continue
        candidates.append((pair, t["quote_volume_24h"]))

    candidates.sort(key=lambda x: x[1], reverse=True)

    if top_n:
        candidates = candidates[:top_n]

    return [p for p, _ in candidates]


def scan_pair(client, pair):
    """
    Fetch 4h + 15m candles for a pair, run the confluence analysis,
    and return a signal dict if it's a LONG candidate (score above threshold),
    else None. Returns None on any data error.
    """
    try:
        df_4h = client.get_candlesticks(pair, config.HTF_INTERVAL, config.HTF_CANDLE_LIMIT)
        df_15m = client.get_candlesticks(pair, config.LTF_INTERVAL, config.LTF_CANDLE_LIMIT)
    except Exception as e:
        log(f"  ! {pair}: data fetch error ({e})")
        return None

    if df_4h.empty or df_15m.empty or len(df_4h) < 30 or len(df_15m) < 30:
        return None

    try:
        htf = engine.analyze_htf(df_4h)
        ltf = engine.analyze_ltf(df_15m)
        score, checks = engine.score_long_setup(htf, ltf)
    except Exception as e:
        log(f"  ! {pair}: analysis error ({e})")
        return None

    if score >= config.SIGNAL_SCORE_THRESHOLD:
        return engine.build_signal(pair, htf, ltf, score, checks)

    return None


def should_alert(pair):
    last = _last_alert.get(pair)
    if last is None:
        return True
    elapsed_min = (time.time() - last) / 60
    return elapsed_min >= config.ALERT_COOLDOWN_MINUTES


def run_scan(client, pairs, send_alerts=True):
    found = []
    log(f"Scanning {len(pairs)} pairs (4h bias + 15m entry, threshold {config.SIGNAL_SCORE_THRESHOLD}/{config.MAX_SCORE})...")

    for idx, pair in enumerate(pairs, 1):
        signal = scan_pair(client, pair)
        if signal:
            found.append(signal)
            log(f"  >>> LONG signal: {pair}  score={signal['score']}/{signal['max_score']}")

            if send_alerts and should_alert(pair):
                msg = tg.format_signal_message(signal)
                tg.send_telegram_message(msg)
                _last_alert[pair] = time.time()

        if idx % 50 == 0:
            log(f"  ...{idx}/{len(pairs)} scanned")

    log(f"Scan complete. {len(found)} long signal(s) found.")
    return found


def print_signal_console(signal):
    pair = signal["pair"]
    print("\n" + "=" * 60)
    print(f"LONG SIGNAL: {pair}  |  Score: {signal['score']}/{signal['max_score']}")
    print("-" * 60)
    print(f"Entry:     {signal['entry']:.6g}")
    print(f"Stop Loss: {signal['stop_loss']:.6g}")
    print(f"TP1: {signal['tp1']:.6g}  (R:R {signal['rr1']})")
    print(f"TP2: {signal['tp2']:.6g}  (R:R {signal['rr2']})")
    print(f"TP3: {signal['tp3']:.6g}  (R:R {signal['rr3']})")
    print(f"4h Bias: {signal['htf']['bias']}   15m RSI: {signal['ltf']['rsi']:.1f}")
    for name, passed in signal["checks"].items():
        print(f"  [{'x' if passed else ' '}] {name}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Gate.io Spot LONG Signal Scanner")
    parser.add_argument("--once", action="store_true", help="run a single scan and exit")
    parser.add_argument("--pair", type=str, default=None, help="scan a single pair (e.g. BTC_USDT)")
    parser.add_argument("--top", type=int, default=None, help="only scan top N pairs by 24h volume")
    parser.add_argument("--no-telegram", action="store_true", help="disable Telegram alerts")
    args = parser.parse_args()

    client = GateIOClient()
    send_alerts = not args.no_telegram

    if args.pair:
        pairs = [args.pair.upper()]
    else:
        log("Fetching spot pair list & 24h volumes from Gate.io...")
        pairs = get_candidate_pairs(client, top_n=args.top)
        log(f"{len(pairs)} pairs pass the {config.MIN_24H_VOLUME_USDT:,.0f} USDT 24h-volume filter.")

    if args.once or args.pair:
        signals = run_scan(client, pairs, send_alerts=send_alerts)
        for s in signals:
            print_signal_console(s)
        if not signals:
            print("No long signals found this scan.")
        return

    # Continuous loop
    while True:
        try:
            signals = run_scan(client, pairs, send_alerts=send_alerts)
            for s in signals:
                print_signal_console(s)
        except KeyboardInterrupt:
            log("Interrupted by user. Exiting.")
            sys.exit(0)
        except Exception as e:
            log(f"Scan loop error: {e}")

        log(f"Sleeping {config.SCAN_INTERVAL_SECONDS}s until next scan...\n")
        time.sleep(config.SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
