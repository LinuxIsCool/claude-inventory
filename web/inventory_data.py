"""Read-only query layer for the inventory webapp.

Privacy gate enforced at serializer boundary. Sui-generis rows are hard-rejected
and never reach JSON output. All connections open with PRAGMA query_only=1 so
that even buggy code paths cannot mutate.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB_PATH = Path.home() / ".claude" / "local" / "inventory" / "db" / "inventory.db"
SUI_GENERIS = "indigenous-sui-generis"
RESTRICTED = "restricted"

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


def hardware_list(
    conn: sqlite3.Connection,
    asset_type: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Return hardware assets (drives, machines, mobiles) as a flat list with type."""
    sql = """
        SELECT
            a.asset_id, a.asset_type, a.name, a.manufacturer, a.model,
            a.status, a.location, a.last_seen, a.created_at
        FROM assets a
        WHERE a.asset_type IN ('drive','machine','mobile','network','venue','peripheral')
    """
    params: list = []
    if asset_type:
        sql += " AND a.asset_type = ?"
        params.append(asset_type)
    sql += " ORDER BY a.asset_type, a.name LIMIT ?"
    params.append(limit)
    rows = query(conn, sql, tuple(params))

    # Enrich drives with capacity (from observations if present)
    drive_ids = [r["asset_id"] for r in rows if r["asset_type"] == "drive"]
    if drive_ids:
        placeholders = ",".join("?" * len(drive_ids))
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
        # Keep only newest per (asset_id, metric)
        cap_by_drive: dict[str, dict] = {}
        for cr in cap_rows:
            key = cr["asset_id"]
            cap_by_drive.setdefault(key, {})
            metric = cr["metric"]
            if metric not in cap_by_drive[key]:
                cap_by_drive[key][metric] = cr["value_num"] or cr["value_text"]
        for r in rows:
            if r["asset_type"] == "drive":
                r["capacity"] = cap_by_drive.get(r["asset_id"], {})
    return rows


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
