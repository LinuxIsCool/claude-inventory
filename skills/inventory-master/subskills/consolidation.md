# Consolidation — Migration, Backup & Wipe Tracking

Tracks the full lifecycle of data consolidation: from initial inventory through
backup, verification, organization, and final wipe of source media.

## Consolidation Phases (per asset)

Each asset moves through these phases sequentially:

1. **Inventory** — catalog what's on the drive/machine
2. **Backup** — ensure data is copied to consolidation target (24TB)
3. **Verify** — checksum verification of backup
4. **Consolidate** — organize into PARA/Johnny Decimal structure on target
5. **Wipe-ready** — all data verified on target, source can be wiped
6. **Wiped** — secure erase completed

Track phase in asset frontmatter:

```yaml
consolidation_phase: inventory|backup|verify|consolidate|wipe-ready|wiped
```

## Rsync Command Generation

Given source asset and target, generate:

```bash
rsync -avhP --info=progress2 \
  user@source:/path/to/data/ \
  /mnt/data-24tb/10-19_Projects/incoming/{source-slug}/
```

Flags:
- `-a` archive mode (preserves permissions, timestamps, symlinks)
- `-v` verbose
- `-h` human-readable sizes
- `-P` show progress + allow resume on interrupt
- `--info=progress2` overall transfer progress

## Verification

After backup completes, verify integrity with checksums:

```bash
# Generate checksums on source
find /source -type f -exec sha256sum {} + > /tmp/source-checksums.txt

# Verify on target
cd /target && sha256sum -c /tmp/source-checksums.txt
```

Mark asset as verified only when all checksums pass with zero mismatches.

## Dashboard

Generate a consolidation progress dashboard from asset frontmatter:

```
## Consolidation Progress

| Asset | Phase | Data Size | Target | Verified |
|-------|-------|-----------|--------|----------|
| e15 | backup | 28GB | 24tb | partial |
| nvme1-other-os | inventory | 944GB | — | — |
| samsung-t7 | wipe-ready | 1TB | 24tb | ✓ |
```

## Workflow

1. Run inventory on asset — create/update asset card with `consolidation_phase: inventory`
2. Generate rsync command for the asset and execute backup
3. Update phase to `backup` while transfer is in progress
4. Run verification checksums on completion
5. Update phase to `verify` (or back to `backup` if mismatches found)
6. Reorganize data into PARA/Johnny Decimal structure on target
7. Update phase to `consolidate`, then `wipe-ready` once confirmed
8. After secure erase, update phase to `wiped`

## Data Path

Asset cards live at: `~/.claude/local/inventory/assets/`

Each asset file contains frontmatter with `consolidation_phase` and all
relevant metadata (size, mount point, filesystem, last seen, etc.).
