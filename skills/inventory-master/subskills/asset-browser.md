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

Render browse results as grouped markdown tables:

```
## Fleet Overview (15 assets)

### Machines (4)
| ID | Name | Role | OS | Status | Health |
|----|------|------|----|--------|--------|
| legion | Legion T5 | primary | CachyOS | active | 85 |

### Drives (8)
| ID | Capacity | Used | Machine | Backup | FS |
|----|----------|------|---------|--------|----|
| 24tb-expansion | 21.8TB | 2.7TB | legion | backed-up | btrfs |
```

Stats output uses a compact summary block:

```
## Fleet Stats
- Assets: 15 total (4 machines, 8 drives, 2 mobile, 1 network)
- Status: 12 active, 2 stored, 1 decommissioned
- Backup: 75% coverage (6/8 data assets backed up)
- Capacity: 45.6TB total, 12.3TB used, 33.3TB free
- Health: 82 average (fleet composite)
- Stale: 2 assets not seen in 30+ days
```

## Column Reference by Type

- **Machines**: ID, Name, Role, OS, Status, Health
- **Drives**: ID, Capacity, Used, Machine, Backup, FS
- **Mobile**: ID, Name, OS, Status, Carrier, Last Seen
- **Network**: ID, Name, Type, IP, Status, Connected To
- **Venues**: ID, Name, Location, Next Event, Status

## Notes

- Never truncate asset data. Show all matching assets in full.
- IDs must be human-readable slugs, not UUIDs.
- Sort stale and unbacked results by urgency (oldest/largest gaps first).
- The `ventures` field is a list; `browse venture:X` matches if X appears anywhere in that list.
