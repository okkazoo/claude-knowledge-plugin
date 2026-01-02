# Knowledge Base Plugin for Claude Code

Persistent knowledge management for Claude Code projects with work-in-progress tracking, save points, and auto-indexing.

## Features

- **Work-in-Progress Tracking**: Save progress between sessions with `/ok-know:wip`
- **Save Points**: Create restore points before risky changes
- **Auto-Indexing**: Code symbols and knowledge automatically indexed
- **Pre-Search Context**: Knowledge surfaced before searches via hooks

## Installation

### From Marketplace (Recommended)

```bash
# Add the marketplace (one-time setup)
/plugins marketplace add okkazoo/ok-claude-plugins

# Install the plugin
/plugins install ok-know
```

### From Local Source

If you're developing or testing the plugin locally:

```bash
# Option 1: Run Claude with the plugin directory
claude --plugin-dir /path/to/claude-knowledge-plugin

# Option 2: Install locally for persistent use
/plugins install /path/to/claude-knowledge-plugin
```

**Important:** The plugin must be installed before running `/ok-know:init`. The init command reads from Claude's plugin registry (`~/.claude/plugins/installed_plugins.json`) to locate the helper scripts.

## Commands

| Command | Description |
|---------|-------------|
| `/ok-know:init` | Initialize knowledge base in current project |
| `/ok-know:wip` | Save work-in-progress (auto-detects topics) |
| `/ok-know:wip -f <text>` | Save a fact directly |
| `/ok-know:save [desc]` | Create restore point before risky changes |
| `/ok-know:knowledge` | Show knowledge base status |
| `/ok-know:setup` | Bootstrap CLAUDE.md for new projects |

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

After running `/ok-know:init`:

```
.claude/knowledge/
├── journey/      # Work-in-progress entries
├── facts/        # Quick facts, gotchas
├── patterns/     # Extracted solutions
├── savepoints/   # State snapshots
├── coderef.json  # Code symbol index
└── knowledge.json # Knowledge index
```

## Quick Start

1. **Install the plugin** (see Installation above)
2. **Navigate to your project** directory in Claude Code
3. **Run `/ok-know:init`** to set up the knowledge base structure
4. **Use `/ok-know:wip`** to save progress as you work
5. **Use `/ok-know:save`** before risky changes

### Troubleshooting

**"Could not find ok-know plugin"** - The plugin isn't installed. Run `/plugins install ok-know` first.

**Helper script not copied** - If `/ok-know:init` completes but the helper script is missing, check that:
- The plugin is in the registry: `cat ~/.claude/plugins/installed_plugins.json | grep ok-know`
- Python 3 is available (used to parse the registry)

## Authors

- OKKazoo

## License

MIT
