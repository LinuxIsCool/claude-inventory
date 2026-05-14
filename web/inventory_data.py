"""Read-only query layer for the inventory webapp.

Privacy gate enforced at serializer boundary. Sui-generis rows are hard-rejected
and never reach JSON output. All connections open with PRAGMA query_only=1 so
that even buggy code paths cannot mutate.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB_PATH = Path.home() / ".claude" / "local" / "inventory" / "db" / "inventory.db"
SUI_GENERIS = "indigenous-sui-generis"
RESTRICTED = "restricted"


# ──────────────────────────── live drive scan ────────────────────────────
# Read-only probes of the running kernel state. No external commands; pure
# /dev + /proc + statvfs. Used to enrich drive rows with a `connected`
# status (attached + mounted + accessible) and fresh capacity values.


def _live_attached_uuids() -> set[str]:
    """Lowercase set of FS-UUIDs currently visible under /dev/disk/by-uuid/."""
    by_uuid = Path("/dev/disk/by-uuid")
    if not by_uuid.is_dir():
        return set()
    try:
        return {p.name.lower() for p in by_uuid.iterdir()}
    except OSError:
        return set()


def _live_mounts_by_uuid() -> dict[str, str]:
    """Map FS-UUID → live mount point. Built from /dev/disk/by-uuid + /proc/mounts."""
    by_uuid_dir = Path("/dev/disk/by-uuid")
    if not by_uuid_dir.is_dir():
        return {}
    # Resolve every UUID symlink to its real /dev/sdXY path
    dev_to_uuid: dict[str, str] = {}
    for link in by_uuid_dir.iterdir():
        try:
            dev_to_uuid[link.resolve().as_posix()] = link.name.lower()
        except OSError:
            continue
    out: dict[str, str] = {}
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                # /proc/mounts encodes spaces as \040 etc.
                dev = parts[0]
                mp = parts[1].replace("\\040", " ").replace("\\011", "\t")
                uuid = dev_to_uuid.get(dev)
                if uuid:
                    out[uuid] = mp
    except OSError:
        pass
    return out


def _statvfs_safe(mount_point: str) -> dict[str, int] | None:
    """Return total/used/free bytes for mount_point, or None on any error."""
    try:
        s = os.statvfs(mount_point)
    except OSError:
        return None
    if s.f_frsize <= 0 or s.f_blocks <= 0:
        return None
    total = s.f_blocks * s.f_frsize
    free = s.f_bavail * s.f_frsize
    # f_bfree counts ALL free incl. root-reserved; f_bavail is what the user can use.
    used = total - (s.f_bfree * s.f_frsize)
    return {"total_bytes": total, "used_bytes": used, "free_bytes": free}

# ──────────────────────────── connection ────────────────────────────


def get_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open inventory.db read-only. PRAGMA query_only=1 prevents mutation."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"inventory.db not found at {path}")
    # mode=ro guarantees read-only at the URI layer; query_only is the belt+braces.
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    return conn


def query(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> list[dict]:
    """Run a SELECT and return list of dicts."""
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def query_one(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> dict | None:
    """Run a SELECT and return first row or None."""
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


# ──────────────────────────── privacy gate ────────────────────────────


def serialize_identity_link(row: dict, is_localhost: bool = True) -> dict | None:
    """Return None for sui-generis rows. Mask restricted on remote bind.

    Privacy classes:
      public                      → always renderable
      private                     → renderable on localhost; hidden remote
      restricted                  → renderable on localhost; masked remote
      indigenous-sui-generis      → NEVER renderable (returns None)
    """
    privacy = (row or {}).get("privacy_class")
    if privacy == SUI_GENERIS:
        return None
    if not is_localhost:
        if privacy == "private":
            return None
        if privacy == RESTRICTED:
            row = dict(row)
            row["identifier"] = _mask_identifier(row.get("identifier", ""), row.get("protocol", ""))
            row["_masked"] = True
    return row


def _mask_identifier(identifier: str, protocol: str) -> str:
    """Mask identifier for remote rendering of restricted rows."""
    if not identifier:
        return identifier
    if "@" in identifier and protocol in {"email"}:
        local, _, domain = identifier.partition("@")
        if not local:
            return identifier
        return f"{local[:1]}{'*' * max(1, len(local) - 1)}@{domain}"
    if identifier.startswith("+"):
        # Phone: keep country code, mask rest
        return f"{identifier[:5]}{'*' * max(1, len(identifier) - 5)}"
    if len(identifier) <= 4:
        return "*" * len(identifier)
    return f"{identifier[:2]}{'*' * (len(identifier) - 2)}"


def serialize_identity_links(rows: Iterable[dict], is_localhost: bool = True) -> list[dict]:
    """Apply serialize_identity_link to each row, dropping None."""
    out = []
    for row in rows:
        serialized = serialize_identity_link(row, is_localhost=is_localhost)
        if serialized is not None:
            out.append(serialized)
    return out


# ──────────────────────────── overview ────────────────────────────


def overview(conn: sqlite3.Connection) -> dict[str, Any]:
    """Counts + privacy breakdown + recent additions + DB metadata."""
    counts = {}
    for row in query(conn, "SELECT asset_type, COUNT(*) AS n FROM assets GROUP BY asset_type ORDER BY asset_type"):
        counts[row["asset_type"]] = row["n"]
    counts["TOTAL"] = sum(counts.values())

    # Identity link counts
    link_count = query_one(conn, "SELECT COUNT(*) AS n FROM identity_links")
    counts["identity_links"] = link_count["n"] if link_count else 0

    # Relationships
    rel_count = query_one(conn, "SELECT COUNT(*) AS n FROM relationships")
    counts["relationships"] = rel_count["n"] if rel_count else 0

    # Privacy breakdown
    privacy_breakdown = {}
    for row in query(
        conn,
        "SELECT privacy_class, COUNT(*) AS n FROM identity_links GROUP BY privacy_class ORDER BY privacy_class",
    ):
        privacy_breakdown[row["privacy_class"]] = row["n"]

    # Recent additions
    recent = query(
        conn,
        """
        SELECT asset_id, asset_type, name, status, last_seen, updated_at
        FROM assets
        ORDER BY COALESCE(updated_at, created_at) DESC
        LIMIT 10
        """,
    )

    # Status breakdown — proxy for health (health_score lives in observations later)
    status_breakdown: dict[str, int] = {}
    for row in query(
        conn,
        "SELECT status, COUNT(*) AS n FROM assets GROUP BY status ORDER BY n DESC",
    ):
        status_breakdown[row["status"] or "unknown"] = row["n"]
    health = {"status_breakdown": status_breakdown}

    # Schema version
    schema_version_row = query_one(
        conn, "SELECT MAX(version) AS v FROM schema_migrations"
    )
    schema_version = schema_version_row["v"] if schema_version_row else None

    return {
        "counts": counts,
        "privacy_breakdown": privacy_breakdown,
        "recent_additions": recent,
        "health": health or {"avg_health": None, "below_50": 0, "scored_count": 0},
        "schema_version": schema_version,
    }


# ──────────────────────────── people ────────────────────────────


def people_list(
    conn: sqlite3.Connection,
    org_id: str | None = None,
    relationship_class: str | None = None,
    privacy_class: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = """
        SELECT
            p.asset_id,
            p.full_name,
            p.preferred_name,
            p.primary_email,
            p.primary_phone,
            p.primary_org_id,
            o.legal_name AS primary_org_name,
            o.short_name AS primary_org_short,
            p.role,
            p.anchor_persona_id,
            p.privacy_class,
            p.relationship_class,
            p.relationship_strength,
            p.spelling_lock,
            p.notes,
            (SELECT COUNT(*) FROM identity_links il WHERE il.asset_id = p.asset_id) AS link_count
        FROM people p
        LEFT JOIN organizations o ON o.asset_id = p.primary_org_id
        WHERE 1=1
    """
    params: list = []
    if org_id:
        sql += " AND p.primary_org_id = ?"
        params.append(org_id)
    if relationship_class:
        sql += " AND p.relationship_class = ?"
        params.append(relationship_class)
    if privacy_class:
        sql += " AND p.privacy_class = ?"
        params.append(privacy_class)
    if q:
        sql += """
            AND (
                p.full_name LIKE ? OR
                p.preferred_name LIKE ? OR
                COALESCE(p.notes,'') LIKE ?
            )
        """
        like = f"%{q}%"
        params.extend([like, like, like])
    sql += " ORDER BY p.full_name LIMIT ?"
    params.append(limit)
    return query(conn, sql, tuple(params))


def person_detail(
    conn: sqlite3.Connection, asset_id: str, is_localhost: bool = True
) -> dict | None:
    person = query_one(
        conn,
        """
        SELECT
            p.*,
            o.legal_name AS primary_org_name,
            o.short_name AS primary_org_short
        FROM people p
        LEFT JOIN organizations o ON o.asset_id = p.primary_org_id
        WHERE p.asset_id = ?
        """,
        (asset_id,),
    )
    if not person:
        return None

    links = query(
        conn,
        """
        SELECT protocol, identifier, is_primary, confidence, verified_by, privacy_class, notes
        FROM identity_links
        WHERE asset_id = ?
        ORDER BY protocol, is_primary DESC, identifier
        """,
        (asset_id,),
    )
    person["identity_links"] = serialize_identity_links(links, is_localhost=is_localhost)

    relationships = query(
        conn,
        """
        SELECT
            r.from_asset, fa.name AS from_name,
            r.to_asset,   ta.name AS to_name,
            r.rel_type, r.strength, r.confidence,
            r.source, r.context, r.notes,
            r.first_observed, r.last_observed
        FROM relationships r
        LEFT JOIN assets fa ON fa.asset_id = r.from_asset
        LEFT JOIN assets ta ON ta.asset_id = r.to_asset
        WHERE r.from_asset = ? OR r.to_asset = ?
        ORDER BY r.strength DESC
        """,
        (asset_id, asset_id),
    )
    person["relationships"] = relationships
    return person


# ──────────────────────────── organizations ────────────────────────────


def organizations_list(
    conn: sqlite3.Connection,
    org_type: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = """
        SELECT
            o.asset_id,
            o.legal_name,
            o.short_name,
            o.org_type,
            o.website,
            o.headquarters,
            o.incorporated_date,
            o.privacy_class,
            o.notes,
            (SELECT COUNT(*) FROM people p WHERE p.primary_org_id = o.asset_id) AS member_count,
            (SELECT COUNT(*) FROM ventures v WHERE v.primary_org_id = o.asset_id) AS venture_count
        FROM organizations o
        WHERE 1=1
    """
    params: list = []
    if org_type:
        sql += " AND o.org_type = ?"
        params.append(org_type)
    sql += " ORDER BY o.legal_name LIMIT ?"
    params.append(limit)
    return query(conn, sql, tuple(params))


# ──────────────────────────── ventures ────────────────────────────


def ventures_list(
    conn: sqlite3.Connection,
    stage: str | None = "active",
    limit: int = 200,
) -> list[dict]:
    sql = """
        SELECT
            v.asset_id,
            a.name,
            v.slug,
            v.lifecycle_stage AS stage,
            v.primary_org_id,
            o.legal_name AS primary_org_name,
            o.short_name AS primary_org_short,
            v.md_path,
            v.started_at,
            v.last_milestone_at,
            v.notes
        FROM ventures v
        LEFT JOIN assets a ON a.asset_id = v.asset_id
        LEFT JOIN organizations o ON o.asset_id = v.primary_org_id
        WHERE 1=1
    """
    params: list = []
    if stage and stage != "all":
        sql += " AND v.lifecycle_stage = ?"
        params.append(stage)
    sql += " ORDER BY v.last_milestone_at DESC, a.name LIMIT ?"
    params.append(limit)
    return query(conn, sql, tuple(params))


# ──────────────────────────── hardware ────────────────────────────


# Internality classification (drives only). External = USB/SD/portable form-factor.
_EXTERNAL_INTERFACES = ("usb",)  # match prefix
_EXTERNAL_FORM_FACTORS = {"usb-stick", "sd", "microsd", "external-2.5", "external-3.5", "external"}


def _classify_internality(interface: str | None, form_factor: str | None) -> str:
    iface = (interface or "").lower()
    ff = (form_factor or "").lower()
    if any(iface.startswith(p) for p in _EXTERNAL_INTERFACES):
        return "external"
    if ff in _EXTERNAL_FORM_FACTORS:
        return "external"
    if iface or ff:
        return "internal"
    return "unknown"


def hardware_list(
    conn: sqlite3.Connection,
    asset_type: str | None = None,
    q: str | None = None,
    status: str | None = None,
    location: str | None = None,
    internality: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Return hardware assets (drives, machines, mobiles) as a flat list with type.

    For drives, enriches each row with:
      - `capacity`: dict of size/used/free/pct from the most recent observations,
        overridden by live statvfs values when the drive is currently mounted.
      - `connected`: bool — attached + mounted + statvfs accessible right now.
      - `live_status`: "connected" when connected=True, else None. Frontend uses
        this to override the DB lifecycle badge when live state confirms.
      - `mount_point`: live mount point from /proc/mounts (when connected) or
        DB-recorded value otherwise.
      - `mount_uuid`: filesystem UUID from drives table (used for live matching).
    """
    sql = """
        SELECT
            a.asset_id, a.asset_type, a.name, a.manufacturer, a.model,
            a.status, a.location, a.last_seen, a.created_at, a.notes
        FROM assets a
        WHERE a.asset_type IN ('drive','machine','mobile','network','venue','peripheral')
    """
    params: list = []
    if asset_type:
        sql += " AND a.asset_type = ?"
        params.append(asset_type)
    if status and status != "connected":
        # 'connected' is a live-derived status — handled post-fetch below
        sql += " AND a.status = ?"
        params.append(status)
    if location:
        sql += " AND a.location = ?"
        params.append(location)
    if q:
        sql += " AND (a.name LIKE ? OR COALESCE(a.manufacturer,'') LIKE ? OR COALESCE(a.model,'') LIKE ? OR COALESCE(a.notes,'') LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])
    sql += " ORDER BY a.asset_type, a.name LIMIT ?"
    params.append(limit)
    rows = query(conn, sql, tuple(params))

    drive_ids = [r["asset_id"] for r in rows if r["asset_type"] == "drive"]
    if not drive_ids:
        return rows

    placeholders = ",".join("?" * len(drive_ids))

    # 1) Latest observations per (asset_id, metric)
    cap_rows = query(
        conn,
        f"""
        SELECT asset_id, metric, value_num, value_text, ts
        FROM observations
        WHERE asset_id IN ({placeholders})
          AND metric IN ('size_bytes','used_bytes','free_bytes','capacity_pct','total_bytes')
        ORDER BY ts DESC
        """,
        tuple(drive_ids),
    )
    cap_by_drive: dict[str, dict] = {}
    for cr in cap_rows:
        key = cr["asset_id"]
        cap_by_drive.setdefault(key, {})
        metric = cr["metric"]
        if metric not in cap_by_drive[key]:
            cap_by_drive[key][metric] = cr["value_num"] or cr["value_text"]

    # 2) drives table — for mount_uuid, interface, form_factor, DB-recorded capacity
    drive_rows = query(
        conn,
        f"""
        SELECT asset_id, mount_uuid, mount_point, drive_state,
               capacity_bytes, used_bytes, free_bytes, filesystem,
               interface, form_factor, backup_status, backup_target,
               usage_class, encryption, smart_health
        FROM drives
        WHERE asset_id IN ({placeholders})
        """,
        tuple(drive_ids),
    )
    drives_by_id: dict[str, dict] = {d["asset_id"]: d for d in drive_rows}

    # 3) Live kernel state — run once per request, reused across rows
    attached_uuids = _live_attached_uuids()
    live_mounts = _live_mounts_by_uuid()

    # 4) Enrich each drive row
    for r in rows:
        if r["asset_type"] != "drive":
            continue
        drive = drives_by_id.get(r["asset_id"], {})
        mount_uuid = (drive.get("mount_uuid") or "").lower() or None
        db_mount_point = drive.get("mount_point")
        db_caps = {
            "capacity_bytes": drive.get("capacity_bytes"),
            "used_bytes": drive.get("used_bytes"),
            "free_bytes": drive.get("free_bytes"),
        }

        attached = bool(mount_uuid and mount_uuid in attached_uuids)
        live_mp = live_mounts.get(mount_uuid) if mount_uuid else None
        live_caps = _statvfs_safe(live_mp) if live_mp else None
        connected = bool(attached and live_mp and live_caps)

        # Build the capacity payload: live values win when available.
        cap = dict(cap_by_drive.get(r["asset_id"], {}))
        # Backfill from drives table if observations didn't have them
        if db_caps["capacity_bytes"] and not cap.get("total_bytes") and not cap.get("size_bytes"):
            cap["total_bytes"] = db_caps["capacity_bytes"]
        if db_caps["used_bytes"] and not cap.get("used_bytes"):
            cap["used_bytes"] = db_caps["used_bytes"]
        if db_caps["free_bytes"] and not cap.get("free_bytes"):
            cap["free_bytes"] = db_caps["free_bytes"]
        # Live override
        if live_caps:
            cap["total_bytes"] = live_caps["total_bytes"]
            cap["used_bytes"] = live_caps["used_bytes"]
            cap["free_bytes"] = live_caps["free_bytes"]
            cap["live"] = True
        else:
            cap["live"] = False

        # Compute pct if total known
        total = cap.get("total_bytes") or cap.get("size_bytes")
        used = cap.get("used_bytes")
        if total and used is not None:
            try:
                cap["capacity_pct"] = round(int(used) / int(total) * 100, 1)
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        r["capacity"] = cap
        r["connected"] = connected
        r["attached"] = attached
        r["live_status"] = "connected" if connected else None
        r["mount_point"] = live_mp or db_mount_point
        r["mount_uuid"] = mount_uuid
        r["filesystem"] = drive.get("filesystem")
        r["interface"] = drive.get("interface")
        r["form_factor"] = drive.get("form_factor")
        r["internality"] = _classify_internality(drive.get("interface"), drive.get("form_factor"))
        r["backup_status"] = drive.get("backup_status")
        r["backup_target"] = drive.get("backup_target")
        r["usage_class"] = drive.get("usage_class")
        r["encryption"] = drive.get("encryption")
        r["smart_health"] = drive.get("smart_health")

    # Post-fetch filters that depend on enriched fields
    if status == "connected":
        rows = [r for r in rows if r.get("connected")]
    if internality:
        rows = [r for r in rows if r.get("asset_type") != "drive" or r.get("internality") == internality]

    return rows


def hardware_facets(conn: sqlite3.Connection) -> dict[str, Any]:
    """Distinct filter values + counts for the Hardware page toolbar.

    Returns:
      types       — asset_type counts
      statuses    — a.status counts (includes 'connected' synthetic value at top)
      locations   — a.location counts
      internalities — derived from drives.interface + drives.form_factor
    """
    types = {row["asset_type"]: row["n"] for row in query(
        conn,
        """
        SELECT asset_type, COUNT(*) AS n FROM assets
        WHERE asset_type IN ('drive','machine','mobile','network','venue','peripheral')
        GROUP BY asset_type ORDER BY asset_type
        """,
    )}
    statuses = {row["status"] or "(none)": row["n"] for row in query(
        conn,
        """
        SELECT status, COUNT(*) AS n FROM assets
        WHERE asset_type IN ('drive','machine','mobile','network','venue','peripheral')
        GROUP BY status ORDER BY n DESC
        """,
    )}
    locations = {row["location"] or "(none)": row["n"] for row in query(
        conn,
        """
        SELECT location, COUNT(*) AS n FROM assets
        WHERE asset_type IN ('drive','machine','mobile','network','venue','peripheral')
        GROUP BY location ORDER BY n DESC
        """,
    )}
    # Internality is derived per-drive; compute live
    drive_rows = query(conn, "SELECT interface, form_factor FROM drives")
    internalities: dict[str, int] = {"internal": 0, "external": 0, "unknown": 0}
    for d in drive_rows:
        cls = _classify_internality(d.get("interface"), d.get("form_factor"))
        internalities[cls] = internalities.get(cls, 0) + 1

    # Connected count (live)
    attached = _live_attached_uuids()
    mounts = _live_mounts_by_uuid()
    connected_uuids = {u for u, mp in mounts.items() if u in attached and _statvfs_safe(mp)}
    # match by mount_uuid in drives table
    db_uuids = [row["mount_uuid"].lower() for row in query(
        conn, "SELECT mount_uuid FROM drives WHERE mount_uuid IS NOT NULL AND mount_uuid != ''"
    ) if row["mount_uuid"]]
    connected_count = sum(1 for u in db_uuids if u in connected_uuids)

    return {
        "types": types,
        "statuses": statuses,
        "locations": locations,
        "internalities": internalities,
        "connected_count": connected_count,
    }


def hardware_detail(conn: sqlite3.Connection, asset_id: str) -> dict | None:
    """Single-asset detail for the drawer sidecar."""
    asset = query_one(
        conn,
        """
        SELECT a.*
        FROM assets a
        WHERE a.asset_id = ?
        """,
        (asset_id,),
    )
    if not asset:
        return None
    # Reuse hardware_list with a tight filter to inherit all enrichment
    rows = hardware_list(conn, asset_type=asset["asset_type"], limit=500)
    enriched = next((r for r in rows if r["asset_id"] == asset_id), None)
    if not enriched:
        return None
    # Pull observation history (last 20) for sparkline-ready data
    obs = query(
        conn,
        """
        SELECT metric, value_num, value_text, ts
        FROM observations
        WHERE asset_id = ?
        ORDER BY ts DESC
        LIMIT 20
        """,
        (asset_id,),
    )
    enriched["observations"] = obs
    enriched["notes"] = asset.get("notes")
    return enriched


# ──────────────────────────── identity links ────────────────────────────


def identity_links_list(
    conn: sqlite3.Connection,
    protocol: str | None = None,
    privacy_class: str | None = None,
    q: str | None = None,
    limit: int = 500,
    is_localhost: bool = True,
) -> list[dict]:
    sql = """
        SELECT
            il.link_id,
            il.asset_id,
            a.name AS asset_name,
            a.asset_type,
            il.protocol,
            il.identifier,
            il.is_primary,
            il.confidence,
            il.verified_by,
            il.privacy_class,
            il.notes
        FROM identity_links il
        LEFT JOIN assets a ON a.asset_id = il.asset_id
        WHERE 1=1
    """
    params: list = []
    if protocol:
        sql += " AND il.protocol = ?"
        params.append(protocol)
    if privacy_class:
        sql += " AND il.privacy_class = ?"
        params.append(privacy_class)
    if q:
        sql += " AND (il.identifier LIKE ? OR COALESCE(il.notes,'') LIKE ? OR a.name LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    sql += " ORDER BY a.name, il.protocol, il.is_primary DESC LIMIT ?"
    params.append(limit)
    rows = query(conn, sql, tuple(params))
    return serialize_identity_links(rows, is_localhost=is_localhost)


def identity_protocols(conn: sqlite3.Connection) -> list[dict]:
    return query(
        conn,
        """
        SELECT protocol, COUNT(*) AS n
        FROM identity_links
        WHERE privacy_class != ?
        GROUP BY protocol
        ORDER BY n DESC
        """,
        (SUI_GENERIS,),
    )


# ──────────────────────────── relationships ────────────────────────────


def relationships_list(
    conn: sqlite3.Connection,
    person: str | None = None,
    rel_type: str | None = None,
    limit: int = 500,
) -> list[dict]:
    sql = """
        SELECT
            r.from_asset, fa.name AS from_name, fa.asset_type AS from_type,
            r.to_asset,   ta.name AS to_name,   ta.asset_type AS to_type,
            r.rel_type,
            r.strength,
            r.confidence,
            r.source,
            r.context,
            r.notes,
            r.first_observed,
            r.last_observed
        FROM relationships r
        LEFT JOIN assets fa ON fa.asset_id = r.from_asset
        LEFT JOIN assets ta ON ta.asset_id = r.to_asset
        WHERE 1=1
    """
    params: list = []
    if person:
        sql += " AND (r.from_asset = ? OR r.to_asset = ?)"
        params.extend([person, person])
    if rel_type:
        sql += " AND r.rel_type = ?"
        params.append(rel_type)
    sql += " ORDER BY r.strength DESC, r.last_observed DESC LIMIT ?"
    params.append(limit)
    return query(conn, sql, tuple(params))


# ──────────────────────────── cross-tab search ────────────────────────────


def search_all(conn: sqlite3.Connection, q: str, limit: int = 50) -> list[dict]:
    """Cross-tab search over asset names + identifiers + people preferred names."""
    if not q:
        return []
    like = f"%{q}%"
    out: list[dict] = []

    # Assets by name
    out.extend(
        query(
            conn,
            """
            SELECT asset_id, asset_type, name, 'asset' AS kind
            FROM assets
            WHERE name LIKE ?
            ORDER BY asset_type, name
            LIMIT ?
            """,
            (like, limit),
        )
    )
    # Identity link identifiers (privacy-gated) — also match on linked asset name
    raw_links = query(
        conn,
        """
        SELECT il.link_id, il.asset_id, a.name AS asset_name, a.asset_type,
               il.protocol, il.identifier, il.privacy_class, 'identity_link' AS kind
        FROM identity_links il
        LEFT JOIN assets a ON a.asset_id = il.asset_id
        WHERE il.identifier LIKE ? OR a.name LIKE ? OR COALESCE(il.notes,'') LIKE ?
        ORDER BY a.name
        LIMIT ?
        """,
        (like, like, like, limit),
    )
    out.extend(serialize_identity_links(raw_links, is_localhost=True))

    # People preferred_name + notes
    out.extend(
        query(
            conn,
            """
            SELECT p.asset_id, 'person' AS asset_type,
                   COALESCE(p.preferred_name, p.full_name) AS name,
                   p.full_name, p.role, p.privacy_class, 'person_alt' AS kind
            FROM people p
            WHERE p.preferred_name LIKE ?
               OR COALESCE(p.notes,'') LIKE ?
               OR COALESCE(p.spelling_lock,'') LIKE ?
            ORDER BY p.full_name
            LIMIT ?
            """,
            (like, like, like, limit),
        )
    )
    return out[: limit * 3]


# ──────────────────────────── healthz ────────────────────────────


def healthz(conn: sqlite3.Connection, db_path: Path | None = None) -> dict[str, Any]:
    schema_row = query_one(conn, "SELECT MAX(version) AS v FROM schema_migrations")
    asset_row = query_one(conn, "SELECT COUNT(*) AS n FROM assets")
    return {
        "status": "ok",
        "db_path": str(db_path or DEFAULT_DB_PATH),
        "schema_version": schema_row["v"] if schema_row else None,
        "asset_count": asset_row["n"] if asset_row else 0,
    }
