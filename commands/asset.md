---
description: "Create or update an inventory asset"
argument-hint: "<name> [--type machine|drive|mobile|network|venue|service]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill]
---

# /asset

Create or update an inventory asset.

## Usage

Parse the argument to extract:
1. **name** — the asset's display name (required)
2. **--type** — asset type (optional, will ask if not provided)

Invoke @asset-writer with the parsed arguments.

## Examples

- `/asset "Lenovo Legion T5" --type machine`
- `/asset "24TB Expansion Drive" --type drive`
- `/asset "Salt Spring Gallery" --type venue`
- `/asset "Tailscale Mesh" --type network`

## Workflow

1. Parse name and --type from arguments
2. If --type missing, ask user which type
3. Delegate to @asset-writer subskill
4. @asset-writer handles slug generation, template, file creation
