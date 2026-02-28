import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_date_str(dt: Optional[datetime] = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y-%m-%d")


@dataclass
class EngineConfig:
    start_equity: float
    daily_max_drawdown_pct: float
    max_trades_per_day: int
    max_position_pct: float
    top_n: int
    maker_fee_bps: float


class DeterministicEngine:
    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg

    def init_state(self) -> Dict[str, Any]:
        return {
            "stopped_forever": False,
            "weekly_last_cutoff_hour": None,
            "daily": {
                "date": utc_date_str(),
                "day_start_equity": None,
                "halted": False,
                "trades": 0,
            },
        }

    def rollover_day_if_needed(self, state: Dict[str, Any]):
        d = utc_date_str()
        if state.get("daily", {}).get("date") != d:
            state["daily"] = {
                "date": d,
                "day_start_equity": None,
                "halted": False,
                "trades": 0,
            }

    def weekly_cutoff(self, state: Dict[str, Any], equity: float, now: Optional[datetime] = None) -> Optional[str]:
        now = now or utc_now()
        if now.weekday() == 6 and now.hour == 0:
            stamp = now.strftime("%Y-%m-%dT%H")
            if state.get("weekly_last_cutoff_hour") != stamp:
                state["weekly_last_cutoff_hour"] = stamp
                if equity < self.cfg.start_equity:
                    state["stopped_forever"] = True
                    return "STOP_FOREVER_EQUITY_BELOW_START"
                return "WEEKLY_FLATTEN"
        return None

    def apply_daily_guard(self, state: Dict[str, Any], equity: float) -> Optional[str]:
        self.rollover_day_if_needed(state)
        daily = state["daily"]
        if daily["day_start_equity"] is None:
            daily["day_start_equity"] = equity
            return None
        if daily["day_start_equity"] <= 0:
            daily["halted"] = True
            return "HALT_DAY_INVALID_DAY_START_EQUITY"
        dd = (daily["day_start_equity"] - equity) / daily["day_start_equity"]
        if dd >= self.cfg.daily_max_drawdown_pct / 100:
            daily["halted"] = True
            return "HALT_DAY_DRAWDOWN"
        return None

    def validate_proposal(
        self,
        proposal: Dict[str, Any],
        state: Dict[str, Any],
        equity: float,
        universe: List[str],
        spread_pct: float,
    ) -> Optional[str]:
        if state.get("stopped_forever"):
            return "STOP_FOREVER_ACTIVE"

        daily = state["daily"]
        if daily.get("halted"):
            return "DAILY_HALT_ACTIVE"

        if daily.get("trades", 0) >= self.cfg.max_trades_per_day:
            return "MAX_TRADES_REACHED"

        action = proposal.get("action")
        if action == "NO_TRADE":
            return "NO_TRADE"
        if action != "TRADE":
            return "INVALID_ACTION"

        if proposal.get("order_type") != "LIMIT":
            return "ONLY_LIMIT_ALLOWED"

        symbol = proposal.get("symbol")
        if symbol not in universe:
            return "SYMBOL_NOT_IN_UNIVERSE"

        side = str(proposal.get("side", "")).upper()
        if side not in ("BUY", "SELL"):
            return "INVALID_SIDE"

        try:
            pos_pct = float(proposal.get("position_size_pct"))
            lp = float(proposal.get("limit_price"))
            tp = float(proposal.get("take_profit_price"))
        except Exception:
            return "NUMERIC_PARSE_ERROR"

        if pos_pct > self.cfg.max_position_pct:
            return "POSITION_SIZE_EXCEEDS_MAX"
        if pos_pct <= 0:
            return "POSITION_SIZE_NON_POSITIVE"
        if lp <= 0 or tp <= 0:
            return "PRICE_NON_POSITIVE"
        if equity <= 0:
            return "EQUITY_NON_POSITIVE"

        maker_fee_pct = (self.cfg.maker_fee_bps / 10000) * 2
        gross_edge = ((tp - lp) / lp) if side == "BUY" else ((lp - tp) / lp)
        if gross_edge < (spread_pct + maker_fee_pct):
            return "EDGE_BELOW_SPREAD_PLUS_FEES"

        return None

    def register_trade(self, state: Dict[str, Any]):
        state["daily"]["trades"] = int(state["daily"].get("trades", 0)) + 1


def load_json(path: Path, default: Any):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def append_jsonl(path: Path, obj: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
