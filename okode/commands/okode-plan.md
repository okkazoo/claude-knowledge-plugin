---
description: Create an execution plan from oKode analysis
allowed-tools: Bash, Read, Write, Task
---

# oKode Plan

Create a phased execution plan for a task, informed by the code graph.

## Usage

```
/okode-plan <task description>
```

Arguments: $ARGUMENTS

## Behavior

### Step 1: Ensure Synthesis Exists

Check if a recent synthesis report exists for the relevant feature area in
`.okode/synthesis/`. If no relevant synthesis exists, or if the existing one
is older than the most recent graph update:

- Identify which feature area the task relates to
- Run reconcile: `python "${CLAUDE_PLUGIN_ROOT}/skills/okode/scripts/okode_query.py" --reconcile <feature>`
- Wait for the synthesis to complete

### Step 2: Gather Context

Read the following files to build full context:
- `.okode/graph_index.md` — The graph index
- `.okode/synthesis/{feature}_synthesis.md` — The feature synthesis
- `.okode/project_rules.md` — Project-specific rules (if exists)

### Step 3: Spawn Planner Subagent

Use the Task tool to spawn the planner subagent. Provide it with:
- The user's task description: `$ARGUMENTS`
- The feature synthesis report content
- The graph index content
- Project rules (if any)

Read the planner subagent instructions from
``${CLAUDE_PLUGIN_ROOT}/skills/okode/agents/planner.md`` and include them as the Task prompt.

### Step 4: Save and Present Plan

1. Parse the planner's output into a structured plan
2. Generate a plan name from the task description (slugified, e.g., `add-webhook-retry`)
3. Create directory: `.okode/plans/{plan_name}/`
4. Save the plan to: `.okode/plans/{plan_name}/plan.md`
5. Present the plan to the user with:
   - Number of phases
   - Number of tasks per phase
   - Files that will be modified
   - Estimated risk level
6. Ask the user to review and approve
7. Tell the user: "To execute this plan, run `/okode-build {plan_name}`"
