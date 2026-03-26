# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "legion-hooks @ git+https://github.com/LinuxIsCool/legion-plugins.git#subdirectory=packages/legion-hooks",
# ]
# ///
"""KOI capture hook for claude-inventory — pushes asset cards to KOI on write.

Fires on PostToolUse for Write|Edit. Captures inventory asset markdown files
with YAML frontmatter (name, type, status, health, location) to the
legion.claude-inventory namespace.
"""

from pathlib import Path

from legion_hooks.koi import (
    is_under_directory,
    read_hook_stdin,
    extract_file_path,
    parse_yaml_frontmatter,
    compute_hash,
    upsert_bundle,
    log_error,
)

NAMESPACE = "legion.claude-inventory"
TARGET_DIR = Path.home() / ".claude" / "local" / "inventory"


def main():
    hook_data = read_hook_stdin()
    if not hook_data:
        return

    file_path = extract_file_path(hook_data)
    if not file_path:
        return

    # Only process .md files under the inventory directory (assets/**/*.md)
    if not is_under_directory(file_path, TARGET_DIR) or file_path.suffix != ".md":
        return

    try:
        text = file_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return
    if not text.strip():
        return

    frontmatter, body = parse_yaml_frontmatter(text)
    # Use path-relative slug to avoid collisions across asset type subdirs
    try:
        rel = file_path.relative_to(TARGET_DIR.resolve())
        path_slug = str(rel.with_suffix("")).replace("/", "-").replace("\\", "-")
    except ValueError:
        path_slug = file_path.stem
    asset_id = frontmatter.get("id", path_slug)
    slug = asset_id
    rid = f"orn:{NAMESPACE}:{slug}"
    content_hash = compute_hash(text)

    name = frontmatter.get("name", slug)
    asset_type = frontmatter.get("type", "")

    contents = {
        "id": asset_id,
        "name": name,
        "type": asset_type,
        "subtype": frontmatter.get("subtype", ""),
        "status": frontmatter.get("status", ""),
        "location": frontmatter.get("location", ""),
        "health": frontmatter.get("health", None),
        "last_seen": str(frontmatter.get("last_seen", "")),
        "contains_data": frontmatter.get("contains_data", False),
        "data_status": frontmatter.get("data_status", ""),
        "backup_status": frontmatter.get("backup_status", ""),
        "priority": frontmatter.get("priority", ""),
        "next_step": frontmatter.get("next_step", ""),
        "body": body.strip(),
        "file_path": str(file_path),
    }

    search_text = f"{name} {asset_type} {frontmatter.get('location', '')} {frontmatter.get('next_step', '')} {body}".strip()

    try:
        upsert_bundle(NAMESPACE, rid, slug, contents, search_text, content_hash)
    except Exception as exc:
        log_error("inventory", exc)


if __name__ == "__main__":
    main()
