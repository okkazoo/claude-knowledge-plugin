# oKode Ring Classification System

The ring system assigns every node in the code graph to one of three concentric rings based on its role in the architecture. Rings provide a coarse-grained importance filter: Ring 0 is the code that implements features, Ring 1 is the code that directly supports it, and Ring 2 is the infrastructure everything sits on.

---

## Ring Definitions

### Ring 0 -- Core

**What it is:** Files that directly implement features. This is the code a developer writes when building or modifying a product feature.

**Includes:**
- Route handlers / endpoint definitions
- Service classes containing business logic
- Domain models and entities
- Task definitions (Celery tasks, Bull jobs, background workers)
- Event publishers and subscribers with business logic
- Webhook handlers with business-specific processing
- Frontend pages and feature components
- CLI commands with domain logic
- Scripts that perform domain-specific operations

**Examples:**

| File                                     | Node Type  | Why Ring 0                                           |
|------------------------------------------|------------|------------------------------------------------------|
| `src/routes/workflows.py`               | endpoint   | Defines the HTTP endpoints a user hits               |
| `src/services/workflow_analyzer.py`      | service    | Contains the core analysis business logic            |
| `src/tasks/analysis.py`                  | task       | Defines the async job that runs analysis             |
| `src/events/handlers/on_completed.py`    | service    | Reacts to domain events with business behavior       |
| `frontend/src/pages/dashboard.tsx`       | page       | The actual page a user sees                          |
| `frontend/src/components/WorkflowEditor.tsx` | component | Core feature component with domain-specific logic |

**Key characteristic:** If you deleted a Ring 0 file, a user-facing feature would break.

---

### Ring 1 -- Adjacent

**What it is:** Files that directly support core code. These are the shared utilities, middleware, validators, serializers, and helpers that Ring 0 code imports. They do not implement features themselves but are required for features to work.

**Includes:**
- Shared utility functions used by Ring 0 code (date formatters, string helpers, math utilities)
- Middleware (authentication, rate limiting, CORS, request logging)
- Validators and schema definitions (Pydantic models, Zod schemas, Joi schemas)
- Serializers and data transformation layers
- Shared type definitions and interfaces
- Decorators and higher-order functions used by business code
- Test fixtures and factories (when analyzing test code)
- Shared frontend hooks (useAuth, useFetch) and context providers

**Examples:**

| File                                   | Node Type | Why Ring 1                                            |
|----------------------------------------|-----------|-------------------------------------------------------|
| `src/utils/date_helpers.py`           | utility   | Pure helper functions used by services and tasks      |
| `src/middleware/auth.py`              | utility   | Checks auth tokens; used by all protected endpoints   |
| `src/schemas/workflow_schema.py`      | utility   | Validates request/response shapes                     |
| `src/decorators/retry.py`            | utility   | Retry decorator used by services                      |
| `frontend/src/hooks/useAuth.ts`      | utility   | Shared hook used by multiple pages and components     |
| `src/utils/pagination.py`            | utility   | Shared pagination logic for list endpoints            |

**Key characteristic:** Ring 1 code is imported by Ring 0 code, but it does not itself define a feature. If you deleted a Ring 1 file, Ring 0 code would fail to import, but the missing piece is support logic, not the feature itself.

---

### Ring 2 -- Infrastructure

**What it is:** Framework-level and platform-level code that everything else sits on. This code rarely changes when building features and is typically configured once.

**Includes:**
- Database clients and connection pools (MongoClient, SQLAlchemy engine, Prisma client)
- HTTP clients (requests sessions, axios instances, fetch wrappers)
- Cache clients (Redis client initialization)
- Logging configuration and logger setup
- Application configuration loading (reading env vars, parsing config files)
- Base classes and abstract interfaces
- Framework boilerplate (app factory, ASGI/WSGI setup, plugin registration)
- Database collections/tables as entities (the collection node itself, not the code that queries it)
- External API client wrappers (thin SDK wrappers around third-party APIs)
- Environment variable definitions
- Docker, CI/CD, and deployment configuration representations

**Examples:**

| File                                | Node Type    | Why Ring 2                                           |
|-------------------------------------|--------------|------------------------------------------------------|
| `src/clients/db.py`               | file         | Creates and exports the database connection          |
| `src/clients/openai_client.py`    | file         | Wraps the OpenAI SDK; no business logic              |
| `src/config.py`                   | file         | Loads all env vars into a config object              |
| `src/logging.py`                  | file         | Configures structured logging                        |
| `src/app.py`                      | file         | ASGI app factory; mounts routers and middleware      |
| `collection:workflows`            | collection   | The DB collection itself is infrastructure           |
| `external_api:openai`             | external_api | The external API entity is infrastructure            |
| `env_var:DATABASE_URL`            | env_var      | Environment variable is infrastructure               |
| `cache_key:workflow:{id}:status`  | cache_key    | The cache key pattern is infrastructure              |

**Key characteristic:** Ring 2 code is the foundation. It changes when you switch databases, upgrade frameworks, or reconfigure infrastructure -- not when you build features.

---

## Classification Rules and Heuristics

The scanner applies the following rules in order to assign a ring to each node:

### Automatic Ring Assignments (by node type)

Some node types have fixed ring assignments because their nature determines their ring:

| Node Type      | Default Ring | Rationale                                         |
|----------------|--------------|---------------------------------------------------|
| `collection`   | 2            | Database entities are infrastructure              |
| `cache_key`    | 2            | Cache key patterns are infrastructure             |
| `external_api` | 2            | External API definitions are infrastructure       |
| `env_var`      | 2            | Environment variables are infrastructure config   |

### Heuristic Ring Assignments (by analysis)

For node types that could be any ring, the scanner uses heuristics:

**1. Path-based heuristics:**

| Path Pattern                           | Assigned Ring | Reason                                      |
|----------------------------------------|---------------|----------------------------------------------|
| `*/routes/*`, `*/handlers/*`          | 0             | Route handlers are core feature code         |
| `*/services/*`                        | 0             | Service classes contain business logic       |
| `*/tasks/*`, `*/jobs/*`, `*/workers/*`| 0             | Background jobs implement features           |
| `*/pages/*`, `*/views/*`             | 0             | Pages are user-facing feature code           |
| `*/components/*` (feature-specific)  | 0             | Feature components implement UI features     |
| `*/utils/*`, `*/helpers/*`           | 1             | Utility modules support core code            |
| `*/middleware/*`                      | 1             | Middleware supports route handlers           |
| `*/schemas/*`, `*/validators/*`      | 1             | Validators support endpoints and services    |
| `*/serializers/*`                    | 1             | Serializers transform data for core code     |
| `*/hooks/*` (shared)                 | 1             | Shared hooks support page/component code     |
| `*/clients/*`, `*/drivers/*`         | 2             | Client wrappers are infrastructure           |
| `*/config/*`, `*/settings/*`         | 2             | Configuration is infrastructure              |
| `*/logging/*`, `*/telemetry/*`       | 2             | Observability is infrastructure              |

**2. Dependency-direction heuristic:**
- If a node is imported by many other nodes but imports few itself, it trends toward Ring 2 (foundational).
- If a node imports many others but is imported by few, it trends toward Ring 0 (feature-level orchestration).
- If a node is imported by Ring 0 nodes and has moderate fan-in, it trends toward Ring 1 (support).

**3. Content-based heuristics:**
- Files containing HTTP method decorators (`@app.get`, `@router.post`) are Ring 0.
- Files containing class definitions with `Service` or `Manager` in the name are Ring 0.
- Files with only pure functions and no side effects trend toward Ring 1.
- Files that initialize clients or read `os.environ` / `process.env` trend toward Ring 2.

---

## How Ring Classification Affects Queries and Reports

### Filtering

Most oKode queries default to showing Ring 0 and Ring 1 results, hiding Ring 2 infrastructure noise. This keeps reports focused on feature code and its direct dependencies.

```
# Default: shows Ring 0 + Ring 1
okode query "what reads the workflows collection?"

# Explicit: include infrastructure
okode query "what reads the workflows collection?" --ring 0,1,2

# Focused: only core feature code
okode query "what reads the workflows collection?" --ring 0
```

### Impact Analysis

When analyzing the impact of a change, rings determine how far the analysis expands:

- **Ring 0 change:** High impact. The report shows all edges in and out, including Ring 1 and Ring 2 dependencies, plus any other Ring 0 nodes that connect through shared dependencies.
- **Ring 1 change:** Medium impact. The report shows which Ring 0 callers are affected and whether other Ring 1 nodes share the same dependency.
- **Ring 2 change:** Broad but shallow impact. The report flags that infrastructure changed and lists all Ring 0 and Ring 1 nodes that depend on it, but these changes typically do not alter feature behavior.

### Drift Detection

Ring changes are themselves a drift signal. If a file that was Ring 1 (utility) in the previous scan is now Ring 0 (service) in the current scan, that indicates the file has taken on business logic responsibilities and should be reviewed. See `drift_rules.md` for details.

### Visualization

In graph visualizations, rings map to visual layers:

- **Ring 0 nodes:** Rendered at the center, largest, boldest styling. These are the nodes users care about most.
- **Ring 1 nodes:** Rendered in the middle layer, medium styling.
- **Ring 2 nodes:** Rendered at the outer edge, smallest, muted styling. Often hidden by default to reduce clutter.
