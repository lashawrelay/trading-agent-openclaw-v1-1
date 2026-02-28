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

## Run with notifications wrapper
```bash
./.venv/bin/python run_and_notify.py
```
Sends Telegram only for important events (`ORDER_SUBMITTED`, `HALTED_FOR_DAY`, `WEEKLY_FLATTEN`, `STOP_FOREVER`, run errors).

## Security watchdog
Moved to separate repo: `https://github.com/lashawrelay/security-watchdog-openclaw`

## External skill mode (no LLM key in app)
Default config uses `llm.mode=external_skill`.

One-command flow (enabled by default):
1. `live_runner.py` writes `input_snapshot.json`.
2. It runs `runtime.proposal_command` to generate `proposal.json`.
3. It validates and executes/paper-executes in the same run.

Default proposal generator:
- `skills/trading-proposal-json/generate_proposal.py`

You can replace `proposal_command` with your own OpenClaw task/skill command later.

## Run daily critique (23:55 UTC)
```bash
./.venv/bin/python daily_critique.py
```

## Important
Start and validate in paper mode first (`runtime.paper_mode=true`).
