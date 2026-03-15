---
name: web-automation-stack
description: Choose the best browser automation path for the current task: Playwright code, Playwright MCP, Browser Use, or Next.js MCP.
allowed-tools: mcp__playwright__*, mcp__browser-use__*, mcp__next-devtools__*, Read, Grep
---

# Browser automation routing guide

Choose the stack based on the goal:

- Use **Playwright code/tests** when the result must live in the repository or CI.
- Use **Playwright MCP** when you need fast interactive browser inspection, screenshots, or local reproduction.
- Use **Browser Use MCP** when the task is open-ended, natural-language heavy, or benefits from cloud browser features.
- Use **Next.js MCP** when diagnosing a running Next.js 16+ dev server, especially for live errors, logs, and route metadata.

When you choose one path, explain why in one short paragraph before proceeding.
