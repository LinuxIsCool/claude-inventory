# claude-inventory webapp v0.1

Read-only HTTP browser over `~/.claude/local/inventory/db/inventory.db`. Backlog 427.

## Launch

```bash
# Default port 8830, localhost-bound, default DB
python ~/.claude/plugins/local/legion-plugins/plugins/claude-inventory/web/server.py

# Custom port
python server.py --port 8831

# Test against fixture DB
python server.py --db /tmp/test.db

# Opt-in remote bind (restricted identity_links auto-mask)
python server.py --bind 0.0.0.0
```

Open `http://localhost:8830/`.

## Tabs

| Tab | Source | Filters |
|---|---|---|
| Overview | counts + privacy + recent additions | none |
| People | `people` JOIN `identity_links` | org, relationship_class, privacy_class, search |
| Organizations | `organizations` | org_type |
| Ventures | `ventures` JOIN `organizations` | lifecycle_stage |
| Hardware | `assets` (drive/machine/mobile/network/venue/peripheral) | asset_type |
| Identity Links | `identity_links` JOIN `assets` | protocol, privacy_class, search |
| Relationships | `relationships` JOIN `assets` (×2) | person |

## Privacy gate

Enforced at `inventory_data.serialize_identity_link()`:

| Class | Localhost | Remote |
|---|---|---|
| `public` | render | render |
| `private` | render | hidden (None) |
| `restricted` | render | masked (first-token-kept) |
| `indigenous-sui-generis` | NEVER render | NEVER render |

Sui-generis rows are dropped at the serializer boundary and never reach JSON output. Tests in `tests/test_privacy_gate.py`.

## Endpoints

| Path | Returns |
|---|---|
| `/` | index.html (SPA shell) |
| `/healthz` | `{status, db_path, schema_version, asset_count}` |
| `/vendor/*` | static assets (milligram.css, app.js, minisearch.js) |
| `/api/overview` | counts + privacy + recent + status |
| `/api/people?org_id=&relationship_class=&privacy_class=&q=&limit=` | people list |
| `/api/people/<asset_id>` | person detail + links + relationships |
| `/api/organizations?type=&limit=` | orgs |
| `/api/ventures?stage=&limit=` | ventures |
| `/api/hardware?type=&limit=` | hardware grouped by type |
| `/api/identity-links?protocol=&privacy_class=&q=&limit=` | identity links |
| `/api/identity-protocols` | protocol counts |
| `/api/relationships?person=&rel_type=&limit=` | edges |
| `/api/search?q=&limit=` | cross-tab search |

## Read-only contract

- DB connection opens with `mode=ro` URI flag + `PRAGMA query_only=1` (belt + braces)
- POST/PUT/DELETE/PATCH return **405** with explanatory JSON
- No mutation endpoints exist in the dispatch table

## Tests

```bash
cd ~/.claude/plugins/local/legion-plugins/plugins/claude-inventory/web
python3 tests/test_privacy_gate.py    # 13/13 — privacy serializer
python3 tests/test_endpoints.py       # 20/20 — endpoint smoke + path traversal
```

## File layout

```
plugins/claude-inventory/web/
├── server.py              ThreadingHTTPServer + 13 GET routes
├── inventory_data.py      Query layer + privacy gate
├── index.html             SPA shell (links to /vendor/app.js)
├── README.md              this file
├── tests/
│   ├── test_privacy_gate.py
│   └── test_endpoints.py
└── vendor/
    ├── app.js             ~520 LOC vanilla JS, 7 tabs
    ├── milligram.css      CSS framework
    ├── minisearch.js      in-browser FTS (reserved for v0.2)
    └── *-LICENSE.txt
```

## Cross-references

- Backlog: `~/.claude/local/backlog/427-inventory-webapp-v01-stub.md`
- Reference impl: `~/.claude/plugins/local/legion-plugins/plugins/claude-youtube/web/`
- DB: `~/.claude/local/inventory/db/inventory.db`
- Migration: `~/.claude/local/inventory/migrations/0007_relations_extension.sql`

## v0.2 candidates (not yet shipped)

- D3 force-directed relationship graph
- Observation sparklines (after backlog 423 sensor cron lands)
- systemd user unit for auto-launch
- Mutation endpoints behind localhost+csrf (v0.3)
- Federated view across fleet (v0.4)
