"""Simulate an inbound WhatsApp message through the real webhook (HMAC-signed).

Builds a Meta-shaped webhook payload and signs it with WHATSAPP_APP_SECRET from
.env the same way app/core/security.py:verify_hmac_meta expects, then POSTs it
to the running backend. Proves the whole pipeline: signature check -> message
router -> DB write (users/conversations) -> reply generation.

Usage:
    .venv/Scripts/python.exe .claude/skills/run-cienanet-bot/simulate_whatsapp_message.py ["texto"] [wa_id] [backend_url]

Defaults: text="hola" (hits the deterministic greeting branch, no AI call),
wa_id="15550001234" (obviously-fake test number - never a real fisherman's,
per CLAUDE.md's rule against logging real phone numbers).
"""

import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_env(path: Path, key: str) -> str:
    """Last-value-wins, matching python-dotenv/pydantic-settings' own parsing."""
    if not path.exists():
        return ""
    value = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            value = line.split("=", 1)[1]
    return value


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "hola"
    wa_id = sys.argv[2] if len(sys.argv) > 2 else "15550001234"
    backend_url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"

    app_secret = _read_env(REPO_ROOT / ".env", "WHATSAPP_APP_SECRET")

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": wa_id, "profile": {"name": "Smoke Test"}}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": "wamid.smoketest",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()

    req = urllib.request.Request(
        f"{backend_url}/api/v1/webhook/whatsapp",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(resp.status, resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.code, exc.read().decode())


if __name__ == "__main__":
    main()
