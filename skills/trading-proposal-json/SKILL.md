---
name: trading-proposal-json
description: Generate strict trading proposal JSON from input_snapshot.json for the OpenClaw-native trading agent. Use when live_runner.py is configured with llm.mode=external_skill and requires proposal.json before execution.
---

# Trading Proposal JSON

Read `../input_snapshot.json`.

Return one strict JSON object only (no markdown) with keys:
- action
- symbol
- side
- order_type
- position_size_pct
- limit_price
- stop_loss_price
- take_profit_price
- rationale
- confidence_score

Rules:
- Use `order_type: LIMIT` only.
- Use only symbols present in `llm_input.universe`.
- Keep `position_size_pct <= 30`.
- If edge/clarity is weak, return `action: NO_TRADE` and safe placeholder prices.

After generating JSON, write it to `../proposal.json`.
