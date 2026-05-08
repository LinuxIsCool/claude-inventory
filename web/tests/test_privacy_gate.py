"""Privacy gate tests — sui-generis must NEVER reach JSON output."""

from __future__ import annotations

import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_DIR))

import inventory_data as iv  # noqa: E402


def test_sui_generis_hard_reject_localhost():
    """Sui-generis MUST be rejected even on localhost."""
    row = {
        "privacy_class": "indigenous-sui-generis",
        "identifier": "secret-rid",
        "protocol": "rid",
    }
    assert iv.serialize_identity_link(row, is_localhost=True) is None
    assert iv.serialize_identity_link(row, is_localhost=False) is None


def test_sui_generis_hard_reject_in_list():
    """A list containing sui-generis must drop it, not error."""
    rows = [
        {"privacy_class": "public", "identifier": "did:key:z6Mk", "protocol": "did"},
        {"privacy_class": "indigenous-sui-generis", "identifier": "secret", "protocol": "rid"},
        {"privacy_class": "private", "identifier": "user@x.com", "protocol": "email"},
    ]
    out = iv.serialize_identity_links(rows, is_localhost=True)
    assert len(out) == 2
    assert all(r["privacy_class"] != "indigenous-sui-generis" for r in out)


def test_public_passthrough_localhost():
    row = {"privacy_class": "public", "identifier": "did:key:z6Mk", "protocol": "did"}
    out = iv.serialize_identity_link(row, is_localhost=True)
    assert out is not None
    assert out["identifier"] == "did:key:z6Mk"
    assert "_masked" not in out


def test_public_passthrough_remote():
    row = {"privacy_class": "public", "identifier": "did:key:z6Mk", "protocol": "did"}
    out = iv.serialize_identity_link(row, is_localhost=False)
    assert out is not None
    assert out["identifier"] == "did:key:z6Mk"


def test_private_passthrough_localhost():
    row = {"privacy_class": "private", "identifier": "eve@x.com", "protocol": "email"}
    out = iv.serialize_identity_link(row, is_localhost=True)
    assert out is not None
    assert out["identifier"] == "eve@x.com"


def test_private_hidden_remote():
    """Private rows must be hidden on non-localhost, not masked."""
    row = {"privacy_class": "private", "identifier": "eve@x.com", "protocol": "email"}
    assert iv.serialize_identity_link(row, is_localhost=False) is None


def test_restricted_passthrough_localhost():
    row = {
        "privacy_class": "restricted",
        "identifier": "cahilton@indigenomics.com",
        "protocol": "email",
    }
    out = iv.serialize_identity_link(row, is_localhost=True)
    assert out is not None
    assert out["identifier"] == "cahilton@indigenomics.com"
    assert "_masked" not in out


def test_restricted_masked_remote_email():
    """Restricted email on remote: keep first char + domain, mask local part."""
    row = {
        "privacy_class": "restricted",
        "identifier": "cahilton@indigenomics.com",
        "protocol": "email",
    }
    out = iv.serialize_identity_link(row, is_localhost=False)
    assert out is not None
    assert out["_masked"] is True
    assert out["identifier"].startswith("c")
    assert out["identifier"].endswith("@indigenomics.com")
    assert "*" in out["identifier"]


def test_restricted_masked_remote_phone():
    """Restricted phone on remote: keep first 5 chars (country+area), mask rest."""
    row = {
        "privacy_class": "restricted",
        "identifier": "+12505551234",
        "protocol": "phone",
    }
    out = iv.serialize_identity_link(row, is_localhost=False)
    assert out is not None
    assert out["_masked"] is True
    assert out["identifier"].startswith("+1250")
    assert "*" in out["identifier"]


def test_restricted_masked_remote_handle():
    """Restricted handle on remote: keep first 2 chars, mask rest."""
    row = {
        "privacy_class": "restricted",
        "identifier": "darren_handle",
        "protocol": "telegram",
    }
    out = iv.serialize_identity_link(row, is_localhost=False)
    assert out is not None
    assert out["_masked"] is True
    assert out["identifier"].startswith("da")
    assert "*" in out["identifier"]


def test_empty_row_handled():
    assert iv.serialize_identity_link({}, is_localhost=True) == {}


def test_serialize_list_with_only_sui_generis_returns_empty():
    rows = [
        {"privacy_class": "indigenous-sui-generis", "identifier": "x", "protocol": "rid"},
        {"privacy_class": "indigenous-sui-generis", "identifier": "y", "protocol": "rid"},
    ]
    out = iv.serialize_identity_links(rows, is_localhost=True)
    assert out == []


def test_mask_short_identifier():
    """Identifier ≤4 chars masks all."""
    masked = iv._mask_identifier("abc", "telegram")
    assert masked == "***"
    masked4 = iv._mask_identifier("abcd", "telegram")
    assert masked4 == "****"


if __name__ == "__main__":
    import traceback

    test_funcs = [
        v for k, v in globals().items()
        if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except Exception:
            failed += 1
            print(f"  FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(test_funcs) - failed}/{len(test_funcs)} passed")
    sys.exit(0 if failed == 0 else 1)
