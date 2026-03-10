# Asset Browser — Browse, Search & Stats

Subskill for browsing, searching, and summarizing the asset inventory.

## Data Source

- Path: `~/.claude/local/inventory/assets/{type}/*.md`
- Each asset file uses YAML frontmatter between `---` delimiters
- Use **Glob** to find files, **Read** to parse them, **Grep** for keyword search

## Browse Modes

All browse commands read asset frontmatter and render grouped tables.

| Command | Description |
|---------|-------------|
| `browse all` | All assets grouped by type, sorted by priority |
| `browse machines` | Machines with status, role, OS |
| `browse drives` | Drives with capacity, used, backup status, machine |
| `browse mobile` | Phones and tablets |
| `browse network` | Network devices and topology |
| `browse venues` | Venues with upcoming events |
| `browse unbacked` | Assets where `backup_status` = `none` or `partial` |
| `browse stale` | Assets where `last_seen` is older than `config.health.stale_days` (default 30) |
| `browse venture:X` | Assets linked via the `ventures` field matching X |
| `search <keyword>` | Grep across all asset files for keyword matches |

## Implementation

1. **Glob** for `~/.claude/local/inventory/assets/**/*.md`
2. **Read** each file, extract YAML frontmatter between `---` delimiters
3. Parse frontmatter fields into structured data
4. Apply filters based on the browse mode selected
5. Sort by `priority` (descending) within each group, then by `name`
6. Render as markdown tables grouped by asset type

For `search <keyword>`: use **Grep** with the keyword pattern across the assets directory,
then read and display matching files with context.

For `browse stale`: compare `last_seen` date against today minus `stale_days`.
Assets with no `last_seen` field are always considered stale.

For `browse unbacked`: filter to assets that have storage (drives, machines with drives)
where `backup_status` is `none` or `partial`.

## Stats Mode

Generate a fleet summary by aggregating frontmatter across all assets.

| Metric | Calculation |
|--------|-------------|
| Total assets by type | Count files per `assets/{type}/` directory |
| Total by status | Group all assets by their `status` field |
| Backup coverage | Percentage of data-containing assets with `backup_status` = `backed-up` |
| Capacity overview | Sum `capacity`, `used`, derive `free` across all drives |
| Health score | Fleet-wide composite average of all `health` fields |
| Stale count | Assets with `last_seen` older than 30 days or missing |

## Display Format

Render browse results as grouped markdown tables with enriched columns:

```
## Fleet Overview (23 assets)

### Machines (5)
| ID | Name | Type | Status | Backup | Backup Date | Priority | Next Step |
|----|------|------|--------|--------|-------------|----------|-----------|
| legion | Lenovo Legion T5 | desktop | active | partial | — | critical | Set up Borg backup |

### Drives (13)
| ID | Name | Type | FS | Capacity | Used | Used% | Machine | Backup | Backup Date | Priority | Next Step |
|----|------|------|----|---------:|-----:|------:|---------|--------|-------------|----------|-----------|
| nvme0-system | Kingston SNV2S500G | int-nvme | btrfs | 462G | 34G | 7% | legion | partial | — | critical | Set up Borg |

### Mobile (3)
| ID | Name | Status | Backup | Backup Date | Priority | Next Step |
|----|------|--------|--------|-------------|----------|-----------|
| samsung-s10 | Galaxy S10 | active | partial | — | important | Full backup |

### Network (2)
| ID | Name | Type | Status | Priority |
|----|------|------|--------|----------|
| telus-router | TELUS Gateway | router | active | critical |
```

## Computed Fields

- **Used%**: Computed from `used / capacity * 100`. If `used` has `~` prefix, mark percentage as approximate too.
  Show `?` if either `used` or `capacity` is missing/empty.

## Drive Type Abbreviations

| Subtype | Display |
|---------|---------|
| internal-nvme | int-nvme |
| internal-ssd | int-ssd |
| internal-sata | int-sata |
| internal-hdd | int-hdd |
| external-ssd | ext-ssd |
| external-hdd | ext-hdd |
| usb-stick | usb-stick |

Stats output uses a compact summary block:

```
## Fleet Stats
- Assets: 23 total (5 machines, 13 drives, 3 mobile, 2 network)
- Status: 18 active, 3 stored, 2 infra
- Backup: 60% coverage (6/10 data assets fully backed up)
- Capacity: ~30TB total, ~11TB used, ~19TB free
- Capacity alerts: drives above 80% used
- Unbacked: assets with backup_status = none
- Health: 75 average (fleet composite)
- Stale: assets not seen in 30+ days
```

## Column Reference by Type

- **Machines**: ID, Name, Type (desktop/laptop/server), Status, Backup, Backup Date, Priority, Next Step
- **Drives**: ID, Name, Type (int-nvme/ext-hdd/etc), FS, Capacity, Used, Used%, Machine, Backup, Backup Date, Priority, Next Step
- **Mobile**: ID, Name, Status, Backup, Backup Date, Priority, Next Step
- **Network**: ID, Name, Type, Status, Priority
- **Venues**: ID, Name, Location, Next Event, Status (excluded from fleet view)

## Notes

- Never truncate asset data. Show all matching assets in full.
- IDs must be human-readable slugs, not UUIDs.
- Sort stale and unbacked results by urgency (oldest/largest gaps first).
- The `ventures` field is a list; `browse venture:X` matches if X appears anywhere in that list.
