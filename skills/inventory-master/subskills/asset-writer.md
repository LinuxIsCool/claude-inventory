# Asset Writer — Create & Update Assets

Subskill of `inventory-master`. Handles creating new asset files and updating existing ones from templates or scan data.

## Slug Generation

Generate slugs: lowercase, hyphens only, max 40 characters.
Strip special characters, collapse whitespace to hyphens, trim trailing hyphens.

Examples: `legion`, `24tb-expansion`, `pixel-7-pro`, `telus-router`, `home-office`.

## Type Templates

Every asset gets universal fields plus type-specific fields. Store assets at:
`~/.claude/local/inventory/assets/{type}/{slug}.md`

### Machine (full template)

```yaml
---
id: {slug}
name: "{name}"
type: machine
subtype: {desktop|laptop|server|vm}
status: active
location: home
last_seen: {today}
contains_data: true
data_status: needs-inventory
backup_status: none
priority: {critical|important|optional}
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
hostname: "{hostname}"
os: "{os}"
kernel: "{kernel}"
role: {primary|secondary|dev|server|storage}
cpu: "{cpu}"
ram: "{ram}"
gpu: "{gpu}"
drives: []
network:
  ip_local: ""
  ip_tailscale: ""
  ssh_host: ""
services: []
---
```

### Drive

Type-specific fields: `device`, `uuid`, `filesystem`, `capacity`, `used`, `mount_point`, `compression`, `machine` (slug ref), `consolidation_phase`.

### Mobile

Type-specific fields: `os`, `carrier`, `storage`.

### Venue

Type-specific fields: `address`, `venue_type`, `contact`, `capacity`, `equipment`, `events`.

### Network

Type-specific fields: `network_type`, `provider`, `nodes` (list of slug refs), `bandwidth`.

### Service

Type-specific fields: `service_type`, `port`, `machine` (slug ref), `container`, `systemd_unit`.

All abbreviated templates inherit the universal fields block (id through outgoing_links) shown in the machine template. Only the type-specific section differs.

## Auto-populate from Scan Data

When `fleet-scanner` has collected data for this machine or drive, read from:
`~/.claude/local/inventory/scans/{hostname}-latest.json`

Map scan fields to template fields automatically. Prefer scan data over defaults, but never overwrite user-edited values on update.

## Workflow

1. **Determine type** — use `--type` flag if provided, otherwise infer or ask
2. **Generate slug** — from the asset name, following slug rules above
3. **Check existence** — look for `~/.claude/local/inventory/assets/{type}/{slug}.md`
   - If exists: load current frontmatter, merge updates, preserve user edits
   - If new: start from blank type template
4. **Apply type template** — fill universal fields + type-specific fields
5. **Pre-fill from scan data** — if a matching scan file exists, populate hardware/network/drive fields automatically
6. **Write file** — create or update at `~/.claude/local/inventory/assets/{type}/{slug}.md`
7. **Report** — output: `Created asset: {slug} (type: {type}, status: {status})` or `Updated asset: {slug} (changed: {field_list})`

## Update Semantics

On update, only touch fields that have new data. Never blank out a field that already has a value unless explicitly requested. Bump `last_seen` on every write.

## Validation

- `id` must match the filename slug
- `type` must be one of: machine, drive, mobile, venue, network, service
- `status` must be one of: active, inactive, decommissioned, unknown
- `priority` must be one of: critical, important, optional
- Relationships must reference valid slugs (warn on dangling refs, don't block)
