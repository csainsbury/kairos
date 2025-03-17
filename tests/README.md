# kAIros Testing Framework

This directory contains the test suite for the kAIros application. The tests are organized to validate both individual components (unit tests) and integrated functionality (integration tests) across all modules of the application.

## Testing Structure

The kAIros testing framework includes:

- **Unit tests** for individual modules
- **Integration tests** for module interactions
- **End-to-end workflow tests** for complete user flows
- **Environment-specific tests** for development and production setups

## Running the Tests

### Using the Test Runner

The simplest way to run tests is using our test runner script:

```bash
# Run all tests with SQLite (default)
python run_integration_tests.py

# Run tests with coverage reporting
python run_integration_tests.py --coverage

# Generate HTML coverage reports
python run_integration_tests.py --coverage --html-cov

# Run tests for a specific module
python run_integration_tests.py --module calendar

# Skip end-to-end tests (faster for quick checks)
python run_integration_tests.py --skip-e2e

# Run tests in production mode
python run_integration_tests.py --env production

# Run tests with PostgreSQL
python run_integration_tests.py --postgres
```

### Using pytest Directly

You can also run the tests directly with pytest:

```bash
# Run all tests
pytest tests/

# Run a specific test file
pytest tests/test_integration.py

# Run with verbose output
pytest -v tests/

# Run a specific test
pytest tests/test_integration.py::test_calendar_event_creation
```

## Test Dependencies

The test suite has the following dependencies:

- pytest
- pytest-cov (for coverage reporting)
- unittest.mock (part of Python standard library)
- coverage (for detailed coverage analysis)

Install them using:

```bash
pip install pytest pytest-cov coverage
```

## Creating New Tests

When adding new features, please follow these guidelines for creating tests:

1. **Unit tests**: Create or update tests in the appropriate module-specific test file (e.g. `test_calendar.py` for calendar functionality)

2. **Integration tests**: Add tests to `test_integration.py` that verify the new feature works correctly with existing components

3. **Style guidelines**:
   - Use descriptive test names that explain what functionality is being tested
   - Include docstrings that explain the test purpose
   - Group related assertions together
   - Use fixtures for common setup/teardown
   - Mock external dependencies (APIs, email services, etc.)

4. **Test isolation**:
   - Each test should be independent and not rely on state from other tests
   - Use temporary database connections (SQLite :memory: when possible)
   - Clean up any files or resources created during tests

## Test Environment

Tests can run in three environments:

- **Development**: More verbose output, detailed error messages
- **Testing**: Default environment for CI/CD pipelines
- **Production**: Simulates production behavior with sanitized error messages

Set the environment using the `--env` flag with the test runner or by setting the `FLASK_ENV` environment variable.

## Database Testing

Tests can use either:

- **SQLite** (default): Fast, in-memory database ideal for unit tests
- **PostgreSQL**: For testing PostgreSQL-specific features

To use PostgreSQL for tests, you'll need:
1. A PostgreSQL server running
2. A test database created
3. Appropriate connection settings in your .env.testing file

## Continuous Integration

Tests are automatically run on:
- Push to main branch
- Pull request creation
- Scheduled daily runs

The CI pipeline uses GitHub Actions and runs tests in both SQLite and PostgreSQL configurations.

## Test Coverage

We aim to maintain at least 80% test coverage across the codebase. Generate and review coverage reports using:

```bash
python run_integration_tests.py --coverage --html-cov
```

Then open `htmlcov/index.html` in your browser to view the detailed report.