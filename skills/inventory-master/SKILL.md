---
name: inventory-master
description: >
  Unified asset inventory and fleet management — track machines, drives, devices, venues, and networks.
  Use when the user asks about hardware, storage, drives, backup status, fleet health, what machines exist,
  where data lives, or needs to scan/inventory assets.
  Also triggers on: "inventory", "fleet", "device", "drive", "backup", "storage", "health check", "what machines".
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Inventory Master

Unified asset inventory for Claude Code. Every tracked thing is an **asset** with a `type` field. The "Where" in the Five Ws framework.

## Philosophy

- **Unified model**: One entity type, `type` field distinguishes. No separate schemas per category.
- **Discovery-first**: Scan before manual entry. Fleet-scanner is the primary onboarding flow.
- **Relationship-aware**: Typed links between assets enable impact analysis.
- **Health-scored**: Composite metric (0-100), not just status strings.

## Directory Structure

```
~/.claude/local/inventory/
├── config.yml
├── assets/
│   ├── machines/     # desktops, laptops, servers, VMs
│   ├── drives/       # SSDs, HDDs, NVMe, external
│   ├── mobile/       # phones, tablets
│   ├── network/      # routers, mesh nodes, tailscale
│   ├── venues/       # galleries, studios, offices
│   └── services/     # self-hosted services
├── deep/             # Verbose analysis files
└── topology/
    └── network-map.md
```

## Asset Frontmatter Schema

Universal fields (all types):

```yaml
---
id: {slug}
name: "{display name}"
type: machine|drive|mobile|network|venue|service
subtype: "{type-specific}"
status: pending|inventoried|assessed|active|stored|retired|wiped
location: "{where}"
last_seen: YYYY-MM-DD
contains_data: true|false
data_status: active|needs-inventory|archived|null
backup_status: none|partial|backed-up|mirrored
priority: critical|important|optional
manufacturer: "{mfg}"
model: "{model}"
serial: null
tags: []
notes: ""
relationships:
  contains: []
  depends_on: []
  associated_with: []
  replaces: []
  composed_of: []
ventures: []
outgoing_links: []
---
```

## Type-Specific Fields

- **machine**: hostname, os, kernel, role, cpu, ram, gpu, drives, network (ip_local, ip_tailscale, ssh_host), services
- **drive**: device, uuid, filesystem, capacity, used, mount_point, compression, machine, consolidation_phase
- **mobile**: os, carrier, storage, imei
- **network**: network_type, provider, nodes, bandwidth
- **venue**: address, venue_type, contact, capacity, equipment, events
- **service**: service_type, port, machine, container, systemd_unit

## Status Lifecycle

`pending` → `inventoried` → `assessed` → `active` → `stored` → `retired` → `wiped`

## Health Score

Composite 0-100 per asset:
- **Backup (40%)**: none=0, partial=50, backed-up=80, mirrored=100. Only for `contains_data: true`.
- **Freshness (30%)**: 0-7d=100, 8-14d=80, 15-30d=50, 31-60d=20, 60d+=0
- **Capacity (20%)**: Drives only. 0-70%=100, 71-80%=70, 81-90%=40, 91-95%=10, 96-100%=0. Non-drives=100.
- **Connectivity (10%)**: Machines only. Tailscale=100, LAN=70, none=0. Non-machines=100.

Fleet health = weighted average of all active asset scores.

## Typed Relationships

- `contains` — machine contains drives, venue contains equipment
- `depends_on` — service depends on machine
- `associated_with` — venue linked to venture, device to project
- `replaces` — new device replaces old one
- `composed_of` — logical grouping (mesh network composed of nodes)

Enable impact analysis: "if X fails, what's affected?" → traverse `depends_on` and `contains`.

## Subskills

### @asset-writer
**Trigger**: Creating or updating assets. "Add this machine", "update drive info", "new device".
Creates asset files with type-appropriate templates. Auto-populates from scan data when available.

### @asset-browser
**Trigger**: Browsing, searching assets. "Show machines", "list drives", "find unbacked", "stats".
Query patterns: `browse all`, `browse machines`, `browse drives`, `browse unbacked`, `browse venture:X`, `search keyword`, `stats`.

### @fleet-scanner
**Trigger**: "Scan", "discover", "what hardware do I have", "inventory this machine".
Primary onboarding flow. Auto-detects local machine specs, drives, network, services. Generates scripts for sudo operations.

### @health-monitor
**Trigger**: "Health", "backup status", "what's at risk", "fleet health", "capacity".
Backup gaps, stale assets, capacity warnings, venture risk, composite health score.

### @consolidation
**Trigger**: "Consolidation", "migration", "wipe status", "data consolidation".
Phase tracking, rsync command generation, backup verification, wipe readiness.

## Routing

- Default (no args): Show fleet overview — machines + drives summary with health scores
- Scan context detected → @fleet-scanner
- Health/backup context → @health-monitor
- Browse/search/list context → @asset-browser
- Create/update context → @asset-writer
- Migration/wipe context → @consolidation

## Config

`~/.claude/local/inventory/config.yml` — health thresholds, integration paths, scan settings.
