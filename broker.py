import requests
from typing import Any, Dict, List


class AlpacaBroker:
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "accept": "application/json",
        }

    def account(self) -> Dict[str, Any]:
        r = requests.get(f"{self.base_url}/v2/account", headers=self.headers, timeout=20)
        r.raise_for_status()
        return r.json()

    def positions(self) -> List[Dict[str, Any]]:
        r = requests.get(f"{self.base_url}/v2/positions", headers=self.headers, timeout=20)
        r.raise_for_status()
        return r.json()

    def close_all_positions(self) -> Any:
        r = requests.delete(f"{self.base_url}/v2/positions", headers=self.headers, timeout=20)
        if r.status_code not in (200, 207):
            r.raise_for_status()
        return r.json() if r.content else {"ok": True}

    def submit_limit(self, symbol: str, side: str, qty: float, limit_price: float) -> Dict[str, Any]:
        body = {
            "symbol": symbol.replace("/", ""),
            "side": side.lower(),
            "type": "limit",
            "time_in_force": "gtc",
            "qty": str(round(qty, 8)),
            "limit_price": str(round(limit_price, 8)),
        }
        r = requests.post(f"{self.base_url}/v2/orders", headers=self.headers, json=body, timeout=20)
        r.raise_for_status()
        return r.json()
