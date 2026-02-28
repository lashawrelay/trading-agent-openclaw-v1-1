import json
import subprocess
from pathlib import Path
from urllib import parse, request

BASE = Path(__file__).parent
CFG = BASE / "config.json"
NOTIFY_STATE = BASE / "data/notify_state.json"


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def send_telegram(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = request.Request(url, data=data, method="POST")
    with request.urlopen(req, timeout=20) as r:
        r.read()


def main():
    cfg = load_json(CFG, {})
    rt = cfg.get("runtime", {})
    notify = rt.get("notify", {})

    proc = subprocess.run([str(BASE / ".venv/bin/python"), str(BASE / "live_runner.py")], capture_output=True, text=True)
    out = (proc.stdout or "").strip().splitlines()
    status_obj = {}
    if out:
        try:
            status_obj = json.loads(out[-1])
        except Exception:
            status_obj = {"status": "RUN_OUTPUT_PARSE_ERROR", "raw": out[-1]}

    important_statuses = {"ORDER_SUBMITTED", "HALTED_FOR_DAY", "STOP_FOREVER", "WEEKLY_FLATTEN"}
    status = status_obj.get("status")

    if proc.returncode != 0:
        status = "RUN_ERROR"

    if not notify.get("enabled"):
        print(json.dumps({"status": status or "UNKNOWN", "notified": False}))
        return

    should_notify = status in important_statuses or status == "RUN_ERROR"
    if not should_notify:
        print(json.dumps({"status": status or "UNKNOWN", "notified": False}))
        return

    token = notify.get("telegram_bot_token")
    chat_id = str(notify.get("telegram_chat_id", ""))
    if not token or not chat_id:
        print(json.dumps({"status": status, "notified": False, "reason": "missing telegram notify config"}))
        return

    # dedupe: avoid repeat notify for same latest event timestamp+status
    log_path = BASE / rt.get("trade_log", "data/trade_log.jsonl")
    last_event = None
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            try:
                last_event = json.loads(lines[-1])
            except Exception:
                last_event = None

    dedupe_key = f"{status}:{(last_event or {}).get('ts','no-ts')}"
    state = load_json(NOTIFY_STATE, {})
    if state.get("last_key") == dedupe_key:
        print(json.dumps({"status": status, "notified": False, "reason": "duplicate"}))
        return

    msg = f"[Trading Agent] {status}\n"
    if status_obj.get("validation"):
        msg += f"validation={status_obj['validation']}\n"
    if last_event and isinstance(last_event, dict):
        if "equity" in last_event:
            msg += f"equity={last_event['equity']}\n"
        p = last_event.get("proposal", {})
        if isinstance(p, dict) and p.get("action") == "TRADE":
            msg += f"{p.get('side')} {p.get('symbol')} @ {p.get('limit_price')}\n"

    send_telegram(token, chat_id, msg.strip())
    state["last_key"] = dedupe_key
    save_json(NOTIFY_STATE, state)
    print(json.dumps({"status": status, "notified": True}))


if __name__ == "__main__":
    main()
