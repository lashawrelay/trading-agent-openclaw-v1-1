import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from engine import (
    EngineConfig,
    DeterministicEngine,
    append_jsonl,
    load_json,
    save_json,
)

BASE = Path(__file__).parent
CFG_PATH = BASE / "config.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_cfg() -> Dict[str, Any]:
    if not CFG_PATH.exists():
        raise FileNotFoundError("config.json missing; copy config.example.json")
    return load_json(CFG_PATH, {})


def load_input_snapshot(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"snapshot missing: {path}")
    return load_json(path, {})


def main():
    cfg = load_cfg()
    rt = cfg["runtime"]
    t = cfg["trading"]

    engine = DeterministicEngine(
        EngineConfig(
            start_equity=t["start_equity"],
            daily_max_drawdown_pct=t["daily_max_drawdown_pct"],
            max_trades_per_day=t["max_trades_per_day"],
            max_position_pct=t["max_position_pct"],
            top_n=t["top_n"],
            maker_fee_bps=t["maker_fee_bps"],
        )
    )

    state_path = BASE / rt["state_file"]
    trade_log = BASE / rt["trade_log"]

    state = load_json(state_path, engine.init_state())

    # OpenClaw agent should produce this file each cycle after collecting tool data.
    snapshot_path = Path(os.getenv("SNAPSHOT_PATH", str(BASE / "input_snapshot.json")))
    snap = load_input_snapshot(snapshot_path)

    equity = float(snap["account"]["equity"])
    universe = snap["universe"]  # list of symbols
    spread_pct = float(snap["selected_symbol_state"]["spread_pct"])

    weekly = engine.weekly_cutoff(state, equity)
    if weekly == "STOP_FOREVER_EQUITY_BELOW_START":
        append_jsonl(trade_log, {"ts": now_iso(), "event": weekly, "equity": equity})
        save_json(state_path, state)
        print(json.dumps({"status": "STOP_FOREVER", "reason": weekly}))
        return

    day_guard = engine.apply_daily_guard(state, equity)
    if day_guard == "HALT_DAY_DRAWDOWN":
        append_jsonl(trade_log, {"ts": now_iso(), "event": day_guard, "equity": equity})
        save_json(state_path, state)
        print(json.dumps({"status": "HALTED_FOR_DAY", "reason": day_guard}))
        return

    proposal = snap["llm_proposal"]
    rejection = engine.validate_proposal(proposal, state, equity, universe, spread_pct)

    event = {
        "ts": now_iso(),
        "equity": equity,
        "proposal": proposal,
        "validation": rejection,
        "paper_mode": bool(rt.get("paper_mode", True)),
    }

    if rejection is None:
        engine.register_trade(state)
        # In OpenClaw-native flow, order execution is done by the agent via integration tools.
        event["execution_intent"] = {
            "action": "SUBMIT_LIMIT",
            "symbol": proposal["symbol"],
            "side": proposal["side"],
            "position_size_pct": proposal["position_size_pct"],
            "limit_price": proposal["limit_price"],
            "stop_loss_price": proposal["stop_loss_price"],
            "take_profit_price": proposal["take_profit_price"],
        }
        status = "APPROVED_FOR_EXECUTION"
    else:
        status = "REJECTED"

    append_jsonl(trade_log, event)
    save_json(state_path, state)

    print(json.dumps({"status": status, "validation": rejection, "daily_trades": state["daily"]["trades"]}))


if __name__ == "__main__":
    main()
