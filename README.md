# OpenClaw-native LLM Trading Agent v1.1

This package now includes a full live runner:
- Pulls account + market data from Alpaca crypto endpoints
- Builds dynamic top-N universe (volume + spread)
- Computes technical state (ATR, RSI, SMA20/50)
- Gets proposal via either:
  - direct LLM API, or
  - OpenClaw skill mode (`llm.mode=external_skill`) without storing an LLM key in this app
- Runs deterministic validation gates
- Submits LIMIT order (or paper-simulates when `paper_mode=true`)

## Implemented hard rules
- Weekly cutoff: Sunday 00:00 UTC flatten all; if equity < 100 => STOP_FOREVER
- Daily drawdown halt: 10% from UTC day start => flatten + halt until next UTC day
- Max trades/day: 5
- LIMIT only
- Position cap: <=30%
- Symbol must be in top-4 universe
- Fee hurdle: edge >= spread + 2*maker_fee

## Files
- `live_runner.py` - end-to-end live cycle runner
- `engine.py` - deterministic guard/validator
- `market_data.py` - universe and indicators
- `broker.py` - Alpaca account/order/flatten operations
- `llm_client.py` - strict JSON LLM call
- `daily_critique.py` - writes `context.txt` daily review payload
- `llm_prompt.md` - strict output contract for model
- `config.example.json`
- `openclaw_runner.md` - run + cron wiring

## Quick start
```bash
cd trading_agent_openclaw_v1_1
python3 -m venv .venv
source .venv/bin/activate
pip install requests python-dateutil
cp config.example.json config.json
```

Edit `config.json` with your Alpaca + LLM keys.

## Run one live cycle
```bash
./.venv/bin/python live_runner.py
```

## External skill mode (no LLM key in app)
Default config uses `llm.mode=external_skill`.

Flow:
1. Run `live_runner.py` once; it writes `input_snapshot.json` and exits if `proposal.json` is missing.
2. Use OpenClaw + skill `skills/trading-proposal-json` to generate strict proposal JSON into `proposal.json`.
3. Run `live_runner.py` again to validate and execute/paper-execute.

## Run daily critique (23:55 UTC)
```bash
./.venv/bin/python daily_critique.py
```

## Important
Start and validate in paper mode first (`runtime.paper_mode=true`).
