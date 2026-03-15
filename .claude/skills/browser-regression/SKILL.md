---
name: browser-regression
description: Run a browser-focused regression pass and summarize visible diffs, broken flows, and evidence.
allowed-tools: mcp__playwright__*, mcp__browser-use__*, Bash(playwright *), Bash(pytest *), Read
---

# Browser regression checklist

1. Identify the pages and user journeys affected by the current diff.
2. Reproduce them in the browser.
3. Capture screenshots or traces where useful.
4. Summarize:
   - visibly broken UI
   - console/runtime errors
   - flow regressions
   - confidence level and remaining unknowns
