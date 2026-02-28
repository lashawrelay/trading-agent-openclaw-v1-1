import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
CFG_PATH = BASE / "config.json"


def utc_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    cfg = load_json(CFG_PATH, {})
    trade_log = BASE / cfg["runtime"]["trade_log"]
    context_file = BASE / cfg["runtime"]["context_file"]

    if not trade_log.exists():
        context_file.write_text("No trades/events logged today.", encoding="utf-8")
        print("No logs")
        return

    today = utc_date_str()
    rows = []
    with open(trade_log, "r", encoding="utf-8") as f:
        for line in f:
            x = json.loads(line)
            if str(x.get("ts", "")).startswith(today):
                rows.append(x)

    approved = [r for r in rows if r.get("validation") is None]
    rejected = [r for r in rows if r.get("validation") not in (None, "NO_TRADE")]
    no_trade = [r for r in rows if r.get("validation") == "NO_TRADE"]

    text = [
        f"Date: {today}",
        f"Total events: {len(rows)}",
        f"Approved trades: {len(approved)}",
        f"Rejected proposals: {len(rejected)}",
        f"No-trade decisions: {len(no_trade)}",
        "",
        "Prompt to LLM:",
        "Review today's trades. Identify what worked and what failed based on the regime.",
        "",
        "Compact trade events JSON follows:",
        json.dumps(rows[-30:], indent=2),
    ]

    context_file.write_text("\n".join(text), encoding="utf-8")
    print(f"Wrote {context_file}")


if __name__ == "__main__":
    main()
