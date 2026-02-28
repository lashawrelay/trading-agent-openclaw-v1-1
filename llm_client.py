import json
import re
from typing import Any, Dict

import requests


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in LLM output")
    return json.loads(m.group(0))


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def propose(self, system_prompt: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            "temperature": 0.1,
        }
        r = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=45)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return _extract_json(content)
