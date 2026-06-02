"""InventoryHandler — claude-webui WebuiHandler subclass for inventory routes.

Mode B (Platform mount at :8800/inventory/) dispatch. Ports the legacy
InventoryHandler route table from server.py onto the kernel's WebuiHandler
base, inheriting gzip / 405 / OPTIONS / static helpers. Data access is
delegated to inventory_data.py (iv), reading the SQLite mirror at
``self.accessor.db_path``.

Read-only: the kernel's catch-all rejects POST/PUT/DELETE/PATCH with 405.
Privacy gate (sui-generis identity_links hard-rejected; restricted rows
masked on remote bind) is enforced inside iv.serialize_identity_link* —
this handler just forwards the is_localhost signal.
"""
from __future__ import annotations

import contextlib
import mimetypes
import sys
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from claude_webui.kernel import WebuiHandler

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import inventory_data as iv  # noqa: E402

from inventory_accessor import InventoryAccessor  # noqa: E402

__version__ = "0.2.0"

MAX_LIMIT = 1000
VENDOR_DIR = (HERE / "vendor").resolve()


# ── arg helpers (mirror legacy server.py) ─────────────────────────────


def _int_arg(params: dict[str, list[str]], key: str, default: int,
             max_value: int = MAX_LIMIT) -> int:
    try:
        value = int(params.get(key, [str(default)])[0])
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, max_value))


def _str_arg(params: dict[str, list[str]], key: str, default: str = "") -> str:
    return (params.get(key, [default])[0] or "").strip()


def _opt_str(params: dict[str, list[str]], key: str) -> str | None:
    val = _str_arg(params, key, "")
    return val or None


class InventoryHandler(WebuiHandler):
    """Substrate-specific GET dispatch over the inventory SQLite mirror."""

    server_version = f"claude-inventory/{__version__}"
    accessor: ClassVar[InventoryAccessor]  # type: ignore[assignment]

    @property
    def _db_path(self) -> Path:
        return self.accessor.db_path

    def _is_localhost(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1", "localhost"}

    def _dispatch_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query, keep_blank_values=True)
        is_local = self._is_localhost()

        # ── generic / kernel-served ────────────────────────────────────
        if path in ("/", "/index.html"):
            return self._serve_index()
        if path == "/favicon.ico":
            return self._serve_favicon()
        if path == "/healthz":
            return self._send_json(self.accessor.healthz())
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path.startswith("/vendor/"):
            return self._serve_vendor(path[len("/vendor/"):])

        # ── inventory-specific routes ──────────────────────────────────
        if path == "/api/overview":
            return self._send_json(self.accessor.stats())
        if path == "/api/people":
            return self._serve_people(params)
        if path.startswith("/api/people/"):
            return self._serve_person(path[len("/api/people/"):].strip("/"), is_local)
        if path == "/api/organizations":
            return self._serve_organizations(params)
        if path == "/api/ventures":
            return self._serve_ventures(params)
        if path == "/api/hardware":
            return self._serve_hardware(params)
        if path == "/api/hardware/facets":
            return self._serve_hardware_facets()
        if path.startswith("/api/hardware/"):
            return self._serve_hardware_detail(path[len("/api/hardware/"):].strip("/"))
        if path == "/api/identity-links":
            return self._serve_identity_links(params, is_local)
        if path == "/api/identity-protocols":
            return self._serve_identity_protocols()
        if path == "/api/relationships":
            return self._serve_relationships(params)
        if path == "/api/search":
            return self._serve_search(params)

        self._send_json({"error": f"unknown path: {path}"}, status=404)

    # ── static (vendor) ────────────────────────────────────────────────

    def _serve_vendor(self, rel: str) -> None:
        """Serve files from web/vendor/ only, sandbox-checked."""
        candidate = (HERE / "vendor" / rel).resolve()
        try:
            candidate.relative_to(VENDOR_DIR)
        except ValueError:
            return self._send_json({"error": "path traversal blocked"}, status=400)
        if not candidate.exists() or not candidate.is_file():
            return self._send_json({"error": f"not found: {rel}"}, status=404)
        ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self._send_bytes(
            candidate.read_bytes(),
            content_type=ctype,
            cache_control="no-cache, must-revalidate",
        )

    # ── route handlers (ported from legacy server.py) ──────────────────

    def _serve_people(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            rows = iv.people_list(
                conn,
                org_id=_opt_str(params, "org_id"),
                relationship_class=_opt_str(params, "relationship_class"),
                privacy_class=_opt_str(params, "privacy_class"),
                q=_opt_str(params, "q"),
                limit=_int_arg(params, "limit", 200),
            )
        self._send_json({"people": rows, "total": len(rows)})

    def _serve_person(self, asset_id: str, is_local: bool) -> None:
        if not asset_id:
            return self._send_json({"error": "asset_id required"}, status=400)
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            person = iv.person_detail(conn, asset_id, is_localhost=is_local)
        if person is None:
            return self._send_json({"error": f"person not found: {asset_id}"}, status=404)
        self._send_json(person)

    def _serve_organizations(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            rows = iv.organizations_list(
                conn,
                org_type=_opt_str(params, "type"),
                limit=_int_arg(params, "limit", 200),
            )
        self._send_json({"organizations": rows, "total": len(rows)})

    def _serve_ventures(self, params: dict[str, list[str]]) -> None:
        stage = _str_arg(params, "stage", "active") or None
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            rows = iv.ventures_list(conn, stage=stage, limit=_int_arg(params, "limit", 200))
        self._send_json({"ventures": rows, "total": len(rows), "stage": stage})

    def _serve_hardware(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            rows = iv.hardware_list(
                conn,
                asset_type=_opt_str(params, "type"),
                q=_opt_str(params, "q"),
                status=_opt_str(params, "status"),
                location=_opt_str(params, "location"),
                internality=_opt_str(params, "internality"),
                limit=_int_arg(params, "limit", 500),
            )
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(r["asset_type"], []).append(r)
        total_bytes = free_bytes = used_bytes = connected = drive_count = 0
        for r in rows:
            if r.get("asset_type") != "drive":
                continue
            drive_count += 1
            if r.get("connected"):
                connected += 1
            cap = r.get("capacity") or {}
            try:
                total_bytes += int(cap.get("total_bytes") or cap.get("size_bytes") or 0)
                used_bytes += int(cap.get("used_bytes") or 0)
                free_bytes += int(cap.get("free_bytes") or 0)
            except (TypeError, ValueError):
                pass
        summary = {
            "count": len(rows),
            "drive_count": drive_count,
            "connected_count": connected,
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "free_bytes": free_bytes,
        }
        self._send_json({"hardware": rows, "grouped": grouped, "total": len(rows), "summary": summary})

    def _serve_hardware_facets(self) -> None:
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            self._send_json(iv.hardware_facets(conn))

    def _serve_hardware_detail(self, asset_id: str) -> None:
        if not asset_id:
            return self._send_json({"error": "asset_id required"}, status=400)
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            data = iv.hardware_detail(conn, asset_id)
        if data is None:
            return self._send_json({"error": f"asset not found: {asset_id}"}, status=404)
        self._send_json(data)

    def _serve_identity_links(self, params: dict[str, list[str]], is_local: bool) -> None:
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            rows = iv.identity_links_list(
                conn,
                protocol=_opt_str(params, "protocol"),
                privacy_class=_opt_str(params, "privacy_class"),
                q=_opt_str(params, "q"),
                limit=_int_arg(params, "limit", 500),
                is_localhost=is_local,
            )
        self._send_json({"identity_links": rows, "total": len(rows)})

    def _serve_identity_protocols(self) -> None:
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            self._send_json({"protocols": iv.identity_protocols(conn)})

    def _serve_relationships(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            rows = iv.relationships_list(
                conn,
                person=_opt_str(params, "person"),
                rel_type=_opt_str(params, "rel_type"),
                limit=_int_arg(params, "limit", 500),
            )
        self._send_json({"relationships": rows, "total": len(rows)})

    def _serve_search(self, params: dict[str, list[str]]) -> None:
        q = _str_arg(params, "q")
        if not q:
            return self._send_json({"results": [], "total": 0, "q": ""})
        with contextlib.closing(iv.get_db(self._db_path)) as conn:
            rows = iv.search_all(conn, q, limit=_int_arg(params, "limit", 50))
        self._send_json({"results": rows, "total": len(rows), "q": q})


__all__ = ["InventoryHandler", "InventoryAccessor"]
