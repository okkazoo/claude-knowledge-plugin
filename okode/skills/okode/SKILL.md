---
name: okode
description: >
  Living code graph system for deep codebase understanding.
  Use /okode-scan to build the graph, /okode-query to query it,
  /okode-plan to create execution plans, /okode-build to execute them.
  The graph is auto-updated via hooks as code changes.
---

# oKode — Code Intelligence

oKode maintains a living graph of your codebase's runtime relationships.
Instead of exploring files to understand architecture, query the graph.

## Quick Start
- `/okode-scan --full` — First-time full scan
- `/okode-query reconcile <feature>` — Deep analysis of a feature
- `/okode-plan <task description>` — Create execution plan
- `/okode-build <plan_name>` — Execute with builder/validator agents

## How It Works
The graph maps every endpoint, service, task, collection, and external API
in your project, along with all the relationships between them (reads,
writes, calls, enqueues, publishes). This means you can ask "what happens
when someone hits POST /api/analyze" and get the full chain without
reading a single source file.

## Context Savings
The graph index (~200 lines) replaces what would otherwise require
reading 20-50 source files to understand. Frontmatter on each file
means opening a file immediately tells you its relationships without
parsing the implementation.

## When To Use
- Before making changes: `/okode-query reconcile <feature>`
- Finding dead code: `/okode-query dead`
- Understanding data flow: `/okode-query contract <collection>`
- Planning refactors: `/okode-plan <description>`
- Executing plans safely: `/okode-build <plan_name>`
