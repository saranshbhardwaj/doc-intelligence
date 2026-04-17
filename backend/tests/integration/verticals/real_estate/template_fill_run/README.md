# TemplateFillRun Test Package

This package groups TemplateFillRun integration tests by boundary, so failures are easier to diagnose and maintain.

## Structure

- `conftest.py`: shared API client and model factories for this package
- `api/`: endpoint contract and lifecycle behavior tests

## Why this layout

- Keeps vertical-specific fixtures close to the tests that use them.
- Separates endpoint contract tests from repository and task-level tests.
- Makes it straightforward to add future folders:
  - `tasks/` for Celery task behavior and idempotency
  - `sse/` for stream termination and event-shape tests
