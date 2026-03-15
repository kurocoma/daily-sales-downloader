#!/usr/bin/env python3
import datetime
import json
import os
import sys
from pathlib import Path

data = json.load(sys.stdin)
root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude" / "audit"
root.mkdir(parents=True, exist_ok=True)
logfile = root / "tool-audit.jsonl"

entry = {
    "ts": datetime.datetime.utcnow().isoformat() + "Z",
    "hook_event": data.get("hook_event_name"),
    "tool_name": data.get("tool_name"),
    "permission_mode": data.get("permission_mode"),
    "cwd": data.get("cwd"),
    "tool_input": data.get("tool_input"),
}
with logfile.open("a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
