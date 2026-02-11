---
description: Query the oKode code graph
allowed-tools: Bash, Read
---

# oKode Query

Query the code graph to understand architecture, data flows, and dependencies.

## Usage

```
/okode-query <query_type> [target]
```

Arguments: $ARGUMENTS

## Query Types

| User Command | Flag | Description |
|---|---|---|
| `trace <endpoint>` | `--trace-endpoint <endpoint>` | Full execution chain for an endpoint |
| `contract <collection>` | `--db-contract <collection>` | Who reads/writes this data collection |
| `uses <file\|service>` | `--uses <name>` | Where is this file or service used |
| `does <file\|service>` | `--does <name>` | What does this file or service do |
| `risks` | `--risks` | All external dependencies and env vars |
| `hotspots` | `--hotspots` | Most connected nodes (highest edge count) |
| `dead` | `--dead` | Zero-caller nodes (potential dead code) |
| `reconcile <feature>` | `--reconcile <feature>` | Full feature synthesis report |

## Behavior

1. Parse the query type from the first argument
2. Map user-friendly command names to the corresponding flags listed above
3. Run: `python "${CLAUDE_PLUGIN_ROOT}/skills/okode/scripts/okode_query.py" <mapped_flag> <target>`
4. Display the results in a readable format

### Special: reconcile

The `reconcile` query performs a deep synthesis of an entire feature area:
- Gathers all nodes and edges related to the feature
- Traces every endpoint chain
- Maps all data contracts
- Identifies risks and external dependencies
- Saves the full synthesis report to `.okode/synthesis/{feature}_synthesis.md`
- Displays a summary and tells the user where the full report is saved

## Prerequisites

The graph must exist at `.okode/graph.json`. If it does not exist, instruct
the user to run `/okode-scan --full` first.
