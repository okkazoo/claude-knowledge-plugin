---
description: Execute an oKode plan with builder/validator agents
allowed-tools: Bash, Read, Write, Task, Edit
---

# oKode Build

Execute a previously created plan using builder and validator subagents.

## Usage

```
/okode-build <plan_name>
```

Arguments: $ARGUMENTS

## Behavior

### Step 1: Load Plan

1. Extract the plan name from the first argument: `$ARGUMENTS`
2. Load the plan from `.okode/plans/{plan_name}/plan.md`
3. If the plan does not exist, list available plans from `.okode/plans/` and ask the user to specify one
4. Create the agent output workspace: `.okode/plans/{plan_name}/agent-outputs/`

### Step 2: Read Graph Context

Read the following for builder/validator context:
- `.okode/graph_index.md`
- `.okode/project_rules.md` (if exists)
- The relevant synthesis report referenced in the plan

### Step 3: Execute Phases (Sequential)

For each phase in the plan, execute sequentially:

#### For Each Task in a Phase (Parallel Where Possible)

Use the Task tool to run tasks within a phase in parallel when they have no
file dependencies on each other.

**Builder Stage:**
1. Read builder subagent instructions from ``${CLAUDE_PLUGIN_ROOT}/skills/okode/agents/builder.md``
2. Spawn builder subagent via Task tool with:
   - Task description from the plan
   - List of files to modify
   - Graph context (relevant node/edge data for those files)
   - Acceptance criteria from the plan
   - Project rules
3. Builder writes output to `.okode/plans/{plan_name}/agent-outputs/phase-{n}/task-{m}/`

**Validator Stage:**
4. Read validator subagent instructions from ``${CLAUDE_PLUGIN_ROOT}/skills/okode/agents/validator.md``
5. Spawn validator subagent via Task tool with:
   - Original task description
   - Acceptance criteria
   - Builder's `changes.md` and `issues.md`
   - Graph context
   - The actual modified files (re-read them)
6. Validator writes `validation.md` to the same output directory

**Retry Logic:**
7. If validator returns FAIL:
   - Feed validation feedback back to a new builder subagent instance
   - Re-validate (max 3 retries per task)
   - If still failing after 3 retries, mark task as BLOCKED and continue
8. If validator returns PASS:
   - Mark task as COMPLETE
   - Run `python "${CLAUDE_PLUGIN_ROOT}/skills/okode/scripts/okode_sync.py"` to update graph for changed files

### Step 4: Post-Build

After all phases complete:
1. Run an incremental scan: `python "${CLAUDE_PLUGIN_ROOT}/skills/okode/scripts/okode_scan.py" --incremental`
2. Generate a before/after comparison of the graph
3. Report:
   - Tasks completed vs blocked
   - Files modified
   - New nodes/edges in the graph
   - Any issues flagged by validators
4. Save build report to `.okode/plans/{plan_name}/build-report.md`
