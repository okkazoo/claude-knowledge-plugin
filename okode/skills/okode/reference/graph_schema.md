# oKode Graph JSON Schema Reference

This document is the authoritative reference for the oKode code graph JSON format. Every scanner output and every query tool operates against this schema.

---

## Top-Level Structure

```json
{
  "metadata": { ... },
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

| Field      | Type     | Description                                      |
|------------|----------|--------------------------------------------------|
| `metadata` | object   | Information about the scan that produced this graph |
| `nodes`    | array    | All discovered code entities                     |
| `edges`    | array    | All discovered relationships between entities    |

---

## Metadata

```json
{
  "metadata": {
    "project": "my-app",
    "generated_at": "2026-02-11T14:30:00Z",
    "scanner_version": "0.4.0",
    "total_files_analyzed": 247,
    "analysis_duration_seconds": 12.8
  }
}
```

| Field                        | Type    | Description                                           |
|------------------------------|---------|-------------------------------------------------------|
| `project`                    | string  | Name of the scanned project (typically the repo name) |
| `generated_at`               | string  | ISO 8601 timestamp of when the scan completed         |
| `scanner_version`            | string  | Semver version of the scanner that produced this graph |
| `total_files_analyzed`       | integer | Count of source files the scanner examined            |
| `analysis_duration_seconds`  | number  | Wall-clock time the scan took, in seconds             |

---

## Node Schema

Each node represents a single code entity discovered during scanning.

```json
{
  "id": "endpoint:POST:/api/workflows/analyze",
  "type": "endpoint",
  "label": "POST /api/workflows/analyze",
  "file": "src/routes/workflows.py",
  "line": 42,
  "ring": 0,
  "metadata": {
    "method": "POST",
    "path": "/api/workflows/analyze",
    "auth_required": true
  }
}
```

### Core Fields

| Field      | Type    | Required | Description                                                      |
|------------|---------|----------|------------------------------------------------------------------|
| `id`       | string  | yes      | Globally unique identifier. Format: `{type}:{qualifier}`. See Node ID Conventions below. |
| `type`     | string  | yes      | One of the 15 node types listed below.                           |
| `label`    | string  | yes      | Human-readable short name for display in reports and visualizations. |
| `file`     | string  | yes      | Relative file path from project root where this entity is defined. |
| `line`     | integer | yes      | Line number in `file` where the definition begins.               |
| `ring`     | integer | yes      | Ring classification: 0 (Core), 1 (Adjacent), or 2 (Infrastructure). See ring_system.md. |
| `metadata` | object  | no       | Type-specific additional information. Contents vary by node type. |

### All 15 Node Types

#### endpoint
An HTTP route handler that accepts incoming requests.
- **Ring**: Typically 0
- **Metadata**: `method` (GET, POST, PUT, DELETE, PATCH), `path` (URL pattern), `auth_required` (boolean), `rate_limited` (boolean)
- **ID format**: `endpoint:{METHOD}:{path}`
- **Example**: `endpoint:POST:/api/workflows/analyze`

#### collection
A database collection or table that the application reads from or writes to.
- **Ring**: Typically 2
- **Metadata**: `db_type` (mongo, postgres, redis, etc.), `indexes` (array of index definitions)
- **ID format**: `collection:{name}`
- **Example**: `collection:workflows`

#### file
A source file in the project. Used when the scanner needs to represent a file as an entity (e.g., for import tracking).
- **Ring**: Varies (0, 1, or 2 depending on file purpose)
- **Metadata**: `language` (python, typescript, etc.), `loc` (lines of code), `imports_count` (number of imports)
- **ID format**: `file:{relative_path}`
- **Example**: `file:src/services/workflow_analyzer.py`

#### router
A route grouping or sub-router that mounts multiple endpoints under a shared prefix.
- **Ring**: Typically 0
- **Metadata**: `prefix` (URL prefix), `middleware` (array of middleware names)
- **ID format**: `router:{prefix}`
- **Example**: `router:/api/workflows`

#### script
A standalone script meant to be run directly (CLI tools, migrations, seed scripts, cron jobs).
- **Ring**: Typically 0
- **Metadata**: `entrypoint` (boolean), `schedule` (cron expression if applicable)
- **ID format**: `script:{filename}`
- **Example**: `script:migrate_db.py`

#### task
An asynchronous task or background job (Celery tasks, Bull jobs, sidekiq workers, etc.).
- **Ring**: Typically 0
- **Metadata**: `queue` (queue name), `retry_policy` (object with max_retries, backoff), `timeout_seconds` (integer)
- **ID format**: `task:{task_name}`
- **Example**: `task:analyze_workflow`

#### cache_key
A cache key pattern used for reading or writing cached data (Redis keys, memcached keys, etc.).
- **Ring**: Typically 2
- **Metadata**: `ttl_seconds` (integer), `pattern` (key pattern string)
- **ID format**: `cache_key:{pattern}`
- **Example**: `cache_key:workflow:{id}:status`

#### service
A service class or module that encapsulates business logic.
- **Ring**: Typically 0
- **Metadata**: `methods` (array of public method names), `dependencies` (array of injected service names)
- **ID format**: `service:{name}`
- **Example**: `service:workflow_analyzer`

#### utility
A utility function or helper module providing shared, reusable functionality.
- **Ring**: Typically 1
- **Metadata**: `pure` (boolean -- whether the function is side-effect free), `exported_functions` (array of function names)
- **ID format**: `utility:{name}`
- **Example**: `utility:date_helpers`

#### webhook
An inbound or outbound webhook endpoint.
- **Ring**: Typically 0
- **Metadata**: `direction` (inbound or outbound), `provider` (e.g., stripe, github), `event_types` (array of event type strings)
- **ID format**: `webhook:{direction}:{provider}:{event}`
- **Example**: `webhook:inbound:stripe:payment_intent.succeeded`

#### event
A named event in a publish/subscribe or event-driven system (e.g., domain events, message bus topics).
- **Ring**: Typically 0
- **Metadata**: `bus` (event bus name), `schema` (payload schema reference)
- **ID format**: `event:{event_name}`
- **Example**: `event:workflow.completed`

#### external_api
A third-party API that the application calls outbound.
- **Ring**: Typically 2
- **Metadata**: `base_url` (string), `auth_method` (api_key, oauth, bearer, etc.), `sdk` (SDK package name if used)
- **ID format**: `external_api:{provider}`
- **Example**: `external_api:openai`

#### env_var
An environment variable that the application reads at runtime.
- **Ring**: Typically 2
- **Metadata**: `required` (boolean), `default` (default value if any), `secret` (boolean -- whether it holds sensitive data)
- **ID format**: `env_var:{VAR_NAME}`
- **Example**: `env_var:OPENAI_API_KEY`

#### component
A UI component (React component, Vue component, Svelte component, etc.).
- **Ring**: Typically 0
- **Metadata**: `framework` (react, vue, svelte, etc.), `props` (array of prop names), `state_management` (local, redux, zustand, etc.)
- **ID format**: `component:{name}`
- **Example**: `component:WorkflowEditor`

#### page
A page-level route in a frontend application (Next.js page, Nuxt page, SvelteKit route, etc.).
- **Ring**: Typically 0
- **Metadata**: `route` (URL path), `layout` (layout component name), `ssr` (boolean)
- **ID format**: `page:{route}`
- **Example**: `page:/dashboard/workflows`

---

## Edge Schema

Each edge represents a directional relationship between two nodes.

```json
{
  "source": "endpoint:POST:/api/workflows/analyze",
  "target": "service:workflow_analyzer",
  "type": "calls",
  "context": "Delegates analysis to WorkflowAnalyzer.run()",
  "file": "src/routes/workflows.py",
  "line": 48
}
```

### Core Fields

| Field     | Type    | Required | Description                                                        |
|-----------|---------|----------|--------------------------------------------------------------------|
| `source`  | string  | yes      | Node ID of the edge origin. Must match an existing node `id`.      |
| `target`  | string  | yes      | Node ID of the edge destination. Must match an existing node `id`. |
| `type`    | string  | yes      | One of the 15 edge types listed below.                             |
| `context` | string  | no       | Human-readable description of what this relationship means in code. |
| `file`    | string  | no       | File where this relationship is expressed.                         |
| `line`    | integer | no       | Line number where this relationship is expressed.                  |

### All 15 Edge Types

#### db_read
The source reads data from the target collection.
- **Source**: endpoint, service, task, script
- **Target**: collection
- **Example**: `service:workflow_analyzer` --db_read--> `collection:workflows`

#### db_write
The source writes data to the target collection (insert, update, delete).
- **Source**: endpoint, service, task, script
- **Target**: collection
- **Example**: `task:analyze_workflow` --db_write--> `collection:workflow_results`

#### endpoint_handler
The source router or file mounts/registers the target endpoint.
- **Source**: router, file
- **Target**: endpoint
- **Example**: `router:/api/workflows` --endpoint_handler--> `endpoint:POST:/api/workflows/analyze`

#### api_call
The source makes an outbound HTTP call to the target external API.
- **Source**: service, task, endpoint, script
- **Target**: external_api
- **Example**: `service:workflow_analyzer` --api_call--> `external_api:openai`

#### cache_read
The source reads from the target cache key.
- **Source**: endpoint, service, task
- **Target**: cache_key
- **Example**: `service:workflow_analyzer` --cache_read--> `cache_key:workflow:{id}:status`

#### cache_write
The source writes to the target cache key.
- **Source**: endpoint, service, task
- **Target**: cache_key
- **Example**: `task:analyze_workflow` --cache_write--> `cache_key:workflow:{id}:status`

#### webhook_receive
The source endpoint receives an inbound webhook from the target provider.
- **Source**: endpoint
- **Target**: webhook
- **Example**: `endpoint:POST:/webhooks/stripe` --webhook_receive--> `webhook:inbound:stripe:payment_intent.succeeded`

#### webhook_send
The source sends an outbound webhook to the target.
- **Source**: service, task
- **Target**: webhook
- **Example**: `service:notification_service` --webhook_send--> `webhook:outbound:slack:message`

#### event_publish
The source publishes the target event onto an event bus.
- **Source**: service, task, endpoint
- **Target**: event
- **Example**: `service:workflow_analyzer` --event_publish--> `event:workflow.completed`

#### event_subscribe
The source subscribes to (listens for) the target event.
- **Source**: service, task
- **Target**: event
- **Example**: `task:send_completion_email` --event_subscribe--> `event:workflow.completed`

#### imports
The source file imports or requires the target file/module.
- **Source**: file
- **Target**: file, utility, service
- **Example**: `file:src/routes/workflows.py` --imports--> `service:workflow_analyzer`

#### calls
The source invokes a function or method on the target.
- **Source**: endpoint, service, task, script, component, page
- **Target**: service, utility
- **Example**: `endpoint:POST:/api/workflows/analyze` --calls--> `service:workflow_analyzer`

#### enqueues
The source enqueues the target task for asynchronous processing.
- **Source**: endpoint, service, task, script
- **Target**: task
- **Example**: `endpoint:POST:/api/workflows/analyze` --enqueues--> `task:analyze_workflow`

#### renders
The source page or component renders the target component.
- **Source**: page, component
- **Target**: component
- **Example**: `page:/dashboard/workflows` --renders--> `component:WorkflowEditor`

#### fetches
The source frontend entity fetches data from the target endpoint.
- **Source**: component, page
- **Target**: endpoint
- **Example**: `component:WorkflowEditor` --fetches--> `endpoint:GET:/api/workflows/{id}`

---

## Node ID Conventions

Node IDs must be globally unique within a graph. They follow the pattern `{type}:{qualifier}` where the qualifier varies by type:

| Node Type      | ID Pattern                                  | Examples                                           |
|----------------|---------------------------------------------|----------------------------------------------------|
| `endpoint`     | `endpoint:{METHOD}:{path}`                  | `endpoint:POST:/api/workflows/analyze`             |
| `collection`   | `collection:{name}`                         | `collection:workflows`                             |
| `file`         | `file:{relative_path}`                      | `file:src/services/workflow_analyzer.py`           |
| `router`       | `router:{prefix}`                           | `router:/api/workflows`                            |
| `script`       | `script:{filename}`                         | `script:migrate_db.py`                             |
| `task`         | `task:{task_name}`                          | `task:analyze_workflow`                             |
| `cache_key`    | `cache_key:{pattern}`                       | `cache_key:workflow:{id}:status`                   |
| `service`      | `service:{name}`                            | `service:workflow_analyzer`                        |
| `utility`      | `utility:{name}`                            | `utility:date_helpers`                             |
| `webhook`      | `webhook:{direction}:{provider}:{event}`    | `webhook:inbound:stripe:payment_intent.succeeded`  |
| `event`        | `event:{event_name}`                        | `event:workflow.completed`                         |
| `external_api` | `external_api:{provider}`                   | `external_api:openai`                              |
| `env_var`      | `env_var:{VAR_NAME}`                        | `env_var:OPENAI_API_KEY`                           |
| `component`    | `component:{name}`                          | `component:WorkflowEditor`                         |
| `page`         | `page:{route}`                              | `page:/dashboard/workflows`                        |

**Rules:**
- IDs are case-sensitive.
- Path segments in endpoint and page IDs use forward slashes.
- Environment variable names use UPPER_SNAKE_CASE by convention.
- Service and utility names use lower_snake_case.
- Component names use PascalCase.
- Colons (`:`) are the delimiter between the type prefix and the qualifier. If the qualifier itself contains colons (e.g., cache key patterns), that is acceptable since the type prefix is always the substring before the first colon.

---

## Example Complete Graph JSON

```json
{
  "metadata": {
    "project": "workflow-engine",
    "generated_at": "2026-02-11T14:30:00Z",
    "scanner_version": "0.4.0",
    "total_files_analyzed": 47,
    "analysis_duration_seconds": 3.2
  },
  "nodes": [
    {
      "id": "router:/api/workflows",
      "type": "router",
      "label": "/api/workflows router",
      "file": "src/routes/workflows.py",
      "line": 1,
      "ring": 0,
      "metadata": {
        "prefix": "/api/workflows",
        "middleware": ["auth", "rate_limit"]
      }
    },
    {
      "id": "endpoint:POST:/api/workflows/analyze",
      "type": "endpoint",
      "label": "POST /api/workflows/analyze",
      "file": "src/routes/workflows.py",
      "line": 42,
      "ring": 0,
      "metadata": {
        "method": "POST",
        "path": "/api/workflows/analyze",
        "auth_required": true,
        "rate_limited": true
      }
    },
    {
      "id": "endpoint:GET:/api/workflows/{id}",
      "type": "endpoint",
      "label": "GET /api/workflows/{id}",
      "file": "src/routes/workflows.py",
      "line": 78,
      "ring": 0,
      "metadata": {
        "method": "GET",
        "path": "/api/workflows/{id}",
        "auth_required": true,
        "rate_limited": false
      }
    },
    {
      "id": "service:workflow_analyzer",
      "type": "service",
      "label": "WorkflowAnalyzer",
      "file": "src/services/workflow_analyzer.py",
      "line": 15,
      "ring": 0,
      "metadata": {
        "methods": ["run", "validate", "score"],
        "dependencies": ["db_client", "openai_client", "cache"]
      }
    },
    {
      "id": "task:analyze_workflow",
      "type": "task",
      "label": "analyze_workflow task",
      "file": "src/tasks/analysis.py",
      "line": 10,
      "ring": 0,
      "metadata": {
        "queue": "analysis",
        "retry_policy": {
          "max_retries": 3,
          "backoff": "exponential"
        },
        "timeout_seconds": 300
      }
    },
    {
      "id": "collection:workflows",
      "type": "collection",
      "label": "workflows",
      "file": "src/models/workflow.py",
      "line": 8,
      "ring": 2,
      "metadata": {
        "db_type": "mongo",
        "indexes": ["owner_id", "status", "created_at"]
      }
    },
    {
      "id": "collection:workflow_results",
      "type": "collection",
      "label": "workflow_results",
      "file": "src/models/workflow_result.py",
      "line": 5,
      "ring": 2,
      "metadata": {
        "db_type": "mongo",
        "indexes": ["workflow_id"]
      }
    },
    {
      "id": "external_api:openai",
      "type": "external_api",
      "label": "OpenAI API",
      "file": "src/clients/openai_client.py",
      "line": 1,
      "ring": 2,
      "metadata": {
        "base_url": "https://api.openai.com/v1",
        "auth_method": "bearer",
        "sdk": "openai"
      }
    },
    {
      "id": "env_var:OPENAI_API_KEY",
      "type": "env_var",
      "label": "OPENAI_API_KEY",
      "file": "src/config.py",
      "line": 12,
      "ring": 2,
      "metadata": {
        "required": true,
        "default": null,
        "secret": true
      }
    },
    {
      "id": "cache_key:workflow:{id}:status",
      "type": "cache_key",
      "label": "workflow status cache",
      "file": "src/services/workflow_analyzer.py",
      "line": 55,
      "ring": 2,
      "metadata": {
        "ttl_seconds": 3600,
        "pattern": "workflow:{id}:status"
      }
    },
    {
      "id": "event:workflow.completed",
      "type": "event",
      "label": "workflow.completed",
      "file": "src/events.py",
      "line": 20,
      "ring": 0,
      "metadata": {
        "bus": "internal",
        "schema": "WorkflowCompletedPayload"
      }
    },
    {
      "id": "utility:date_helpers",
      "type": "utility",
      "label": "date_helpers",
      "file": "src/utils/date_helpers.py",
      "line": 1,
      "ring": 1,
      "metadata": {
        "pure": true,
        "exported_functions": ["parse_iso", "format_duration", "now_utc"]
      }
    },
    {
      "id": "component:WorkflowEditor",
      "type": "component",
      "label": "WorkflowEditor",
      "file": "frontend/src/components/WorkflowEditor.tsx",
      "line": 12,
      "ring": 0,
      "metadata": {
        "framework": "react",
        "props": ["workflowId", "onSave", "readOnly"],
        "state_management": "zustand"
      }
    },
    {
      "id": "page:/dashboard/workflows",
      "type": "page",
      "label": "Workflows Dashboard",
      "file": "frontend/src/pages/dashboard/workflows.tsx",
      "line": 1,
      "ring": 0,
      "metadata": {
        "route": "/dashboard/workflows",
        "layout": "DashboardLayout",
        "ssr": false
      }
    }
  ],
  "edges": [
    {
      "source": "router:/api/workflows",
      "target": "endpoint:POST:/api/workflows/analyze",
      "type": "endpoint_handler",
      "context": "Mounts POST /analyze under /api/workflows",
      "file": "src/routes/workflows.py",
      "line": 42
    },
    {
      "source": "router:/api/workflows",
      "target": "endpoint:GET:/api/workflows/{id}",
      "type": "endpoint_handler",
      "context": "Mounts GET /{id} under /api/workflows",
      "file": "src/routes/workflows.py",
      "line": 78
    },
    {
      "source": "endpoint:POST:/api/workflows/analyze",
      "target": "service:workflow_analyzer",
      "type": "calls",
      "context": "Delegates analysis to WorkflowAnalyzer.run()",
      "file": "src/routes/workflows.py",
      "line": 48
    },
    {
      "source": "endpoint:POST:/api/workflows/analyze",
      "target": "task:analyze_workflow",
      "type": "enqueues",
      "context": "Enqueues async analysis job for large workflows",
      "file": "src/routes/workflows.py",
      "line": 52
    },
    {
      "source": "service:workflow_analyzer",
      "target": "collection:workflows",
      "type": "db_read",
      "context": "Reads workflow definition by ID",
      "file": "src/services/workflow_analyzer.py",
      "line": 30
    },
    {
      "source": "task:analyze_workflow",
      "target": "collection:workflow_results",
      "type": "db_write",
      "context": "Writes analysis results after processing",
      "file": "src/tasks/analysis.py",
      "line": 45
    },
    {
      "source": "service:workflow_analyzer",
      "target": "external_api:openai",
      "type": "api_call",
      "context": "Calls OpenAI chat completions for workflow scoring",
      "file": "src/services/workflow_analyzer.py",
      "line": 62
    },
    {
      "source": "service:workflow_analyzer",
      "target": "cache_key:workflow:{id}:status",
      "type": "cache_read",
      "context": "Checks if analysis result is already cached",
      "file": "src/services/workflow_analyzer.py",
      "line": 25
    },
    {
      "source": "task:analyze_workflow",
      "target": "cache_key:workflow:{id}:status",
      "type": "cache_write",
      "context": "Caches analysis status after completion",
      "file": "src/tasks/analysis.py",
      "line": 50
    },
    {
      "source": "task:analyze_workflow",
      "target": "event:workflow.completed",
      "type": "event_publish",
      "context": "Publishes completion event after analysis finishes",
      "file": "src/tasks/analysis.py",
      "line": 55
    },
    {
      "source": "service:workflow_analyzer",
      "target": "utility:date_helpers",
      "type": "calls",
      "context": "Uses date_helpers.now_utc() for timestamps",
      "file": "src/services/workflow_analyzer.py",
      "line": 18
    },
    {
      "source": "endpoint:GET:/api/workflows/{id}",
      "target": "collection:workflows",
      "type": "db_read",
      "context": "Fetches single workflow by ID",
      "file": "src/routes/workflows.py",
      "line": 82
    },
    {
      "source": "page:/dashboard/workflows",
      "target": "component:WorkflowEditor",
      "type": "renders",
      "context": "Renders workflow editor in dashboard page",
      "file": "frontend/src/pages/dashboard/workflows.tsx",
      "line": 35
    },
    {
      "source": "component:WorkflowEditor",
      "target": "endpoint:GET:/api/workflows/{id}",
      "type": "fetches",
      "context": "Loads workflow data on mount via GET request",
      "file": "frontend/src/components/WorkflowEditor.tsx",
      "line": 28
    }
  ]
}
```

---

## Schema Validation Notes

- Every `source` and `target` in the edges array must reference a valid `id` from the nodes array. Dangling references are scanner bugs.
- Node IDs must be unique. Duplicate IDs indicate the scanner discovered the same entity twice and failed to deduplicate.
- The `ring` field must be 0, 1, or 2. Any other value is invalid.
- The `type` field on nodes must be one of the 15 defined node types. The `type` field on edges must be one of the 15 defined edge types.
- The `file` field on nodes is always required and must be a relative path from the project root (no leading slash, no absolute paths).
- The `line` field on nodes must be a positive integer (1 or greater).
