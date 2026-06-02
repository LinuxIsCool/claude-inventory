"""InventoryAccessor — implements claude_webui.accessor.Accessor Protocol.

Read-only adapter over the claude-inventory SQLite mirror (inventory.db).
Used by ``InventoryKernel`` for Platform mount (Mode B at :8800/inventory/).
Mode A standalone (:8830/) still goes through the legacy InventoryHandler
in server.py — both read the same DB via inventory_data.py.

The Accessor's five methods are the contract floor the kernel requires
(``isinstance(accessor, Accessor)`` is runtime-checked at construction).
Inventory's rich routes (/api/people, /api/hardware, ...) live in
InventoryHandler; the generic /api/list, /api/stats, /api/feed, /api/detail
map here to the asset (hardware) surface. ``healthz()`` is the load-bearing
one — claude-home reads ``stats.key_metric`` to render the hub card.
"""
from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Any

import inventory_data as iv

__all__ = ["InventoryAccessor"]

NAMESPACE = "legion.claude-inventory"


class InventoryAccessor:
    """5-method Accessor Protocol over the claude-inventory SQLite mirror."""

    slug = "inventory"
    title = "Inventory"
    namespace = NAMESPACE

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path: Path = (
            Path(db_path).expanduser().resolve()
            if db_path
            else iv.DEFAULT_DB_PATH
        )

    # ── Accessor Protocol ──────────────────────────────────────────────

    def list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:  # noqa: A003
        """Generic asset (hardware) list. Backs /api/list."""
        params = params or {}
        started = time.perf_counter()
        with contextlib.closing(iv.get_db(self.db_path)) as conn:
            rows = iv.hardware_list(
                conn,
                asset_type=params.get("type") or None,
                q=params.get("q") or None,
                status=params.get("status") or None,
                location=params.get("location") or None,
                internality=params.get("internality") or None,
                limit=_clamp_int(params.get("limit"), 500, 1000),
            )
        return {
            "items": rows,
            "total": len(rows),
            "data_ms": (time.perf_counter() - started) * 1000,
        }

    def detail(self, item_id: str) -> dict[str, Any] | None:
        """Single asset detail. Backs /api/detail/<id>."""
        if not item_id:
            return None
        with contextlib.closing(iv.get_db(self.db_path)) as conn:
            return iv.hardware_detail(conn, item_id)

    def stats(self) -> dict[str, Any]:
        """Inventory overview counts. Backs /api/stats + /api/overview."""
        with contextlib.closing(iv.get_db(self.db_path)) as conn:
            data = iv.overview(conn)
        data["timestamp"] = time.time()
        return data

    def feed(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Recent assets feed. Backs /api/feed."""
        params = params or {}
        started = time.perf_counter()
        with contextlib.closing(iv.get_db(self.db_path)) as conn:
            rows = iv.hardware_list(
                conn,
                limit=_clamp_int(params.get("limit"), 20, 200),
            )
        return {
            "items": rows,
            "data_ms": (time.perf_counter() - started) * 1000,
        }

    def healthz(self) -> dict[str, Any]:
        """Health probe — DB reachability + key metric for the hub card.

        Conforms to the claude-webui contract shape consumed by
        claude-home: {ok, namespace, stats: {key_metric, key_metric_label}}.
        Retains the legacy inventory healthz fields for back-compat.
        """
        try:
            with contextlib.closing(iv.get_db(self.db_path)) as conn:
                legacy = iv.healthz(conn, self.db_path)
            asset_count = int(legacy.get("asset_count", 0))
            return {
                "ok": bool(legacy.get("ok", True)),
                "namespace": self.namespace,
                "error": None,
                "stats": {
                    "key_metric": asset_count,
                    "key_metric_label": "assets",
                },
                **legacy,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "namespace": self.namespace,
                "error": str(exc),
                "stats": {"key_metric": 0, "key_metric_label": "assets"},
            }


def _clamp_int(value: Any, default: int, max_value: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, max_value))
