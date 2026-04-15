# claude-inventory

Unified asset inventory — the "Where" in the Five Ws framework.

## Quick Start
- `/inventory` — fleet overview (machines + drives)
- `/inventory scan` — scan local machine, auto-detect hardware
- `/inventory health` — health assessment with scoring
- `/asset "name" --type machine` — create asset manually

## Data Location
Assets: `~/.claude/local/inventory/assets/{type}/{slug}.md`
Config: `~/.claude/local/inventory/config.yml`

## Asset Types
machine | drive | mobile | network | venue | service

## Status Lifecycle
pending → inventoried → assessed → active → stored → retired → wiped

## The Five Ws
- **What** → ventures (strategic container)
- **How** → backlog tasks (tactical steps)
- **Why** → journal (reflections, decisions)
- **When** → temporal (deadlines, timestamps)
- **Where** → **inventory** (machines, drives, venues, networks)
- **Who** → co-venturers, assignees

## Typed Relationships
Assets link to each other via typed relationships:
- `contains` — machine contains drives
- `depends_on` — service depends on machine
- `associated_with` — venue linked to venture
- `replaces` — new device replaces old one
- `composed_of` — logical grouping

## Health Score
Composite 0-100 score: backup coverage (40%) + freshness (30%) + capacity headroom (20%) + connectivity (10%).

## Data Schema

No SQLite. File-based only.

### File Layout

```
~/.claude/local/inventory/
├── config.yml
└── assets/
    ├── machines/*.md
    ├── drives/*.md
    ├── mobile/*.md
    ├── network/*.md
    ├── printers/*.md
    ├── services/*.md
    └── venues/*.md
```

### Frontmatter Contract

```yaml
---
id: mothership                        # required, slug
name: "Pop!_OS Mothership"            # required
type: machine                         # required (machine|drive|mobile|network|printer|service|venue)
subtype: desktop                      # optional
status: active                        # required (pending|inventoried|assessed|active|stored|retired|wiped)
location: home                        # optional
last_seen: 2026-02-25                 # optional, date
contains_data: true                   # optional, boolean
data_status: inventoried              # optional
backup_status: partial                # optional (none|partial|full)
backup_date: null                     # optional, date
backup_target: null                   # optional, path/slug
next_step: "Install Pop!_OS Cosmic"   # optional
priority: critical                    # optional
manufacturer: "Custom"               # optional
model: "Custom Build"                 # optional
serial: null                          # optional
tags: [mothership, server]            # optional
notes: "..."                          # optional
relationships:                        # optional
  contains: [drive-slug]
  depends_on: [device-slug]
  associated_with: []
  replaces: []
  composed_of: []
ventures: []                          # optional
hostname: "pop-os"                    # optional, machine-specific
---
```

### Canonical Count

The SessionStart hook (`fleet-pulse.py`) counts:

```python
for type_dir in ASSETS_ROOT.iterdir():
    for f in type_dir.glob("*.md"):
        fm = parse_frontmatter(f)
        if fm.get("status") in ("retired", "wiped"):
            continue
        asset_count += 1
```

Assets with `status: retired` or `status: wiped` are excluded from the active count and health score.
