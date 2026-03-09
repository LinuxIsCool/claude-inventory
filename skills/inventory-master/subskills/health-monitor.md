# Health Monitor — Scoring, Gaps & Risk

Continuous health assessment across the entire asset fleet. Produces per-asset health scores,
fleet-wide summaries, backup coverage reports, and venture risk analysis.

## Health Score Algorithm

Each active asset receives a composite health score (0-100) from four weighted dimensions.

### 1. Backup Score (40% weight)

Map `backup_status` to a numeric value. Only applies to assets where `contains_data: true`.
Assets without data automatically score 100 (nothing to lose).

| backup_status | Score |
|---------------|-------|
| none          | 0     |
| partial       | 50    |
| backed-up     | 80    |
| mirrored      | 100   |

### 2. Freshness Score (30% weight)

Based on days elapsed since `last_seen` timestamp. Staleness degrades confidence
that the asset state is accurately represented.

| Days since last_seen | Score |
|----------------------|-------|
| 0-7                  | 100   |
| 8-14                 | 80    |
| 15-30                | 50    |
| 31-60                | 20    |
| 60+                  | 0     |

### 3. Capacity Score (20% weight)

Applies to drives only (`type: drive`). Based on percentage of capacity used.
Non-drive assets automatically score 100.

| % Used  | Score |
|---------|-------|
| 0-70%   | 100   |
| 71-80%  | 70    |
| 81-90%  | 40    |
| 91-95%  | 10    |
| 96-100% | 0     |

### 4. Connectivity Score (10% weight)

Applies to machines with network configuration. Non-machine assets automatically score 100.

| Network State  | Score |
|----------------|-------|
| Tailscale      | 100   |
| LAN only       | 70    |
| No network     | 0     |

### Composite Calculation

```
health = (backup * 0.4) + (freshness * 0.3) + (capacity * 0.2) + (connectivity * 0.1)
```

Fleet health = weighted average of all active asset health scores.

## Health Report Output

```
## Fleet Health: 72/100

### Critical Issues
- 🔴 E15: backup_status=partial, 93% full (health: 23)
- 🟡 nvme1-other-os: backup_status=none, stale 45d (health: 35)

### By Category
| Category | Assets | Avg Health | Worst |
|----------|--------|------------|-------|
| Machines | 4 | 75 | e15 (42) |
| Drives | 8 | 68 | nvme1 (35) |

### Backup Coverage
- 6/8 data-containing assets backed up (75%)
- Unbacked: nvme1-other-os, samsung-s10
```

Thresholds for issue severity: 🔴 health < 30, 🟡 health < 50, 🟢 health >= 50.

## Venture Risk Assessment

For each active venture, trace `relationships.contains` and `depends_on` to find
referenced data paths and the assets they live on. Report per-venture:

- Asset health and backup status for every dependency
- Example: "Salish Sea Dreaming data on 24tb-expansion (health: 82, backed-up) — OK"

Impact analysis models asset loss scenarios:

- "If legion goes offline, 3 ventures affected" — traverse all relationships to find dependents
- "If 24tb-expansion fails, 2 ventures lose primary data" — check backup coverage for recovery path

## Data & Configuration

- Asset files: `~/.claude/local/inventory/assets/`
- Health thresholds: `~/.claude/local/inventory/config.yml` (override default scoring brackets)
- Report output: stdout by default, optionally written to `~/.claude/local/inventory/reports/`
