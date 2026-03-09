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
import sys
from datetime import date
from pathlib import Path

import yaml

INVENTORY_ROOT = Path.home() / ".claude" / "local" / "inventory"
ASSETS_ROOT = INVENTORY_ROOT / "assets"


def parse_frontmatter(path: Path) -> dict:
    content = path.read_text()
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    return yaml.safe_load(content[3:end]) or {}


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

    # Capacity (20%) — drives only
    if fm.get("type") == "drive":
        score += 70 * 0.2  # default mid-range for drives
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

    # Scan all asset files
    type_counts = {}
    total_health = 0
    asset_count = 0
    unbacked = 0
    critical_issues = []

    for type_dir in ASSETS_ROOT.iterdir():
        if not type_dir.is_dir():
            continue
        for f in type_dir.glob("*.md"):
            fm = parse_frontmatter(f)
            if fm.get("status") in ("retired", "wiped"):
                continue

            asset_type = fm.get("type", type_dir.name)
            type_counts[asset_type] = type_counts.get(asset_type, 0) + 1

            health = compute_health(fm)
            total_health += health
            asset_count += 1

            if fm.get("contains_data") and fm.get("backup_status") in ("none", None):
                unbacked += 1

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
