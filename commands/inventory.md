---
description: "View and manage the asset inventory"
argument-hint: "[scan | health | browse <query> | stats | consolidation]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill]
---

# /inventory

Fleet overview and management command.

## Routing

Parse the argument to determine which subskill to invoke:

- **No args** → Show fleet overview: read all assets from `~/.claude/local/inventory/assets/`, group by type, show health scores. Use @asset-browser in overview mode.
- **`scan`** → Invoke @fleet-scanner to scan local machine, auto-detect hardware and drives.
- **`health`** → Invoke @health-monitor for full health report with scores, backup gaps, and venture risk.
- **`browse <query>`** → Invoke @asset-browser with the query. Examples: `browse machines`, `browse unbacked`, `browse venture:salish-sea-dreaming`.
- **`stats`** → Invoke @asset-browser in stats mode — counts by type/status, backup coverage, capacity overview.
- **`consolidation`** → Invoke @consolidation for migration dashboard and phase tracking.

## Data Location

- Assets: `~/.claude/local/inventory/assets/{type}/*.md`
- Config: `~/.claude/local/inventory/config.yml`

## Examples

- `/inventory` — quick fleet overview
- `/inventory scan` — scan this machine
- `/inventory health` — full health report
- `/inventory browse drives` — list all drives
- `/inventory browse unbacked` — find assets missing backups
- `/inventory stats` — fleet statistics
- `/inventory consolidation` — migration progress
