# Testing Framework

Comprehensive testing setup for the doc-intelligence backend, focusing on the real estate template filling vertical.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (DB, repos, models, LLM mocks)
├── fixtures/                # Test data files
│   ├── excel/              # Sample Excel templates
│   ├── responses/          # Recorded API responses (record/replay)
│   └── documents/          # Mock document chunks
├── unit/                    # Pure function tests (no mocking)
│   └── verticals/
│       └── real_estate/
│           └── test_field_type_inference.py
├── integration/             # Service tests (with mocked dependencies)
│   └── verticals/
│       └── real_estate/
│           ├── test_template_repository.py
│           └── test_llm_service.py
└── e2e/                     # End-to-end tests (full stack)
```

## Running Tests

### Setup (One-time)

1. **Create test database**:
```powershell
.\setup_test_db.ps1
```

Or manually:
```bash
docker exec -i docint-postgres psql -U docint -d docint -c "CREATE DATABASE docint_test;"
```

2. **Install dependencies**:
```bash
cd backend
pip install -r requirements-dev.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Types

```bash
# Unit tests only (fast, no mocking)
pytest -m unit

# Integration tests only
pytest -m integration

# End-to-end tests
pytest -m e2e
```

### Run Specific Files

```bash
# Field type inference tests
pytest tests/unit/verticals/real_estate/test_field_type_inference.py

# Template repository tests
pytest tests/integration/verticals/real_estate/test_template_repository.py

# LLM service tests
pytest tests/integration/verticals/real_estate/test_llm_service.py
```

### Run With Coverage

```bash
# Generate coverage report
pytest --cov=app --cov-report=html

# View coverage (opens in browser)
start htmlcov/index.html  # Windows
```

## Test Categories

### Unit Tests (`@pytest.mark.unit`)

Pure function tests with **no external dependencies**.

### Integration Tests (`@pytest.mark.integration`)

Tests with **mocked external services** (DB, LLM, storage).

### End-to-End Tests (`@pytest.mark.e2e`)

Full pipeline tests with **all components**.

## LLM Testing (Record/Replay)

Uses **recorded API responses** from `tests/fixtures/responses/`.

### Record Mode

To record new API responses:

```bash
set PYTEST_RECORD_MODE=record
set ANTHROPIC_API_KEY=your-api-key
pytest tests/integration/verticals/real_estate/test_llm_service.py
```

## Writing New Tests

### Unit Test Template

```python
import pytest

class TestMyFunction:
    @pytest.mark.unit
    def test_basic_case(self):
        result = function_to_test("input")
        assert result == "expected"
```

### Integration Test Template

```python
import pytest

class TestMyRepository:
    @pytest.mark.integration
    def test_create_entity(self, my_repo):
        entity = my_repo.create(name="Test")
        assert entity.id is not None
```

## Code Coverage Goals

| Component | Target |
|-----------|--------|
| Repositories | 90%+ |
| LLM Service | 85%+ |
| Pure Functions | 95%+ |

## Next Steps

1. Run unit tests: `pytest -m unit`
2. Check coverage: `pytest --cov=app`
3. Add more tests for other modules
