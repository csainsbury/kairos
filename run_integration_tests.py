#!/usr/bin/env python
"""Integration test runner for kAIros application"""

import os
import sys
import pytest
import argparse
import coverage
from pathlib import Path

# Add the kAIros directory to path so imports work
KAIROS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(KAIROS_DIR))

def run_tests():
    """Run the kAIros integration test suite"""
    parser = argparse.ArgumentParser(description='Run kAIros integration tests')
    parser.add_argument('--coverage', action='store_true', help='Run with coverage reporting')
    parser.add_argument('--html-cov', action='store_true', help='Generate HTML coverage reports')
    parser.add_argument('--postgres', action='store_true', help='Run tests with PostgreSQL')
    parser.add_argument('--env', choices=['development', 'testing', 'production'], 
                       default='testing', help='Environment to run tests in')
    parser.add_argument('--module', help='Run tests for a specific module')
    parser.add_argument('--skip-e2e', action='store_true', help='Skip end-to-end tests')
    
    args = parser.parse_args()
    
    # Set testing environment
    os.environ['FLASK_ENV'] = args.env
    
    # Configure test database
    if args.postgres:
        os.environ['USE_POSTGRES_FOR_TESTS'] = '1'
        print("Using PostgreSQL for tests")
    else:
        os.environ['USE_POSTGRES_FOR_TESTS'] = '0'
        print("Using SQLite for tests")
    
    # Determine which tests to run
    test_path = 'tests/'
    if args.module:
        test_path = f'tests/test_{args.module}.py'
    
    # Skip E2E tests if requested
    if args.skip_e2e:
        pytest_args = ['-k', 'not test_end_to_end_workflow']
    else:
        pytest_args = []
    
    # Add verbosity
    pytest_args.extend(['-v'])
    
    # Add test path
    pytest_args.append(test_path)
    
    # Run with coverage if requested
    if args.coverage:
        cov = coverage.Coverage(
            source=['app'],
            omit=[
                '*/migrations/*',
                '*/tests/*',
                '*/venv/*',
                '*/env/*',
            ]
        )
        cov.start()
        result = pytest.main(pytest_args)
        cov.stop()
        
        # Print coverage report
        print("\nCoverage Report:")
        cov.report()
        
        # Generate HTML report if requested
        if args.html_cov:
            cov_dir = 'htmlcov'
            print(f"\nGenerating HTML coverage report in {cov_dir}/")
            cov.html_report(directory=cov_dir)
        
        return result
    else:
        # Run tests without coverage
        return pytest.main(pytest_args)

if __name__ == '__main__':
    sys.exit(run_tests() or 0)  # Exit with pytest status code