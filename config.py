"""
Configuration for the Gate.io Spot Long-Signal Scanner Bot.
Fill in your Telegram credentials below (or set as environment variables).
"""

import os

# ---------------------------------------------------------------------------
# TELEGRAM SETTINGS
# ---------------------------------------------------------------------------
# Create a bot via @BotFather on Telegram to get a token.
# Get your chat_id by messaging @userinfobot or @getidsbot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "PUT_YOUR_CHAT_ID_HERE")

# ---------------------------------------------------------------------------
# SCAN SETTINGS
# ---------------------------------------------------------------------------
QUOTE_CURRENCY = "USDT"          # only scan pairs quoted in USDT
HTF_INTERVAL = "4h"              # higher timeframe = trend / bias
LTF_INTERVAL = "15m"             # lower timeframe = entry trigger

HTF_CANDLE_LIMIT = 200           # candles to fetch for 4h analysis
LTF_CANDLE_LIMIT = 150           # candles to fetch for 15m analysis

# Minimum 24h quote-volume (in USDT) for a pair to be considered.
# Filters out dead/illiquid pairs. Set to 0 to disable.
MIN_24H_VOLUME_USDT = 50000

# How often to run a full scan (seconds)
SCAN_INTERVAL_SECONDS = 15 * 60   # every 15 minutes (matches LTF)

# Confluence score required to fire a LONG signal (out of MAX_SCORE below)
SIGNAL_SCORE_THRESHOLD = 5

# Max points possible (used for display, e.g. "6/8")
MAX_SCORE = 8

# Don't re-alert the same pair within this many minutes
ALERT_COOLDOWN_MINUTES = 240   # 4 hours

# Indicator parameters
RSI_PERIOD = 14
RSI_OVERSOLD = 40          # for long bias, RSI should be below this (or recovering)
RSI_MAX = 65               # don't long if RSI already overbought above this
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

FIB_LOOKBACK = 50           # candles to look back for swing high/low (fib & structure)
FVG_LOOKBACK = 30           # candles to scan for unfilled FVGs
OB_LOOKBACK = 30            # candles to scan for order blocks

VOLUME_PROFILE_BINS = 24    # number of price bins for volume profile
VOLUME_PROFILE_LOOKBACK = 100

# Networking
REQUEST_TIMEOUT = 15
RATE_LIMIT_SLEEP = 0.15     # seconds between API calls to respect Gate.io rate limits

GATEIO_BASE_URL = "https://api.gateio.ws/api/v4"
