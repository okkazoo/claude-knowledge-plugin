---
description: Build or update the oKode code graph
allowed-tools: Bash, Read, Write
---

# oKode Scan

Full or incremental codebase scan to build/update the code graph.

## Usage

```
/okode-scan [--full|--feature <name>|--incremental]
```

Arguments: $ARGUMENTS

## Behavior

1. Run the scanner: `python "${CLAUDE_PLUGIN_ROOT}/skills/okode/scripts/okode_scan.py" $ARGUMENTS`
2. With `--full`: Scan entire project, rebuild graph from scratch
3. With `--feature <name>`: Scope scan to a specific feature directory
4. With `--incremental` (default): Only scan files changed since last scan
5. Display summary of nodes/edges found
6. Regenerate the graph index at `.okode/graph_index.md`

If no arguments are provided, default to `--incremental` if a graph already exists
at `.okode/graph.json`, otherwise default to `--full`.

## Post-Scan

After scanning completes:
- Report the number of nodes and edges discovered
- Report any new nodes or removed nodes compared to previous scan
- If frontmatter injection is enabled, update file frontmatter for changed files
- Commit the updated graph files if the user has auto-commit enabled

## Troubleshooting

If the scan script is not found, inform the user they need to run the oKode
setup first. The scanner requires Python 3.8+ and no external dependencies
beyond the standard library.
