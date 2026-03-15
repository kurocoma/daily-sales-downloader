# Project Rules

## Identity
- This repository should declare its expected GitHub identity in `.claude/project-identity.json`.
- Before any push, PR creation, or merge action, the harness must verify the active `gh` account, `git user.email`, and git remote against that file.

## Verification
- Use `/verify` as the default verification entry point.
- If this is a Python project, prefer `uv` + `pytest` + Playwright Python flows.
- If this is a Next.js project, read `AGENTS.md` first, then use the Next.js MCP and Playwright-based verification paths.

## MCP
- This repo expects project-scoped MCP configuration in `.mcp.json`.
- Approved MCP servers for this template: `playwright`, `browser-use`, and `next-devtools`.
