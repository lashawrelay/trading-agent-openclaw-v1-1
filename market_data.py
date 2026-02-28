import requests
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AlpacaMarketData:
    def __init__(self, api_key: str, api_secret: str, data_url: str):
        self.data_url = data_url.rstrip("/")
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "accept": "application/json",
        }

    def bars(self, symbol: str, timeframe: str, start: datetime, end: datetime, limit: int = 1000) -> List[Dict[str, Any]]:
        sym = symbol
        params = {
            "symbols": sym,
            "timeframe": timeframe,
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "limit": limit,
        }
        r = requests.get(f"{self.data_url}/v1beta3/crypto/us/bars", headers=self.headers, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("bars", {}).get(sym, [])

    def latest_quote(self, symbol: str) -> Dict[str, Any]:
        sym = symbol
        r = requests.get(
            f"{self.data_url}/v1beta3/crypto/us/latest/quotes?symbols={sym}",
            headers=self.headers,
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("quotes", {}).get(sym, {})

    def build_universe(self, candidates: List[str], top_n: int) -> List[Dict[str, Any]]:
        end = utc_now()
        start = end - timedelta(hours=24)
        rows = []
        for s in candidates:
            try:
                bars = self.bars(s, "1Min", start, end, 1440)
                if not bars:
                    continue
                dv = sum(float(b.get("vw", 0) or 0) * float(b.get("v", 0) or 0) for b in bars)
                q = self.latest_quote(s)
                bid = float(q.get("bp", 0) or 0)
                ask = float(q.get("ap", 0) or 0)
                if bid <= 0 or ask <= 0:
                    continue
                spread_pct = (ask - bid) / ((ask + bid) / 2)
                rows.append({"symbol": s, "dollar_volume_24h": dv, "spread_pct": spread_pct})
            except Exception:
                continue
        rows.sort(key=lambda x: (-x["dollar_volume_24h"], x["spread_pct"]))
        top = rows[:top_n]
        top.sort(key=lambda x: x["spread_pct"])
        return top

    @staticmethod
    def _sma(values: List[float], n: int):
        if len(values) < n:
            return None
        return sum(values[-n:]) / n

    @staticmethod
    def _rsi(closes: List[float], period: int = 14):
        if len(closes) < period + 1:
            return None
        gains, losses = [], []
        for i in range(-period, 0):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0))
            losses.append(abs(min(d, 0)))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14):
        if len(closes) < period + 1:
            return None
        tr = []
        for i in range(1, len(closes)):
            tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        if len(tr) < period:
            return None
        return sum(tr[-period:]) / period

    def symbol_state(self, symbol: str) -> Dict[str, Any]:
        end = utc_now()
        bars_1m = self.bars(symbol, "1Min", end - timedelta(minutes=180), end, 180)
        bars_1h = self.bars(symbol, "1Hour", end - timedelta(hours=120), end, 120)

        closes_1m = [float(b["c"]) for b in bars_1m]
        highs_1m = [float(b["h"]) for b in bars_1m]
        lows_1m = [float(b["l"]) for b in bars_1m]
        closes_1h = [float(b["c"]) for b in bars_1h]

        quote = self.latest_quote(symbol)
        bid = float(quote.get("bp", 0) or 0)
        ask = float(quote.get("ap", 0) or 0)
        mid = (bid + ask) / 2 if bid and ask else (closes_1m[-1] if closes_1m else 0)
        spread_pct = (ask - bid) / mid if (bid and ask and mid) else 0

        return {
            "symbol": symbol,
            "spread_pct": spread_pct,
            "price_mid": mid,
            "atr_1m": self._atr(highs_1m, lows_1m, closes_1m, 14),
            "rsi_1m": self._rsi(closes_1m, 14),
            "sma20_1h": self._sma(closes_1h, 20),
            "sma50_1h": self._sma(closes_1h, 50),
        }
