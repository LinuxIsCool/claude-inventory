"""Endpoint smoke tests — boot server, hit each endpoint, check shape."""

from __future__ import annotations

import json
import sys
import time
import threading
import urllib.request
from http.client import HTTPResponse
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_DIR))

import server  # noqa: E402

PORT = 18830  # high port to avoid collision


def _get(path: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # type: HTTPResponse
            body = resp.read().decode("utf-8")
            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype:
                return resp.status, json.loads(body)
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body


def _post(path: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method="POST", data=b"{}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body


def boot_server_in_thread() -> threading.Thread:
    """Start the server in a background thread for endpoint tests."""
    server.SERVER_DB_PATH = server.iv.DEFAULT_DB_PATH
    httpd = server.ThreadingHTTPServer(("127.0.0.1", PORT), server.InventoryHandler)

    def serve():
        httpd.serve_forever()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    # Wait for boot
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=1).read()
            return t
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("server failed to boot")


# ──────────────────────────── tests ────────────────────────────


def test_healthz():
    status, body = _get("/healthz")
    assert status == 200
    assert body["status"] == "ok"
    assert body["asset_count"] >= 1
    assert body["schema_version"] >= 7


def test_overview():
    status, body = _get("/api/overview")
    assert status == 200
    assert "counts" in body
    assert body["counts"]["TOTAL"] >= 1
    assert "privacy_breakdown" in body
    assert body["schema_version"] >= 7


def test_people_list():
    status, body = _get("/api/people")
    assert status == 200
    assert "people" in body
    assert body["total"] >= 0


def test_person_detail():
    status, body = _get("/api/people/person-shawn")
    if status == 404:
        # If shawn not seeded in this DB, skip
        return
    assert status == 200
    assert body["asset_id"] == "person-shawn"
    assert "identity_links" in body
    assert "relationships" in body


def test_person_not_found():
    status, body = _get("/api/people/person-nonexistent-12345")
    assert status == 404
    assert "error" in body


def test_organizations():
    status, body = _get("/api/organizations")
    assert status == 200
    assert "organizations" in body


def test_ventures_active():
    status, body = _get("/api/ventures?stage=active")
    assert status == 200
    assert "ventures" in body
    assert body.get("stage") == "active"


def test_ventures_all():
    status, body = _get("/api/ventures?stage=all")
    assert status == 200
    assert "ventures" in body


def test_hardware():
    status, body = _get("/api/hardware")
    assert status == 200
    assert "hardware" in body
    assert "grouped" in body


def test_identity_links():
    status, body = _get("/api/identity-links")
    assert status == 200
    assert "identity_links" in body
    # No sui-generis row should ever appear
    for il in body["identity_links"]:
        assert il.get("privacy_class") != "indigenous-sui-generis"


def test_identity_links_filter_protocol():
    status, body = _get("/api/identity-links?protocol=email")
    assert status == 200
    assert all(il["protocol"] == "email" for il in body["identity_links"])


def test_identity_protocols():
    status, body = _get("/api/identity-protocols")
    assert status == 200
    assert "protocols" in body


def test_relationships():
    status, body = _get("/api/relationships")
    assert status == 200
    assert "relationships" in body


def test_search():
    status, body = _get("/api/search?q=Carol+Anne")
    assert status == 200
    assert body.get("q") == "Carol Anne"


def test_search_empty_q():
    status, body = _get("/api/search?q=")
    assert status == 200
    assert body.get("results") == []


def test_post_rejected():
    """POST to any endpoint must return 405."""
    status, body = _post("/api/people")
    assert status == 405
    assert body.get("error") if isinstance(body, dict) else "read-only" in body


def test_unknown_path():
    status, body = _get("/api/this-does-not-exist")
    assert status == 404


def test_index_html():
    status, body = _get("/")
    assert status == 200
    # Returns HTML, not JSON
    assert isinstance(body, str)
    assert "<!doctype html>" in body.lower() or "<html" in body.lower()


def test_static_vendor():
    status, body = _get("/vendor/milligram.css")
    assert status == 200


def test_path_traversal_blocked():
    status, body = _get("/vendor/../inventory_data.py")
    # Either 400 (blocked) or 404 (not found after resolution)
    assert status in (400, 404)


if __name__ == "__main__":
    import traceback

    boot_server_in_thread()

    test_funcs = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception:
            failed += 1
            print(f"  ERR  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(test_funcs) - failed}/{len(test_funcs)} passed")
    sys.exit(0 if failed == 0 else 1)
