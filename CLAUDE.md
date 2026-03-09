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
