import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

BASE = Path(__file__).parent
CFG_PATH = BASE / "watchdog_config.json"
STATE_PATH = BASE / "data/watchdog_state.json"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def run(cmd):
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def send_telegram(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = request.Request(url, data=data, method="POST")
    with request.urlopen(req, timeout=20) as r:
        r.read()


def check_tailscale(cfg):
    out = {}
    rc, stdout, stderr = run("tailscale funnel status")
    out["funnel_cmd_ok"] = rc == 0
    out["funnel_raw"] = stdout or stderr
    out["funnel_exposed"] = bool(re.search(r"https?://", stdout or ""))

    rc2, stdout2, stderr2 = run("tailscale serve status")
    out["serve_cmd_ok"] = rc2 == 0
    out["serve_raw"] = stdout2 or stderr2

    allowed = set(cfg.get("tailscale", {}).get("allowed_public_paths", []))
    exposed_paths = set(re.findall(r"/[^\s]*", stdout or ""))
    out["unexpected_public_paths"] = sorted(list(exposed_paths - allowed))
    return out


def check_ssh(cfg):
    path = cfg.get("ssh", {}).get("config_path", "/etc/ssh/sshd_config")
    out = {"config_path": path, "exists": False}
    p = Path(path)
    if not p.exists():
        return out
    text = p.read_text(encoding="utf-8", errors="ignore")
    out["exists"] = True

    def has_value(key, value):
        rx = re.compile(rf"^\s*{re.escape(key)}\s+{re.escape(value)}\b", re.IGNORECASE | re.MULTILINE)
        return bool(rx.search(text))

    out["password_auth_disabled"] = has_value("PasswordAuthentication", "no")
    out["root_login_disabled"] = has_value("PermitRootLogin", "no")
    return out


def check_firewall(cfg):
    out = {}
    rc, stdout, stderr = run("ufw status verbose")
    if rc == 0:
        out["ufw_present"] = True
        out["ufw_raw"] = stdout
        out["ufw_active"] = "Status: active" in stdout
        out["ufw_default_deny_incoming"] = "Default: deny (incoming)" in stdout
    else:
        out["ufw_present"] = False
        out["ufw_raw"] = stderr or stdout
    return out


def check_openclaw(cfg):
    out = {}
    oc_path = Path(cfg.get("openclaw", {}).get("config_path", "/home/lashaws/.openclaw/openclaw.json"))
    out["openclaw_config_exists"] = oc_path.exists()
    if oc_path.exists():
        data = json.loads(oc_path.read_text(encoding="utf-8"))
        hooks = data.get("hooks", {})
        out["gmail_funnel_enabled"] = ("gmail" in hooks) or ("gmail" in hooks.get("presets", []))

    # security audit is optional if CLI available
    cmd = cfg.get("openclaw", {}).get("security_audit_cmd", "")
    if cmd:
        rc, stdout, stderr = run(cmd)
        out["security_audit_ok"] = rc == 0
        out["security_audit_excerpt"] = (stdout or stderr)[-600:]
    return out


def check_ports(cfg):
    rc, stdout, stderr = run("ss -ltn")
    out = {"ss_ok": rc == 0, "listening": []}
    if rc != 0:
        out["error"] = stderr or stdout
        return out
    ports = sorted(set(re.findall(r":(\d+)\s", stdout)))
    out["listening"] = ports
    allowed = set(str(p) for p in cfg.get("ports", {}).get("allowed_listening", []))
    out["unexpected_ports"] = [p for p in ports if p not in allowed]
    return out


def evaluate(findings, cfg):
    issues = []

    t = findings["tailscale"]
    if t.get("funnel_exposed") and not cfg.get("tailscale", {}).get("allow_funnel", False):
        issues.append("Tailscale Funnel is publicly exposed")
    if t.get("unexpected_public_paths"):
        issues.append(f"Unexpected public tailscale paths: {t['unexpected_public_paths']}")

    s = findings["ssh"]
    if s.get("exists"):
        if not s.get("password_auth_disabled", False):
            issues.append("SSH password authentication is not disabled")
        if not s.get("root_login_disabled", False):
            issues.append("SSH root login is not disabled")

    f = findings["firewall"]
    if f.get("ufw_present"):
        if not f.get("ufw_active", False):
            issues.append("UFW is not active")
        if not f.get("ufw_default_deny_incoming", False):
            issues.append("UFW default incoming policy is not deny")

    o = findings["openclaw"]
    if o.get("gmail_funnel_enabled"):
        issues.append("OpenClaw Gmail funnel appears enabled")

    p = findings["ports"]
    if p.get("unexpected_ports"):
        issues.append(f"Unexpected listening ports: {p['unexpected_ports']}")

    return issues


def main():
    cfg = load_json(CFG_PATH, {})
    if not cfg:
        raise SystemExit("watchdog_config.json missing; copy watchdog_config.example.json")

    findings = {
        "ts": now_iso(),
        "tailscale": check_tailscale(cfg),
        "ssh": check_ssh(cfg),
        "firewall": check_firewall(cfg),
        "openclaw": check_openclaw(cfg),
        "ports": check_ports(cfg),
    }
    issues = evaluate(findings, cfg)
    findings["issues"] = issues

    prev = load_json(STATE_PATH, {})
    prev_key = prev.get("issues_key")
    issues_key = "|".join(sorted(issues)) if issues else "OK"

    notify = cfg.get("notify", {})
    should_notify = issues_key != prev_key and notify.get("enabled", False)

    if should_notify:
        token = notify.get("telegram_bot_token")
        chat_id = str(notify.get("telegram_chat_id", ""))
        if token and chat_id:
            if issues:
                msg = "[Security Watchdog] ALERT\n" + "\n".join(f"- {x}" for x in issues)
            else:
                msg = "[Security Watchdog] OK: posture recovered"
            send_telegram(token, chat_id, msg)

    state = {
        "checked_at": findings["ts"],
        "issues_key": issues_key,
        "issues": issues,
        "findings": findings,
    }
    save_json(STATE_PATH, state)

    print(json.dumps({"checked_at": findings["ts"], "issues": issues, "notified": bool(should_notify)}))


if __name__ == "__main__":
    main()
