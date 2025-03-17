# Test runner for kAIros

import unittest
import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def run_tests(postgres=False, coverage=False):
    """Run tests with coverage report if requested"""
    if coverage:
        import coverage
        cov = coverage.Coverage(source=['app'])
        cov.start()
    
    # Load all tests
    test_loader = unittest.TestLoader()
    if postgres:
        # Run all tests including PostgreSQL
        test_suite = test_loader.discover('tests')
    else:
        # Skip PostgreSQL tests
        test_suite = unittest.TestSuite()
        for test in test_loader.discover('tests'):
            for suite in test:
                if 'postgres' not in suite.id().lower():
                    test_suite.addTest(suite)
    
    # Run the tests
    result = unittest.TextTestRunner(verbosity=2).run(test_suite)
    
    if coverage:
        cov.stop()
        cov.save()
        print("\nCoverage Summary:")
        cov.report()
        cov.html_report(directory='coverage_html')
        print("HTML version: coverage_html/index.html")
    
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run kAIros unit tests')
    parser.add_argument('--postgres', action='store_true', 
                      help='Include PostgreSQL tests (requires DB connection)')
    parser.add_argument('--coverage', action='store_true',
                      help='Generate coverage report')
    args = parser.parse_args()
    
    # Run the tests
    sys.exit(run_tests(postgres=args.postgres, coverage=args.coverage))