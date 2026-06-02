#!/usr/bin/env python3
"""Claude Inventory webapp — read-only browser over inventory.db.

Pattern mirrors claude-youtube/web/server.py. Single ThreadingHTTPServer,
8 GET routes, no mutations. Privacy gate enforced at serializer boundary
in inventory_data.py. Sui-generis identity_links never reach JSON output.

Usage:
  python web/server.py
  python web/server.py --port 8831
  python web/server.py --db /tmp/test.db
  python web/server.py --bind 0.0.0.0    # opt-in to remote bind
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

import inventory_data as iv  # noqa: E402

DEFAULT_PORT = 8830
MAX_LIMIT = 1000

# Configured at startup
SERVER_DB_PATH: Path = iv.DEFAULT_DB_PATH
SERVER_BIND: str = "127.0.0.1"


# ──────────────────────────── arg helpers (claude-youtube pattern) ────────────────────────────


def _int_arg(params: dict[str, list[str]], key: str, default: int, max_value: int = MAX_LIMIT) -> int:
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


# ──────────────────────────── handler ────────────────────────────


class InventoryHandler(BaseHTTPRequestHandler):
    """Read-only request handler. Rejects POST/PUT/DELETE/PATCH with 405."""

    server_version = "ClaudeInventory/0.1"

    # Suppress default per-request stderr logging in noisy envs
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def _is_localhost(self) -> bool:
        # Trust the connection's source IP, not headers
        client_ip = self.client_address[0]
        return client_ip in {"127.0.0.1", "::1", "localhost"}

    # ───── routing ─────

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._dispatch_get()
        except FileNotFoundError as e:
            self._send_json({"error": str(e)}, status=404)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"ERROR {self.path}: {e!r}\n")
            self._send_json({"error": f"{type(e).__name__}: {e}"}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        self._send_json({"error": "read-only webapp; mutations not supported"}, status=405)

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json({"error": "read-only webapp; mutations not supported"}, status=405)

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json({"error": "read-only webapp; mutations not supported"}, status=405)

    def do_PATCH(self) -> None:  # noqa: N802
        self._send_json({"error": "read-only webapp; mutations not supported"}, status=405)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.end_headers()

    # ───── dispatch ─────

    def _dispatch_get(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query, keep_blank_values=True)
        path = parsed.path
        is_local = self._is_localhost()

        if path == "/" or path == "/index.html":
            return self._serve_index()
        if path == "/healthz":
            return self._serve_healthz()
        if path.startswith("/static/") or path.startswith("/vendor/"):
            return self._serve_static(path)

        # APIs
        if path == "/api/overview":
            return self._serve_overview()
        if path == "/api/people":
            return self._serve_people(params)
        if path.startswith("/api/people/"):
            asset_id = path[len("/api/people/"):].strip("/")
            return self._serve_person(asset_id, is_local)
        if path == "/api/organizations":
            return self._serve_organizations(params)
        if path == "/api/ventures":
            return self._serve_ventures(params)
        if path == "/api/hardware":
            return self._serve_hardware(params)
        if path == "/api/hardware/facets":
            return self._serve_hardware_facets()
        if path.startswith("/api/hardware/"):
            asset_id = path[len("/api/hardware/"):].strip("/")
            return self._serve_hardware_detail(asset_id)
        if path == "/api/identity-links":
            return self._serve_identity_links(params, is_local)
        if path == "/api/identity-protocols":
            return self._serve_identity_protocols()
        if path == "/api/relationships":
            return self._serve_relationships(params)
        if path == "/api/search":
            return self._serve_search(params)

        self._send_json({"error": f"unknown path: {path}"}, status=404)

    # ───── route handlers ─────

    def _serve_index(self) -> None:
        index_path = WEB_DIR / "index.html"
        if not index_path.exists():
            return self._send_json({"error": "index.html not found"}, status=500)
        body = index_path.read_bytes()
        self._send_bytes(body, content_type="text/html; charset=utf-8")

    def _serve_static(self, path: str) -> None:
        """Serve files from vendor/ only. Reject any traversal that escapes."""
        rel = path.lstrip("/")
        # Both /static/* and /vendor/* alias to the vendor directory
        if rel.startswith("static/"):
            rel = "vendor/" + rel[len("static/"):]
        # Reject any reference to source files
        vendor_root = (WEB_DIR / "vendor").resolve()
        candidate = (WEB_DIR / rel).resolve()
        try:
            candidate.relative_to(vendor_root)
        except ValueError:
            return self._send_json({"error": "path traversal blocked"}, status=400)
        if not candidate.exists() or not candidate.is_file():
            return self._send_json({"error": f"not found: {path}"}, status=404)
        ctype, _ = mimetypes.guess_type(str(candidate))
        ctype = ctype or "application/octet-stream"
        body = candidate.read_bytes()
        # During v0.x development we want fast iteration without stale browser
        # caches across restyles. Promote to max-age=3600 once UI stabilizes.
        self._send_bytes(
            body,
            content_type=ctype,
            cache_control="no-cache, must-revalidate",
        )

    def _serve_healthz(self) -> None:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            data = iv.healthz(conn, SERVER_DB_PATH)
        self._send_json(data)

    def _serve_overview(self) -> None:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            data = iv.overview(conn)
        self._send_json(data)

    def _serve_people(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
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
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            person = iv.person_detail(conn, asset_id, is_localhost=is_local)
        if person is None:
            return self._send_json({"error": f"person not found: {asset_id}"}, status=404)
        self._send_json(person)

    def _serve_organizations(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            rows = iv.organizations_list(
                conn,
                org_type=_opt_str(params, "type"),
                limit=_int_arg(params, "limit", 200),
            )
        self._send_json({"organizations": rows, "total": len(rows)})

    def _serve_ventures(self, params: dict[str, list[str]]) -> None:
        stage = _str_arg(params, "stage", "active") or None
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            rows = iv.ventures_list(
                conn,
                stage=stage,
                limit=_int_arg(params, "limit", 200),
            )
        self._send_json({"ventures": rows, "total": len(rows), "stage": stage})

    def _serve_hardware(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            rows = iv.hardware_list(
                conn,
                asset_type=_opt_str(params, "type"),
                q=_opt_str(params, "q"),
                status=_opt_str(params, "status"),
                location=_opt_str(params, "location"),
                internality=_opt_str(params, "internality"),
                limit=_int_arg(params, "limit", 500),
            )
        # Group by asset_type for tab convenience
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(r["asset_type"], []).append(r)
        # Summary stats — count + total/free capacity across filtered drives
        total_bytes = 0
        free_bytes = 0
        used_bytes = 0
        connected = 0
        drive_count = 0
        for r in rows:
            if r.get("asset_type") != "drive":
                continue
            drive_count += 1
            if r.get("connected"):
                connected += 1
            cap = r.get("capacity") or {}
            t = cap.get("total_bytes") or cap.get("size_bytes") or 0
            u = cap.get("used_bytes") or 0
            f = cap.get("free_bytes") or 0
            try:
                total_bytes += int(t)
                used_bytes += int(u)
                free_bytes += int(f)
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
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            data = iv.hardware_facets(conn)
        self._send_json(data)

    def _serve_hardware_detail(self, asset_id: str) -> None:
        if not asset_id:
            return self._send_json({"error": "asset_id required"}, status=400)
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            data = iv.hardware_detail(conn, asset_id)
        if data is None:
            return self._send_json({"error": f"asset not found: {asset_id}"}, status=404)
        self._send_json(data)

    def _serve_identity_links(self, params: dict[str, list[str]], is_local: bool) -> None:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
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
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            rows = iv.identity_protocols(conn)
        self._send_json({"protocols": rows})

    def _serve_relationships(self, params: dict[str, list[str]]) -> None:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
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
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            rows = iv.search_all(conn, q, limit=_int_arg(params, "limit", 50))
        self._send_json({"results": rows, "total": len(rows), "q": q})

    # ───── response helpers ─────

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
        self._send_bytes(
            body,
            content_type="application/json; charset=utf-8",
            status=status,
            cache_control="no-store",
        )

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: int = 200,
        cache_control: str = "no-store",
    ) -> None:
        accept_encoding = (self.headers.get("Accept-Encoding") or "").lower()
        encoded_body = body
        encoding_header: str | None = None
        if "gzip" in accept_encoding and len(body) > 1024:
            encoded_body = gzip.compress(body)
            encoding_header = "gzip"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded_body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        if encoding_header:
            self.send_header("Content-Encoding", encoding_header)
        self.end_headers()
        try:
            self.wfile.write(encoded_body)
        except BrokenPipeError:
            pass


# ──────────────────────────── Mode B kernel factory ────────────────────────────
#
# build_kernel() lets the claude-webui Platform mount inventory at
# :8800/inventory/ alongside the other surfacing/capture substrates. The
# kernel path uses InventoryAccessor + InventoryHandler (kernel-pattern);
# the legacy standalone main() below still uses the in-file InventoryHandler
# at :8830/. Both read the same inventory.db via inventory_data.py.
#
# Imports are lazy (inside build_kernel) so Mode A standalone — launched as
# `python web/server.py`, where claude_webui is NOT on sys.path — keeps
# working without the shell installed.


def build_kernel(port: int = DEFAULT_PORT, bind: str = "127.0.0.1"):
    """Construct (don't start) the inventory kernel for Platform mounting.

    Mirrors the claude-youtube/claude-voice build_kernel() factory contract
    the Platform bootstrap (scripts/webui_platform.py) calls with port=0.
    """
    from claude_webui.kernel import WebuiKernel

    from inventory_accessor import InventoryAccessor
    from inventory_handler import InventoryHandler

    class InventoryKernel(WebuiKernel):
        """claude-inventory webui kernel — read-only over inventory.db."""

        slug = "inventory"
        title = "Inventory"

        def _make_handler_class(self) -> type:
            accessor = self.accessor
            static_dir = self.static_dir
            event_bus = self._event_bus
            mutation_catalog = self._mutation_catalog

            class _Handler(InventoryHandler):
                pass

            _Handler.accessor = accessor  # type: ignore[assignment]
            _Handler.static_dir = static_dir
            _Handler.event_bus = event_bus
            _Handler.mutation_catalog = mutation_catalog
            return _Handler

    return InventoryKernel(
        accessor=InventoryAccessor(db_path=SERVER_DB_PATH),
        port=port,
        bind=bind,
        static_dir=WEB_DIR,
    )


# ──────────────────────────── entrypoint ────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Claude Inventory webapp (read-only)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default: {DEFAULT_PORT})")
    p.add_argument(
        "--bind",
        default="127.0.0.1",
        help="bind address (default: 127.0.0.1; pass 0.0.0.0 to opt-in remote bind)",
    )
    p.add_argument(
        "--db",
        default=str(iv.DEFAULT_DB_PATH),
        help=f"path to inventory.db (default: {iv.DEFAULT_DB_PATH})",
    )
    return p.parse_args()


def main() -> int:
    global SERVER_DB_PATH, SERVER_BIND  # noqa: PLW0603
    args = parse_args()
    SERVER_DB_PATH = Path(args.db).expanduser().resolve()
    SERVER_BIND = args.bind

    if not SERVER_DB_PATH.exists():
        sys.stderr.write(f"ERROR: db not found at {SERVER_DB_PATH}\n")
        return 1

    # Smoke-check that schema responds
    try:
        with contextlib.closing(iv.get_db(SERVER_DB_PATH)) as conn:
            health = iv.healthz(conn, SERVER_DB_PATH)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"ERROR: db smoke-check failed: {e!r}\n")
        return 1

    if SERVER_BIND not in {"127.0.0.1", "::1", "localhost"}:
        sys.stderr.write(
            "WARNING: binding to a non-localhost address.\n"
            "         Restricted identity_links will be masked, but verify privacy guarantees.\n"
        )

    server = ThreadingHTTPServer((SERVER_BIND, args.port), InventoryHandler)
    sys.stderr.write(
        f"claude-inventory webapp listening on http://{SERVER_BIND}:{args.port}/\n"
        f"  db: {SERVER_DB_PATH}\n"
        f"  schema: v{health['schema_version']}, assets: {health['asset_count']}\n"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nshutting down\n")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
