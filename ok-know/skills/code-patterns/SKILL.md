---
name: code-patterns
description: Project coding conventions and patterns with examples. Use when writing new code to follow project standards. Contains examples for API endpoints, components, error handling, and testing.
allowed-tools:
  - Read
model: sonnet
---

# Project Code Patterns

## When This Skill Activates

- Writing new code
- Creating new files
- Unsure of project conventions
- Need to match existing style

## How to Use

1. Check which type of code you're writing
2. Find the matching pattern below
3. Follow the example structure

## Available Patterns

### API Endpoints

See `examples/api-minimal.py`, `examples/api-standard.py`, `examples/api-full.py`

**When to use each:**
- **Minimal**: Internal tools, health checks
- **Standard**: Most endpoints, includes validation
- **Full**: Public API, includes docs, auth, rate limiting

### Components

See `examples/component-simple.jsx`, `examples/component-with-state.jsx`

**When to use each:**
- **Simple**: Display-only components
- **With state**: Interactive components

### Error Handling

See `examples/error-handling.py`

**Pattern:**
- Always catch specific exceptions
- Log with context
- Return user-friendly messages
- Don't expose internal details

### Testing

See `examples/test-pattern.py`

**Pattern:**
- Arrange / Act / Assert structure
- Descriptive test names
- One assertion per test (when practical)
- Mock external services

## Quick Reference

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Files (Python) | snake_case | `user_service.py` |
| Files (React) | PascalCase | `UserProfile.jsx` |
| Functions | snake_case | `get_user_by_id()` |
| Classes | PascalCase | `UserService` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |
| API routes | kebab-case | `/api/user-profile` |

### Import Order

```python
# 1. Standard library
import os
import sys

# 2. Third-party
import requests
from fastapi import APIRouter

# 3. Local
from app.models import User
from app.utils import helpers
```

### Docstrings

```python
def process_data(input_data: dict, validate: bool = True) -> Result:
    """
    Process input data and return result.

    Args:
        input_data: Dictionary containing the data to process
        validate: Whether to validate input (default: True)

    Returns:
        Result object with processed data

    Raises:
        ValidationError: If validate=True and data is invalid
    """
```

## Remember

- Consistency is more important than perfection
- Match the existing codebase style
- When in doubt, check similar existing code
- See `examples/` directory for concrete patterns
