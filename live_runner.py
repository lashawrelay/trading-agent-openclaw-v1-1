import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from broker import AlpacaBroker
from engine import EngineConfig, DeterministicEngine, append_jsonl, load_json, save_json
from llm_client import LLMClient
from market_data import AlpacaMarketData

BASE = Path(__file__).parent
CFG_PATH = BASE / "config.json"
PROMPT_PATH = BASE / "llm_prompt.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_cfg() -> Dict[str, Any]:
    if not CFG_PATH.exists():
        raise FileNotFoundError("config.json missing; copy config.example.json")
    return load_json(CFG_PATH, {})


def main():
    cfg = load_cfg()
    t = cfg["trading"]
    rt = cfg["runtime"]
    alp = cfg["alpaca"]
    llm_cfg = cfg["llm"]

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

    broker = AlpacaBroker(alp["api_key"], alp["api_secret"], alp["base_url"])
    md = AlpacaMarketData(alp["api_key"], alp["api_secret"], alp["data_url"])
    llm = LLMClient(llm_cfg["api_key"], llm_cfg["base_url"], llm_cfg["model"])

    state_path = BASE / rt["state_file"]
    log_path = BASE / rt["trade_log"]
    context_path = BASE / rt["context_file"]

    state = load_json(state_path, engine.init_state())
    account = broker.account()
    equity = float(account.get("equity") or account.get("cash") or t["start_equity"])

    weekly = engine.weekly_cutoff(state, equity)
    if weekly in ("WEEKLY_FLATTEN", "STOP_FOREVER_EQUITY_BELOW_START"):
        flatten_res = broker.close_all_positions()
        append_jsonl(log_path, {"ts": now_iso(), "event": weekly, "flatten": flatten_res, "equity": equity})
        save_json(state_path, state)
        print(json.dumps({"status": "STOP_FOREVER" if state.get("stopped_forever") else "WEEKLY_FLATTEN"}))
        return

    day_guard = engine.apply_daily_guard(state, equity)
    if day_guard == "HALT_DAY_DRAWDOWN":
        flatten_res = broker.close_all_positions()
        append_jsonl(log_path, {"ts": now_iso(), "event": day_guard, "flatten": flatten_res, "equity": equity})
        save_json(state_path, state)
        print(json.dumps({"status": "HALTED_FOR_DAY"}))
        return

    universe_objs = md.build_universe(t["candidate_symbols"], t["top_n"])
    universe = [x["symbol"] for x in universe_objs]
    if not universe:
        append_jsonl(log_path, {"ts": now_iso(), "event": "NO_UNIVERSE"})
        save_json(state_path, state)
        print(json.dumps({"status": "NO_UNIVERSE"}))
        return

    selected = universe[0]
    symbol_state = md.symbol_state(selected)
    daily_context = context_path.read_text(encoding="utf-8") if context_path.exists() else ""

    llm_input = {
        "timestamp_utc": now_iso(),
        "equity": equity,
        "universe": universe_objs,
        "selected_symbol_state": symbol_state,
        "recent_news_sentiment": "neutral",
        "daily_context": daily_context,
        "constraints": {
            "max_trades_day": t["max_trades_per_day"],
            "limit_only": True,
            "max_position_pct": t["max_position_pct"],
        },
    }

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    proposal = llm.propose(system_prompt, llm_input)
    rejection = engine.validate_proposal(proposal, state, equity, universe, float(symbol_state["spread_pct"]))

    event = {
        "ts": now_iso(),
        "equity": equity,
        "universe": universe,
        "symbol_state": symbol_state,
        "proposal": proposal,
        "validation": rejection,
        "paper_mode": bool(rt.get("paper_mode", True)),
    }

    if rejection is None:
        pos_pct = float(proposal["position_size_pct"]) / 100
        notional = equity * pos_pct
        qty = notional / float(proposal["limit_price"])
        if rt.get("paper_mode", True):
            order = {
                "paper": True,
                "symbol": proposal["symbol"],
                "side": proposal["side"],
                "qty": qty,
                "limit_price": proposal["limit_price"],
            }
        else:
            order = broker.submit_limit(proposal["symbol"], proposal["side"], qty, float(proposal["limit_price"]))
        engine.register_trade(state)
        event["order"] = order
        status = "ORDER_SUBMITTED"
    else:
        status = "NO_EXECUTION"

    append_jsonl(log_path, event)
    save_json(state_path, state)
    print(json.dumps({"status": status, "validation": rejection, "daily_trades": state['daily']['trades']}))


if __name__ == "__main__":
    main()
