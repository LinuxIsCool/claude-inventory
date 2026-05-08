---
description: "Launch the read-only inventory webapp (port 8830) and open browser"
argument-hint: "[--port N] [--db PATH] [--bind ADDR] [stop]"
allowed-tools: [Bash, Read]
---

# /inventory-web

Launch the read-only inventory webapp v0.1 (backlog 427).

## Behavior

1. Check whether server already running (`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8830/healthz`)
2. If not running, launch in background with `nohup python web/server.py &`
3. Wait until `/healthz` returns 200 (max 10s)
4. Open browser via `xdg-open http://127.0.0.1:8830/`
5. Print the URL + db path + asset count

## Arguments

- No args → start server (or attach to existing) and open browser
- `--port N` → use a non-default port (default 8830)
- `--db PATH` → override DB path (default `~/.claude/local/inventory/db/inventory.db`)
- `--bind ADDR` → bind address (default `127.0.0.1`); pass `0.0.0.0` to opt-in to remote bind (restricted identity_links auto-mask)
- `stop` → kill any running server bound to localhost on the configured port

## Implementation hints

- Start command: `nohup python ~/.claude/plugins/local/legion-plugins/plugins/claude-inventory/web/server.py [args] > /tmp/inventory-web.log 2>&1 &`
- PID file: `/tmp/inventory-web.pid` (write `$!` after launch)
- Stop: `pkill -f "claude-inventory/web/server.py"` or read PID from `/tmp/inventory-web.pid`
- Probe: `curl -s http://127.0.0.1:${PORT}/healthz`

## Privacy reminder

The webapp respects the privacy gate in `inventory_data.serialize_identity_link()`. Sui-generis identity_links are hard-rejected and never reach the browser. Restricted rows mask the local part on remote bind. See `web/README.md` and backlog 427 §6 for the full doctrine.

## Cross-references

- Backlog: `~/.claude/local/backlog/427-inventory-webapp-v01-stub.md`
- Server: `~/.claude/plugins/local/legion-plugins/plugins/claude-inventory/web/server.py`
- README: `~/.claude/plugins/local/legion-plugins/plugins/claude-inventory/web/README.md`
- Tests: `~/.claude/plugins/local/legion-plugins/plugins/claude-inventory/web/tests/`
