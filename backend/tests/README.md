# Tests Directory

This directory contains all test files for the backend project, organized by test type.

## Directory Structure

- **unit/** - Unit tests for individual components (Service layer, utilities, validators)
- **integration/** - Integration tests for API endpoints and multi-component interactions
- **property/** - Property-based tests using Hypothesis
- **e2e/** - End-to-end tests (Django Admin interface tests, browser automation)
- **structure/** - Project structure validation tests
- **factories/** - Test data factories using factory-boy
- **mocks/** - Mock objects and test utilities
- **strategies/** - Hypothesis strategies for property-based testing

## Running Tests

```bash
# Run all tests
pytest

# Run specific test type
pytest tests/unit/
pytest tests/integration/
pytest tests/property/
pytest tests/e2e/
pytest tests/structure/

# Run with coverage
pytest --cov=apps --cov-report=html
```

## Structure Guardrails

The project uses structure tests to prevent architectural regressions (cross-module coupling, wiring leakage, protocol drift).

```bash
python backend/apiSystem/manage.py check
pytest -q backend/tests/structure/test_cross_module_import_properties.py --no-cov
pytest -q backend/tests/structure/test_protocol_implementation_alignment.py --no-cov
pytest -q backend/tests/structure/test_service_locator_only_in_wiring.py --no-cov
```

## Test Organization

Tests are organized by module and test type:
- `tests/unit/test_<module>/` - Unit tests for a specific module
- `tests/integration/test_<module>_api/` - Integration tests for module APIs
- `tests/property/test_<module>_properties/` - Property-based tests for module

## Writing Tests

- Use factories from `tests/factories/` to create test data
- Use mocks from `tests/mocks/` to isolate dependencies
- Follow the AAA pattern: Arrange, Act, Assert
- Name tests descriptively: `test_<action>_<expected_result>`
