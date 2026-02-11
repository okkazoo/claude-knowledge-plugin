# oKode Architectural Drift Detection

Drift detection compares two code graph snapshots -- the previous known-good graph and the current graph produced by a fresh scan -- and flags structural changes that may indicate unplanned architectural evolution.

---

## What Drift Detection Is and Why It Matters

Codebases evolve constantly. Most changes are intentional and well-understood: adding a new endpoint, updating a service, fixing a bug. But some changes introduce structural shifts that the developer may not have intended or fully considered:

- A service that was read-only against a collection now writes to it.
- A new third-party API dependency was introduced without team discussion.
- A utility file quietly grew into a service with business logic.
- Code that used to have callers is now orphaned.
- A circular dependency crept in through a seemingly innocent import.

Drift detection catches these structural changes automatically by diffing the graph. It does not judge whether a change is good or bad -- it flags changes that warrant human review because they alter the architecture in ways that may have non-obvious consequences.

---

## Severity Levels

### FLAG

A FLAG is an advisory alert. The change is permitted but should be reviewed by a human because it represents an architectural shift.

**Characteristics:**
- The change may be intentional and correct.
- No automated blocking occurs.
- The drift report includes the flag with context so a reviewer can make an informed decision.
- Multiple FLAGs in a single diff may collectively indicate a larger unplanned refactor.

### BLOCK

A BLOCK is a hard stop. The change introduces a structural violation that should not proceed without explicit resolution.

**Characteristics:**
- The change creates a known-bad architectural pattern (e.g., circular dependencies).
- Automated pipelines can use BLOCK signals to fail CI checks.
- Resolution requires either fixing the code or explicitly acknowledging the drift with a justification.

---

## Detection Rules

### 1. New External API Call Added -- FLAG

**Trigger:** An `api_call` edge exists in the new graph that did not exist in the old graph.

**Why it matters:** Adding a new external API dependency means the system now has a new failure point, a new latency source, and potentially new cost and compliance implications. External APIs require error handling, retry logic, circuit breakers, and monitoring.

**What the report shows:**
```
FLAG: New external API dependency detected
  Source: service:billing_calculator
  Target: external_api:stripe
  Edge:   api_call
  File:   src/services/billing_calculator.py:87
  Note:   This service previously had no external API calls.
```

### 2. New DB Write to Previously Read-Only Collection -- FLAG

**Trigger:** A `db_write` edge to a given collection exists in the new graph, but in the old graph that collection only had `db_read` edges (or no edges at all).

**Why it matters:** A collection that was read-only is architecturally simpler: no write conflicts, no need for write-concern tuning, simpler caching strategies. Introducing writes changes the data flow model and may require schema migration, index updates, or write-ahead logging.

**What the report shows:**
```
FLAG: New write to previously read-only collection
  Source: service:workflow_analyzer
  Target: collection:audit_log
  Edge:   db_write
  File:   src/services/workflow_analyzer.py:104
  Note:   collection:audit_log had 3 db_read edges and 0 db_write edges in previous graph.
```

### 3. New Environment Variable Dependency Added -- FLAG

**Trigger:** An `env_var` node exists in the new graph that did not exist in the old graph.

**Why it matters:** Every new environment variable is a deployment configuration requirement. If it is missing in production, staging, or a teammate's local setup, the application may fail to start or behave incorrectly. New env vars need to be added to `.env.example`, deployment manifests, CI secrets, and documentation.

**What the report shows:**
```
FLAG: New environment variable dependency
  Node: env_var:STRIPE_WEBHOOK_SECRET
  File: src/config.py:45
  Metadata: required=true, secret=true
  Note:   This env var did not exist in the previous graph.
          Ensure it is added to all deployment environments.
```

### 4. File Ring Changed -- FLAG

**Trigger:** A node's `ring` value in the new graph differs from its `ring` value in the old graph.

**Why it matters:** Ring changes indicate a file's architectural role has shifted. The most concerning pattern is a Ring 1 (utility) file being reclassified to Ring 0 (core), which means a shared helper has taken on business logic responsibilities. The reverse -- Ring 0 demoted to Ring 1 -- may indicate dead feature code being repurposed. Either way, this is a structural shift that deserves review.

**What the report shows:**
```
FLAG: Ring reclassification detected
  Node: utility:date_helpers -> service:date_helpers
  File: src/utils/date_helpers.py
  Old ring: 1 (Adjacent)
  New ring: 0 (Core)
  Note:   This file was a Ring 1 utility and is now classified as Ring 0 core.
          It may have taken on business logic responsibilities.
```

### 5. Orphaned Code Created -- FLAG

**Trigger:** A node that had one or more incoming edges in the old graph now has zero incoming edges in the new graph. (Incoming edges are edges where the node is the `target`.)

**Why it matters:** Code with no callers is dead code. It increases maintenance burden, confuses developers reading the codebase, and may indicate an incomplete refactor where callers were updated but the old target was not removed.

**Exclusions:**
- Entry-point nodes are excluded from this rule: `endpoint`, `page`, `script`, and `webhook` (inbound) nodes are expected to have no incoming edges from application code because they are invoked externally.
- Nodes that had zero incoming edges in both the old and new graphs are not flagged (they were already orphaned).

**What the report shows:**
```
FLAG: Orphaned code detected (callers dropped to 0)
  Node: service:legacy_exporter
  File: src/services/legacy_exporter.py
  Old incoming edges: 2 (from endpoint:GET:/api/export, task:nightly_export)
  New incoming edges: 0
  Note:   No code in the current graph calls this service.
          Consider removing it or restoring its callers.
```

### 6. Circular Dependency Introduced -- BLOCK

**Trigger:** The new graph contains a cycle in `imports` or `calls` edges that did not exist in the old graph. A cycle is detected when a depth-first traversal from any node following `imports` and `calls` edges arrives back at the starting node.

**Why it matters:** Circular dependencies cause import errors in many languages (Python circular imports, Node.js require cycles), make the dependency graph unpredictable, prevent clean module boundaries, and make it impossible to understand a module in isolation. This is the only BLOCK-level rule because circular dependencies are never architecturally desirable.

**What the report shows:**
```
BLOCK: Circular dependency introduced
  Cycle: service:order_service -> service:payment_service -> service:order_service
  Via edges:
    service:order_service --calls--> service:payment_service  (src/services/order_service.py:34)
    service:payment_service --calls--> service:order_service  (src/services/payment_service.py:67)
  Note:   This cycle did not exist in the previous graph.
          Circular dependencies must be resolved before merging.
          Consider extracting shared logic into a new service or using events.
```

---

## How Drift Is Detected

Drift detection operates on two graph snapshots: the **baseline** (previous known-good graph) and the **current** (freshly scanned graph).

### Step 1: Node Diff

Compare nodes by `id`:
- **Added nodes:** Present in current but not in baseline. Check for new `env_var`, `external_api`, and other significant additions.
- **Removed nodes:** Present in baseline but not in current. Check for orphaned code implications.
- **Modified nodes:** Present in both but with changed `ring`, `type`, or `metadata` fields. Check for ring reclassification.

### Step 2: Edge Diff

Compare edges by `(source, target, type)` tuple:
- **Added edges:** Present in current but not in baseline. Check for new `api_call`, `db_write`, `imports`, and `calls` edges.
- **Removed edges:** Present in baseline but not in current. These may cause orphaned nodes.
- **Modified edges:** Same `(source, target, type)` but different `context`, `file`, or `line`. Informational only, not flagged.

### Step 3: Derived Analysis

Using the node and edge diffs:
- **Read-only violation:** For each collection node, gather all `db_write` edges. If any are new (added edges) and the collection previously had zero `db_write` edges (in the baseline), flag it.
- **Orphan detection:** For each node that lost all incoming edges (by comparing baseline incoming edge count vs. current incoming edge count), flag it if the node type is not an entry-point type.
- **Cycle detection:** Run a cycle-detection algorithm (Tarjan's or DFS-based) on the current graph restricted to `imports` and `calls` edges. Compare detected cycles against cycles in the baseline graph. Any new cycle is a BLOCK.

---

## History Tracking

Every drift analysis result is persisted to the `.okode/history/` directory in the project root. This provides an audit trail of architectural evolution over time.

### Directory Structure

```
.okode/
  history/
    20260211T143000Z_diff.json
    20260210T091500Z_diff.json
    20260209T163200Z_diff.json
    ...
```

### Filename Format

```
{ISO8601_timestamp}_diff.json
```

The timestamp uses UTC in compact ISO 8601 format: `YYYYMMDDTHHMMSSZ`. This ensures files sort chronologically by name.

### Diff File Schema

```json
{
  "timestamp": "2026-02-11T14:30:00Z",
  "baseline_generated_at": "2026-02-10T09:15:00Z",
  "current_generated_at": "2026-02-11T14:30:00Z",
  "scanner_version": "0.4.0",
  "summary": {
    "nodes_added": 3,
    "nodes_removed": 1,
    "nodes_modified": 2,
    "edges_added": 5,
    "edges_removed": 2,
    "flags": 4,
    "blocks": 0
  },
  "flags": [
    {
      "rule": "new_external_api_call",
      "severity": "FLAG",
      "message": "New external API dependency detected",
      "source": "service:billing_calculator",
      "target": "external_api:stripe",
      "edge_type": "api_call",
      "file": "src/services/billing_calculator.py",
      "line": 87,
      "details": "This service previously had no external API calls."
    },
    {
      "rule": "new_db_write_to_readonly_collection",
      "severity": "FLAG",
      "message": "New write to previously read-only collection",
      "source": "service:workflow_analyzer",
      "target": "collection:audit_log",
      "edge_type": "db_write",
      "file": "src/services/workflow_analyzer.py",
      "line": 104,
      "details": "collection:audit_log had 3 db_read edges and 0 db_write edges in previous graph."
    },
    {
      "rule": "new_env_var",
      "severity": "FLAG",
      "message": "New environment variable dependency",
      "node": "env_var:STRIPE_WEBHOOK_SECRET",
      "file": "src/config.py",
      "line": 45,
      "details": "required=true, secret=true. Ensure it is added to all deployment environments."
    },
    {
      "rule": "orphaned_code",
      "severity": "FLAG",
      "message": "Orphaned code detected (callers dropped to 0)",
      "node": "service:legacy_exporter",
      "file": "src/services/legacy_exporter.py",
      "old_incoming_count": 2,
      "new_incoming_count": 0,
      "details": "Previously called by endpoint:GET:/api/export and task:nightly_export."
    }
  ],
  "blocks": [],
  "nodes_added": [
    {
      "id": "external_api:stripe",
      "type": "external_api",
      "file": "src/clients/stripe_client.py",
      "ring": 2
    },
    {
      "id": "env_var:STRIPE_WEBHOOK_SECRET",
      "type": "env_var",
      "file": "src/config.py",
      "ring": 2
    },
    {
      "id": "env_var:STRIPE_API_KEY",
      "type": "env_var",
      "file": "src/config.py",
      "ring": 2
    }
  ],
  "nodes_removed": [
    {
      "id": "service:legacy_exporter",
      "type": "service",
      "file": "src/services/legacy_exporter.py",
      "ring": 0
    }
  ],
  "nodes_modified": [
    {
      "id": "utility:date_helpers",
      "field": "ring",
      "old_value": 1,
      "new_value": 0
    },
    {
      "id": "service:workflow_analyzer",
      "field": "metadata.dependencies",
      "old_value": ["db_client", "openai_client", "cache"],
      "new_value": ["db_client", "openai_client", "cache", "stripe_client"]
    }
  ],
  "edges_added": [
    {
      "source": "service:billing_calculator",
      "target": "external_api:stripe",
      "type": "api_call"
    },
    {
      "source": "service:workflow_analyzer",
      "target": "collection:audit_log",
      "type": "db_write"
    }
  ],
  "edges_removed": [
    {
      "source": "endpoint:GET:/api/export",
      "target": "service:legacy_exporter",
      "type": "calls"
    },
    {
      "source": "task:nightly_export",
      "target": "service:legacy_exporter",
      "type": "calls"
    }
  ]
}
```

---

## Example Drift Report Output

When drift detection runs, it produces a human-readable summary in addition to the JSON diff file:

```
=== oKode Drift Report ===
Baseline: 2026-02-10T09:15:00Z
Current:  2026-02-11T14:30:00Z

Summary:
  +3 nodes added, -1 removed, ~2 modified
  +5 edges added, -2 removed
  4 FLAGs, 0 BLOCKs

--- FLAGS ---

[FLAG] New external API dependency detected
  service:billing_calculator --api_call--> external_api:stripe
  src/services/billing_calculator.py:87
  This service previously had no external API calls.

[FLAG] New write to previously read-only collection
  service:workflow_analyzer --db_write--> collection:audit_log
  src/services/workflow_analyzer.py:104
  collection:audit_log had 3 db_read edges and 0 db_write edges previously.

[FLAG] New environment variable dependency
  env_var:STRIPE_WEBHOOK_SECRET
  src/config.py:45
  required=true, secret=true
  Ensure it is added to all deployment environments.

[FLAG] Orphaned code detected (callers dropped to 0)
  service:legacy_exporter
  src/services/legacy_exporter.py
  Was called by 2 nodes, now called by 0.
  Consider removing it or restoring its callers.

--- BLOCKS ---

  (none)

=== End Report ===
```

When a BLOCK is present, the report changes its exit posture:

```
=== oKode Drift Report ===
Baseline: 2026-02-10T09:15:00Z
Current:  2026-02-11T14:30:00Z

Summary:
  +2 nodes added, -0 removed, ~1 modified
  +3 edges added, -0 removed
  1 FLAG, 1 BLOCK

--- FLAGS ---

[FLAG] New environment variable dependency
  env_var:PAYMENT_GATEWAY_URL
  src/config.py:52
  required=true, secret=false

--- BLOCKS ---

[BLOCK] Circular dependency introduced
  Cycle: service:order_service -> service:payment_service -> service:order_service
  service:order_service --calls--> service:payment_service  (src/services/order_service.py:34)
  service:payment_service --calls--> service:order_service  (src/services/payment_service.py:67)
  This cycle did not exist in the previous graph.
  Resolve before merging: extract shared logic into a new service or use events.

=== DRIFT CHECK FAILED (1 BLOCK) ===
```

---

## Integration with CI/CD

Drift detection is designed to run in CI pipelines:

- **Exit code 0:** No BLOCKs detected. FLAGs are advisory and do not fail the build.
- **Exit code 1:** One or more BLOCKs detected. The pipeline should fail and require resolution.
- The JSON diff file is always written to `.okode/history/` regardless of exit code, providing a persistent record.
- FLAGs can optionally be promoted to BLOCKs via project configuration if a team wants stricter enforcement (e.g., "all new external API calls require explicit approval").
