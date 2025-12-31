# Knowledge Base Plugin for Claude Code

Persistent knowledge management for Claude Code projects with work-in-progress tracking, checkpoints, and auto-indexing.

## Features

- **Work-in-Progress Tracking**: Save progress between sessions with `/knowledge-base:wip`
- **Checkpoints**: Create restore points before risky changes
- **Auto-Indexing**: Code symbols and knowledge automatically indexed
- **Pre-Search Context**: Knowledge surfaced before searches via hooks

## Installation

```bash
# Add marketplace
/plugin marketplace add okkazoo/claude-knowledge-plugin

# Install plugin
/plugin install knowledge-base@claude-knowledge-plugin
```

## Commands

| Command | Description |
|---------|-------------|
| `/knowledge-base:init` | Initialize knowledge base in current project |
| `/knowledge-base:wip` | Save work-in-progress |
| `/knowledge-base:wip -f <text>` | Save a fact directly |
| `/knowledge-base:wip -list` | List existing journeys |
| `/knowledge-base:checkpoint [desc]` | Create restore point |
| `/knowledge-base:knowledge` | Show knowledge base status |
| `/knowledge-base:knowledge -reset` | Reset knowledge base |

## Hooks

- **session-start**: Injects git status and active journeys on startup
- **pre-search**: Searches indexes before Grep/Glob, surfaces relevant patterns
- **auto-index**: Updates code symbol index after file edits

## Directory Structure

After running `/knowledge-base:init`:

```
.claude/knowledge/
├── journey/      # Work-in-progress entries
├── facts/        # Quick facts, gotchas
├── patterns/     # Extracted solutions
├── checkpoints/  # State snapshots
├── versions/     # Version history
├── coderef.json  # Code symbol index
└── knowledge.json # Knowledge index
```

## Quick Start

1. Install the plugin
2. Run `/knowledge-base:init` in your project
3. Use `/knowledge-base:wip` to save progress as you work
4. Use `/knowledge-base:checkpoint` before risky changes

## Authors

- OKKazoo

## License

MIT
