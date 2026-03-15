---
name: nextjs-app-router
description: Work on a Next.js App Router project using version-matched bundled docs and, when available, next-devtools MCP.
allowed-tools: Bash(cat *), Bash(ls *), Bash(find *), Read, Grep, mcp__next-devtools__*
---

# Next.js App Router workflow

1. Read `AGENTS.md` first.
2. Before coding, read the relevant bundled docs in `node_modules/next/dist/docs/`.
3. If `next-devtools` MCP is available and the dev server is running, use it for:
   - current errors
   - logs
   - page metadata
   - project metadata
4. Prefer App Router conventions already present in the repo.
5. When explaining a change, cite whether it came from bundled docs or live MCP context.
