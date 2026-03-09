# Fleet Scanner — Auto-Detect & Discover

This is the PRIMARY onboarding flow. Discovery over manual entry.
Scan first, ask questions later. The machine tells you what it is.

## Local Machine Scan

No sudo needed for most of these. Run them all, parse the output.

```bash
# CPU
lscpu | grep "Model name"
nproc

# RAM
free -h | grep Mem

# GPU
lspci | grep -i vga
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null

# Hostname
hostname

# OS
cat /etc/os-release | grep PRETTY_NAME
uname -r

# Drives (detailed)
lsblk --json -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,UUID,MODEL

# btrfs stats (per mount)
btrfs filesystem df /home 2>/dev/null
btrfs filesystem usage /home 2>/dev/null | head -5

# Disk usage
df -h --output=source,size,used,avail,pcent,target | grep -v tmpfs

# Network
ip -4 addr show | grep -oP 'inet \K[\d.]+'
tailscale status --json 2>/dev/null

# Services
systemctl --user list-units --type=service --state=running --no-pager --plain
```

Every command is optional. If it fails, skip and note the gap.

## Scan Workflow

1. Run all commands above, capture stdout for each
2. Parse into structured data (hostname, cpu, ram, gpu, drives, network, services)
3. Compare against existing inventory in `~/.claude/local/inventory/assets/`:
   - Flag drift: new drives, changed capacity, new/missing services
   - Identify new machines vs. known machines
4. Create or update asset files using @asset-writer:
   - One file per machine: `machines/{hostname}.md`
   - One file per drive: `drives/{hostname}-{device}.md`
5. Update `last_seen` timestamp on every touched asset
6. Report: "Scanned {hostname}: N drives detected, X new, Y changed"

Do NOT prompt the user during a scan. Collect everything, report at the end.

## Network Scan

Requires tailscale. If not available, skip gracefully.

```bash
tailscale status --json 2>/dev/null
```

Parse the JSON for peer hostnames, IPs, online/offline status, OS type.
For known peers: update `last_seen`. For unknown: flag as discovered.
Never auto-create remote machine assets — local machine only.

## Drift Detection

Drift = difference between what inventory says and what the scan finds.

| Signal | Action |
|--------|--------|
| New drive appears | Suggest creating asset via @asset-writer |
| Drive capacity changed | Update asset, flag in report |
| Drive missing | Mark as detached/removed, flag |
| Service started/stopped | Note in machine asset |
| Machine offline (network) | Update last_seen, flag if stale (>7d) |
| RAM/CPU changed | Update machine asset (hardware swap?) |
| New tailscale peer | Report as discovered, suggest onboarding |

Drift is informational, not destructive. Never delete assets on drift — mark them.

## Sudo Operations

Some commands need elevated privileges. Never run sudo directly.
Generate a script to `~/.claude/local/scripts/inventory-scan.sh` instead.

Sudo commands: `smartctl` (SMART/health), `blkid` (UUIDs), `btrfs scrub status`.
Script should be idempotent, output JSON to stdout.
User runs: `sudo bash ~/.claude/local/scripts/inventory-scan.sh`
Parse output on the next scan invocation.

## Data Path

```
~/.claude/local/inventory/assets/
├── machines/          # One file per machine
├── drives/            # One file per drive
└── network/           # Network topology, tailscale peers
```

## Invocation

- Full scan: local + network, detect drift, update everything
- Quick scan: local only, skip network, refresh last_seen
- Network only: tailscale peers, update online/offline status

The scanner is the source of truth. Manual edits are overwritten on next scan
unless the field is marked `manual: true` in the asset file.
