# oKode Synthesis Report: {feature_name}

> Generated: {timestamp}
> Graph Version: {graph_version}
> Scope: {scope_description}

---

## Quick Stats

| Metric | Count |
|--------|-------|
| Components | {node_count} |
| Endpoints | {endpoint_count} |
| Services | {service_count} |
| Background Tasks | {task_count} |
| Collections | {collection_count} |
| External APIs | {external_api_count} |
| Relationships | {edge_count} |
| Environment Variables | {env_var_count} |

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Component Registry](#component-registry)
3. [Endpoint Chains](#endpoint-chains)
4. [Data Flows](#data-flows)
5. [External Dependencies](#external-dependencies)
6. [Dependency Map](#dependency-map)
7. [Risk Analysis](#risk-analysis)
8. [Quick Reference](#quick-reference)

---

## Architecture Overview

### Ring Distribution

```
Ring 0 (Core):         {ring_0_components}
Ring 1 (Features):     {ring_1_components}
Ring 2 (Integrations): {ring_2_components}
```

### High-Level Flow

```
{architecture_diagram}
```

{architecture_narrative}

---

## Component Registry

### Endpoints

{endpoint_registry}

### Services

{service_registry}

### Background Tasks

{task_registry}

### Models

{model_registry}

### Middleware

{middleware_registry}

---

## Endpoint Chains

Full execution traces for each endpoint in this feature.

{endpoint_chains}

---

## Data Flows

### Collections

{collection_details}

### Data Contract Summary

| Collection | Readers | Writers | Deleters |
|------------|---------|---------|----------|
{data_contract_table}

### Cache Usage

{cache_details}

---

## External Dependencies

### External APIs

{external_api_details}

### Environment Variables

| Variable | Used By | Purpose |
|----------|---------|---------|
{env_var_table}

### Queue/Job Dependencies

{queue_details}

---

## Dependency Map

### Inbound Dependencies (Who Depends on This Feature)

{inbound_dependencies}

### Outbound Dependencies (What This Feature Depends On)

{outbound_dependencies}

### Cross-Feature Connections

{cross_feature_connections}

---

## Risk Analysis

### Hotspots (Most Connected Nodes)

| Node | Inbound | Outbound | Total | Risk |
|------|---------|----------|-------|------|
{hotspot_table}

### Single Points of Failure

{single_points_of_failure}

### Dead Code Candidates

{dead_code_candidates}

### Circular Dependencies

{circular_dependencies}

---

## Quick Reference

### "What happens when..." Cheat Sheet

{what_happens_when}

### Common Modification Patterns

{modification_patterns}

### Files by Modification Risk

| Risk Level | Files |
|------------|-------|
| High | {high_risk_files} |
| Medium | {medium_risk_files} |
| Low | {low_risk_files} |

---

> oKode synthesis complete. Use `/okode-plan <task>` to create an execution plan
> based on this analysis.
