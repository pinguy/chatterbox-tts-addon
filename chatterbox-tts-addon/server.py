#!/usr/bin/env python3
"""Check the local Chatterbox bridge used by the Firefox add-on.

The actual TTS services are managed by systemd:
  chatterbox-nano.service         (model, port 8020)
  openwebui-audio-bridge.service  (OpenAI-compatible API, port 8010)
"""

import json
import urllib.error
import urllib.request

HEALTH_URL = "http://127.0.0.1:8010/health"


def main() -> int:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"Chatterbox bridge unavailable: {exc}")
        print("Start it with: systemctl --user start openwebui-audio-bridge.service")
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
