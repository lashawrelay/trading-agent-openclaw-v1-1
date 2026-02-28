import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SNAPSHOT = BASE / "input_snapshot.json"
PROPOSAL = BASE / "proposal.json"


def main():
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    llm_input = data.get("llm_input", {})
    universe = llm_input.get("universe", [])
    if not universe:
        raise RuntimeError("No universe in input_snapshot.json")

    best = universe[0]["symbol"] if isinstance(universe[0], dict) else universe[0]
    s = llm_input.get("selected_symbol_state", {})
    mid = float(s.get("price_mid") or 0)
    spread = float(s.get("spread_pct") or 0)
    rsi = s.get("rsi_1m")

    # Simple safe default policy for local verification:
    # - prefer NO_TRADE unless there is a clear mean-reversion signal.
    action = "NO_TRADE"
    side = "BUY"
    pos_pct = 10

    if isinstance(rsi, (int, float)) and rsi < 35 and mid > 0:
        action = "TRADE"
        side = "BUY"
        pos_pct = 20

    # Price template keeps edge above basic fee+spread hurdle for test runs.
    limit_price = mid if mid > 0 else 1.0
    stop_loss = limit_price * 0.992
    take_profit = limit_price * (1.012 + spread)

    proposal = {
        "action": action,
        "symbol": best,
        "side": side,
        "order_type": "LIMIT",
        "position_size_pct": pos_pct,
        "limit_price": round(limit_price, 6),
        "stop_loss_price": round(stop_loss, 6),
        "take_profit_price": round(take_profit, 6),
        "rationale": {
            "technical_summary": "Auto-generated proposal task (skill mode).",
            "sentiment": "neutral",
            "regime_identified": "mean_reversion" if action == "TRADE" else "range",
            "fee_hurdle_cleared": True if action == "TRADE" else False,
        },
        "confidence_score": 60 if action == "TRADE" else 35,
    }

    PROPOSAL.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    print(f"Wrote {PROPOSAL}")


if __name__ == "__main__":
    main()
