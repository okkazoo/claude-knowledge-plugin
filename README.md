# Knowledge Base Plugin for Claude Code

Persistent knowledge management for Claude Code projects with work-in-progress tracking, checkpoints, and auto-indexing.

## Features

- **Work-in-Progress Tracking**: Save progress between sessions with `/ok:wip`
- **Checkpoints**: Create restore points before risky changes
- **Auto-Indexing**: Code symbols and knowledge automatically indexed
- **Pre-Search Context**: Knowledge surfaced before searches via hooks
- **Version Management**: Automatic version bumping and changelog

## Installation

```bash
# Add marketplace
/plugin marketplace add okkazoo/claude-knowledge-plugin

# Install plugin
/plugin install ok@okkazoo/claude-knowledge-plugin
```

Or run locally:
```bash
claude --plugin-dir ~/Documents/Dev/claude-knowledge-plugin
```

## Commands

| Command | Description |
|---------|-------------|
| `/ok:init` | Initialize knowledge base in current project |
| `/ok:wip` | Save work-in-progress (auto-detects topics) |
| `/ok:wip -f <text>` | Save a fact directly |
| `/ok:checkpoint [desc]` | Create restore point with auto-versioning |
| `/ok:knowledge` | Show knowledge base status |
| `/ok:version` | Show current version |
| `/ok:version -patch\|-minor\|-major` | Bump version and update changelog |
| `/ok:setup` | Bootstrap CLAUDE.md for new projects |

## Hooks

- **session-start**: Injects git status and active journeys on startup
- **pre-search**: Searches indexes before Grep/Glob, surfaces relevant patterns
- **pre-read**: Warns when reading large files without offset/limit
- **auto-index**: Updates code symbol index after file edits

## Skills

- **knowledge-search**: Always search knowledge base before starting work
- **context-manager**: Handle large files efficiently, reduce context bloat
- **code-patterns**: Project coding conventions and examples

## Recommended Built-in Agents

Use these Claude Code built-in agents (via Task tool) for common tasks:

| Task | Built-in Agent | Usage |
|------|---------------|-------|
| Codebase exploration | `Explore` | "Find all API endpoints", "How does auth work?" |
| Implementation planning | `Plan` | Design approach before coding |
| Feature architecture | `feature-dev:code-architect` | Design new feature structure |
| Code analysis | `feature-dev:code-explorer` | Trace execution paths, map dependencies |
| Code review | `feature-dev:code-reviewer` | Review changes for bugs/issues |
| General tasks | `general-purpose` | Multi-step tasks with full tool access |

Example:
```
Task(subagent_type="Explore", prompt="Find all error handling patterns")
Task(subagent_type="Plan", prompt="Plan implementation for user auth")
```

## Directory Structure

After running `/ok:init`:

```
.claude/knowledge/
├── journey/      # Work-in-progress entries
├── facts/        # Quick facts, gotchas
├── patterns/     # Extracted solutions
├── checkpoints/  # State snapshots
├── versions/     # CHANGELOG.md
├── coderef.json  # Code symbol index
└── knowledge.json # Knowledge index
```

## Quick Start

1. Install the plugin
2. Run `/ok:init` in your project
3. Use `/ok:wip` to save progress as you work
4. Use `/ok:checkpoint` before risky changes

## Authors

- OKKazoo

## License

MIT
