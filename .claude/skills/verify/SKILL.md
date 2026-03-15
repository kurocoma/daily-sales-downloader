---
name: verify
description: Run project verification with uv/pytest/Playwright for Python projects, and package-manager checks for Next.js projects when present.
allowed-tools: Bash(uv *), Bash(pytest *), Bash(python *), Bash(playwright *), Bash(node *), Bash(npm *), Bash(pnpm *), Bash(yarn *), Bash(bun *), Bash(cat *), Bash(ls *), Bash(find *), Bash(git diff *), Read, Grep
---

# Verification protocol

1. Detect the project type before running commands:
   - If `pyproject.toml` exists, treat it as a Python/uv project.
   - If `package.json` exists, also inspect available scripts and lockfiles (`pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `bun.lockb`) for web verification.

2. Python / uv flow:
   - Run `uv sync --all-groups` when `pyproject.toml` exists.
   - If Ruff is configured, run `uv run ruff check .`.
   - Run `uv run pytest -q`.
   - If Playwright Python tests exist, also run the most appropriate browser suite:
     - prefer `uv run pytest -m smoke`
     - otherwise `uv run pytest -m e2e`
     - otherwise the Playwright-specific test path if one clearly exists.

3. Next.js / Node flow:
   - Pick the package manager from the lockfile.
   - If scripts exist, prefer this order:
     - `lint`
     - `typecheck`
     - `test`
     - `test:e2e` or `e2e`
   - If the project uses Next.js 16+, mention whether `next-devtools` MCP is available and whether the dev server should be started for deeper diagnosis.

4. Report output in four bullets:
   - commands run
   - pass/fail summary
   - browser evidence generated (screenshots/traces)
   - exact follow-up fix needed, if any

5. Do not create a PR from this skill.
