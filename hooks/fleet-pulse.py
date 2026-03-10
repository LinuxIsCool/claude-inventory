#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""
Session-start hook: fleet health pulse.
Outputs JSON with systemMessage (visible) and additionalContext (Claude sees).
"""

import json
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

INVENTORY_ROOT = Path.home() / ".claude" / "local" / "inventory"
ASSETS_ROOT = INVENTORY_ROOT / "assets"
HOSTNAME = socket.gethostname()
TODAY = date.today().isoformat()


def parse_frontmatter(path: Path) -> tuple[dict, str, str]:
    """Parse YAML frontmatter. Returns (frontmatter_dict, raw_yaml, body)."""
    content = path.read_text()
    if not content.startswith("---"):
        return {}, "", content
    end = content.find("---", 3)
    if end == -1:
        return {}, "", content
    raw_yaml = content[3:end]
    body = content[end + 3:]
    return yaml.safe_load(raw_yaml) or {}, raw_yaml, body


def write_frontmatter(path: Path, fm: dict, body: str):
    """Write updated frontmatter back to asset file, preserving body."""
    yaml_str = yaml.dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{yaml_str}---{body}")


def get_live_drive_info() -> dict[str, dict]:
    """Get current drive info from lsblk + df. Returns {device: info}."""
    drives = {}
    try:
        # lsblk: device name, model, serial, size, transport, fstype, mountpoint, uuid
        result = subprocess.run(
            ["lsblk", "-bdno", "NAME,MODEL,SERIAL,SIZE,TRAN,FSTYPE,MOUNTPOINT,UUID"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 7)
            if len(parts) < 4:
                continue
            name = parts[0]
            drives[f"/dev/{name}"] = {
                "model": parts[1] if len(parts) > 1 and parts[1] else None,
                "serial": parts[2] if len(parts) > 2 and parts[2] else None,
                "size_bytes": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None,
                "transport": parts[4] if len(parts) > 4 and parts[4] else None,
                "fstype": parts[5] if len(parts) > 5 and parts[5] else None,
                "mountpoint": parts[6] if len(parts) > 6 and parts[6] else None,
                "uuid": parts[7] if len(parts) > 7 and parts[7] else None,
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # df for usage info on mounted filesystems
    try:
        result = subprocess.run(
            ["df", "-B1", "--output=target,size,used"],
            capture_output=True, text=True, timeout=5,
        )
        mount_usage = {}
        for line in result.stdout.strip().splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 3:
                mount_usage[parts[0]] = {
                    "capacity_bytes": int(parts[1]),
                    "used_bytes": int(parts[2]),
                }
        # Attach usage to drives by mountpoint
        for dev, info in drives.items():
            mp = info.get("mountpoint")
            if mp and mp in mount_usage:
                info["capacity_bytes"] = mount_usage[mp]["capacity_bytes"]
                info["used_bytes"] = mount_usage[mp]["used_bytes"]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return drives


def human_size(nbytes: int | None) -> str | None:
    """Convert bytes to human-readable size matching existing format (e.g. 462G, 1.9T)."""
    if nbytes is None:
        return None
    tb = nbytes / (1024 ** 4)
    if tb >= 1.0:
        return f"{tb:.1f}T" if tb < 10 else f"{int(tb)}T"
    gb = nbytes / (1024 ** 3)
    if gb >= 1.0:
        return f"{int(gb)}G"
    mb = nbytes / (1024 ** 2)
    return f"{int(mb)}M"


def refresh_local_drives(live: dict[str, dict]):
    """Update drive asset files for drives on this machine with live data."""
    drives_dir = ASSETS_ROOT / "drives"
    if not drives_dir.exists():
        return

    # Build lookup by UUID (most reliable) and device path
    by_uuid = {}
    by_device = {}
    for dev, info in live.items():
        if info.get("uuid"):
            by_uuid[info["uuid"]] = (dev, info)
        by_device[dev] = info

    for f in drives_dir.glob("*.md"):
        fm, raw_yaml, body = parse_frontmatter(f)
        if not fm or fm.get("type") != "drive":
            continue

        # Only refresh drives belonging to this machine or currently mounted here
        machine = fm.get("machine", "")
        if machine not in (HOSTNAME, "legion", "portable"):
            continue

        # Match by UUID first, then device path
        match = None
        dev_path = None
        asset_uuid = fm.get("uuid")
        asset_device = fm.get("device")

        if asset_uuid and asset_uuid in by_uuid:
            dev_path, match = by_uuid[asset_uuid]
        elif asset_device and asset_device in by_device:
            match = by_device[asset_device]
            dev_path = asset_device

        if not match:
            continue

        # Update fields that can be machine-read
        changed = False

        if match.get("mountpoint") and fm.get("mount_point") != match["mountpoint"]:
            fm["mount_point"] = match["mountpoint"]
            changed = True

        if dev_path and fm.get("device") != dev_path:
            fm["device"] = dev_path
            changed = True

        cap = human_size(match.get("capacity_bytes"))
        if cap and fm.get("capacity") != cap:
            fm["capacity"] = cap
            changed = True

        used = human_size(match.get("used_bytes"))
        if used is not None and fm.get("used") != used:
            fm["used"] = used
            changed = True

        if fm.get("last_seen") != TODAY:
            fm["last_seen"] = TODAY
            changed = True

        if changed:
            write_frontmatter(f, fm, body)


def _parse_size(s: str) -> float:
    """Parse human-readable size like '462G', '1.9T', '281G' to bytes."""
    s = s.strip().lstrip("~")
    if not s or s == "0":
        return 0.0
    multipliers = {"T": 1024**4, "G": 1024**3, "M": 1024**2, "K": 1024}
    if s[-1].upper() in multipliers:
        return float(s[:-1]) * multipliers[s[-1].upper()]
    return float(s)


def compute_health(fm: dict) -> int:
    """Compute per-asset health score 0-100."""
    score = 0.0

    # Backup (40%)
    backup_map = {"none": 0, "partial": 50, "backed-up": 80, "mirrored": 100}
    if fm.get("contains_data", False):
        backup = fm.get("backup_status", "none")
        score += backup_map.get(backup, 0) * 0.4
    else:
        score += 100 * 0.4

    # Freshness (30%)
    last_seen = fm.get("last_seen")
    if last_seen:
        try:
            days = (date.today() - date.fromisoformat(str(last_seen))).days
            if days <= 7: fresh = 100
            elif days <= 14: fresh = 80
            elif days <= 30: fresh = 50
            elif days <= 60: fresh = 20
            else: fresh = 0
            score += fresh * 0.3
        except (ValueError, TypeError):
            score += 50 * 0.3
    else:
        score += 50 * 0.3

    # Capacity (20%) — drives only, based on used/capacity ratio
    if fm.get("type") == "drive":
        cap_str = str(fm.get("capacity", ""))
        used_str = str(fm.get("used", "")).lstrip("~")
        try:
            cap_val = _parse_size(cap_str)
            used_val = _parse_size(used_str)
            if cap_val > 0:
                pct = used_val / cap_val * 100
                if pct < 60: cap_score = 100
                elif pct < 75: cap_score = 80
                elif pct < 85: cap_score = 50
                elif pct < 95: cap_score = 20
                else: cap_score = 0
                score += cap_score * 0.2
            else:
                score += 70 * 0.2
        except (ValueError, TypeError):
            score += 70 * 0.2
    else:
        score += 100 * 0.2

    # Connectivity (10%) — machines only
    if fm.get("type") == "machine":
        network = fm.get("network", {})
        if network and (network.get("ip_tailscale") or network.get("ssh_host")):
            score += 100 * 0.1
        elif network and network.get("ip_local"):
            score += 70 * 0.1
        else:
            score += 0 * 0.1
    else:
        score += 100 * 0.1

    return int(score)


def output(system_msg: str, additional: str = None):
    """Output JSON with systemMessage and additionalContext."""
    print(json.dumps({
        "systemMessage": system_msg,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": additional or system_msg,
        },
    }))


def main():
    try:
        json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        pass

    if not ASSETS_ROOT.exists():
        output("[inventory] no assets yet · /inventory scan to start")
        return

    # Auto-refresh local drives with live data before health scan
    try:
        live = get_live_drive_info()
        if live:
            refresh_local_drives(live)
    except Exception:
        pass  # refresh is best-effort, never block startup

    # Scan all asset files
    type_counts = {}
    total_health = 0
    asset_count = 0
    unbacked = 0
    stale = 0
    critical_issues = []

    # Venue/service types are location references, not fleet devices
    SKIP_TYPES = {"venues", "services"}

    for type_dir in ASSETS_ROOT.iterdir():
        if not type_dir.is_dir():
            continue
        if type_dir.name in SKIP_TYPES:
            continue
        for f in type_dir.glob("*.md"):
            fm, _, _ = parse_frontmatter(f)
            if fm.get("status") in ("retired", "wiped"):
                continue

            asset_type = fm.get("type", type_dir.name)
            type_counts[asset_type] = type_counts.get(asset_type, 0) + 1

            health = compute_health(fm)
            total_health += health
            asset_count += 1

            if fm.get("contains_data") and fm.get("backup_status") in ("none", None):
                unbacked += 1

            last_seen = fm.get("last_seen")
            if last_seen:
                try:
                    days = (date.today() - date.fromisoformat(str(last_seen))).days
                    if days > 30:
                        stale += 1
                except (ValueError, TypeError):
                    stale += 1
            else:
                stale += 1

            if health < 40:
                critical_issues.append(f"{fm.get('id', f.stem)}: health {health}")

    if asset_count == 0:
        output("[inventory] no active assets · /inventory scan to start")
        return

    fleet_health = total_health // asset_count

    # Build compact systemMessage
    type_summary = " · ".join(f"{c} {t}s" for t, c in sorted(type_counts.items()))
    parts = [f"[inventory] {asset_count} assets ({type_summary})", f"health: {fleet_health}/100"]
    if unbacked > 0:
        parts.append(f"{unbacked} unbacked")
    if stale > 0:
        parts.append(f"{stale} stale")

    system_msg = " · ".join(parts)

    # Build detailed additionalContext
    detail_parts = [system_msg]
    if critical_issues:
        detail_parts.append(f"Critical: {', '.join(critical_issues[:3])}")

    output(system_msg, " | ".join(detail_parts))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
