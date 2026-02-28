# OpenClaw Runner Wiring (v1.1)

## 1) Prepare env
```bash
cd /home/lashaws/.openclaw/workspace/trading_agent_openclaw_v1_1
python3 -m venv .venv
source .venv/bin/activate
pip install requests python-dateutil
cp config.example.json config.json
```

## 2) Live cycle command
```bash
cd /home/lashaws/.openclaw/workspace/trading_agent_openclaw_v1_1 && ./.venv/bin/python live_runner.py
```

## 3) Daily critique command (23:55 UTC)
```bash
cd /home/lashaws/.openclaw/workspace/trading_agent_openclaw_v1_1 && ./.venv/bin/python daily_critique.py
```

## 4) Suggested cron (UTC)
```cron
* * * * * cd /home/lashaws/.openclaw/workspace/trading_agent_openclaw_v1_1 && ./.venv/bin/python live_runner.py >> logs/live.log 2>&1
55 23 * * * cd /home/lashaws/.openclaw/workspace/trading_agent_openclaw_v1_1 && ./.venv/bin/python daily_critique.py >> logs/critique.log 2>&1
```

## 5) Safety defaults
- `paper_mode=true` by default.
- Keep paper mode until logs show stable behavior.
- Flip to live only after validation.
