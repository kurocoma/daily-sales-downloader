#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
tool = data.get("tool_name", "")
tool_input = data.get("tool_input", {}) or {}
project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
identity_path = project_dir / ".claude" / "project-identity.json"

def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }))
    sys.exit(0)

def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=project_dir, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""

identity = {}
if identity_path.exists():
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except Exception:
        identity = {}

if tool == "Bash":
    cmd = (tool_input.get("command") or "").strip()

    # Require correct GitHub identity for push/PR/merge operations.
    guarded_ops = [
        "git push",
        "gh pr create",
        "gh pr merge",
        "gh repo create",
        "git remote set-url",
    ]
    if any(cmd.startswith(prefix) for prefix in guarded_ops):
        expected_user = identity.get("expectedGhUser", "")
        expected_email = identity.get("expectedGitEmail", "")
        expected_remote_pattern = identity.get("expectedRemotePattern", "")

        active_gh = ""
        try:
            status_json = subprocess.check_output(
                ["gh", "auth", "status", "--active", "--json", "hosts"],
                cwd=project_dir,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            payload = json.loads(status_json)
            hosts = payload.get("hosts", {})
            github_host = hosts.get("github.com")
            if isinstance(github_host, dict):
                active_gh = github_host.get("user", "") or github_host.get("login", "")
            elif isinstance(github_host, list) and github_host:
                active_gh = github_host[0].get("user", "") or github_host[0].get("login", "")
        except Exception:
            active_gh = ""

        git_email = run(["git", "config", "user.email"])
        remote_url = run(["git", "remote", "get-url", "origin"])

        problems = []
        if expected_user and active_gh and active_gh != expected_user:
            problems.append(f"gh account mismatch: active={active_gh}, expected={expected_user}")
        if expected_email and git_email and git_email != expected_email:
            problems.append(f"git email mismatch: active={git_email}, expected={expected_email}")
        if expected_remote_pattern and remote_url and not re.search(expected_remote_pattern, remote_url):
            problems.append(f"remote mismatch: active={remote_url}, expected pattern={expected_remote_pattern}")

        if problems:
            deny("Project identity harness blocked this action. " + " | ".join(problems))

    # Optional extra project-level command bans.
    if re.search(r"(?i)\bterraform\s+apply\b", cmd):
        deny("Project harness blocked terraform apply. Run it manually after review.")

sys.exit(0)
