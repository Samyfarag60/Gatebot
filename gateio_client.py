"""
Lightweight client for Gate.io's public Spot Market API (v4).
No API key required for public market data.
"""

import time
import requests
import pandas as pd

import config


class GateIOClient:
    def __init__(self):
        self.base_url = config.GATEIO_BASE_URL
        self.session = requests.Session()

    # ------------------------------------------------------------------
    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        time.sleep(config.RATE_LIMIT_SLEEP)
        return resp.json()

    # ------------------------------------------------------------------
    def get_spot_pairs(self, quote=config.QUOTE_CURRENCY):
        """Return list of tradeable spot pair symbols, e.g. ['BTC_USDT', ...]"""
        data = self._get("/spot/currency_pairs")
        pairs = []
        for item in data:
            if item.get("trade_status") != "tradable":
                continue
            if item.get("quote") != quote:
                continue
            pairs.append(item["id"])
        return pairs

    # ------------------------------------------------------------------
    def get_tickers(self, quote=config.QUOTE_CURRENCY):
        """Return a dict {pair: {quote_volume_24h, last_price, change_pct}}"""
        data = self._get("/spot/tickers")
        out = {}
        for item in data:
            pair = item.get("currency_pair", "")
            if not pair.endswith(f"_{quote}"):
                continue
            try:
                qvol = float(item.get("quote_volume", 0) or 0)
            except (TypeError, ValueError):
                qvol = 0.0
            out[pair] = {
                "quote_volume_24h": qvol,
                "last": float(item.get("last", 0) or 0),
                "change_pct": float(item.get("change_percentage", 0) or 0),
            }
        return out

    # ------------------------------------------------------------------
    def get_candlesticks(self, pair, interval, limit=200):
        """
        Returns a pandas DataFrame with columns:
        timestamp, volume, close, high, low, open  (sorted ascending by time)
        """
        params = {"currency_pair": pair, "interval": interval, "limit": limit}
        data = self._get("/spot/candlesticks", params=params)

        if not data:
            return pd.DataFrame()

        # Gate.io candlestick row format:
        # [timestamp, quote_volume, close, high, low, open, base_volume, window_closed]
        cols = ["timestamp", "quote_volume", "close", "high", "low", "open",
                "base_volume", "window_closed"]
        df = pd.DataFrame(data, columns=cols[:len(data[0])])

        for c in ["close", "high", "low", "open", "quote_volume", "base_volume"]:
            if c in df.columns:
                df[c] = df[c].astype(float)
        df["timestamp"] = df["timestamp"].astype(int)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df
