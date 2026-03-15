---
name: playwright-python
description: Use Playwright from a Python/uv project for browser verification, login flows, screenshots, and E2E support.
allowed-tools: Bash(uv *), Bash(pytest *), Bash(playwright *), Bash(python *), Read, Grep
---

# Playwright Python workflow

- Prefer `pytest-playwright` patterns when the repository already uses Python tests.
- First ensure dependencies are present:
  - `uv sync --all-groups`
  - if browsers are missing, use Playwright install commands appropriate to the repo.
- For verification work:
  - reproduce the flow
  - capture screenshot/trace when useful
  - summarize selectors, waits, retries, and flake risks
- For login-heavy or scraping-style browser flows:
  - prefer deterministic selectors
  - keep credentials outside source-controlled files
  - note any rate-limit or TOS concerns before automating
