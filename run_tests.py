#!/usr/bin/env python
"""
Run all tests in the tests directory.

This script automatically discovers and runs all test cases in the tests directory.
It can be executed with different verbosity levels and filtering options.

Usage:
    python run_tests.py               # Run all tests
    python run_tests.py -v            # Run with verbose output
    python run_tests.py --stp-only    # Run only STP-related tests
"""
import os
import sys
import unittest
import argparse
import importlib.util


def should_exclude_test(test_file):
    """
    Return True if the test file should be excluded from automatic testing.
    Exclude tests that start servers or require network connections.
    """
    # Files that start servers or need special handling
    exclude_list = [
        "test_location_container.py",
        "test_web_interface.py"
    ]
    return any(test_file.endswith(excluded) for excluded in exclude_list)

def get_test_pattern(args):
    """Return the test pattern based on command line arguments."""
    if args.stp_only:
        return "test_stp*.py"
    return "test_*.py"


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run CIF parser test suite")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--stp-only", action="store_true", help="Only run STP indicator tests")
    args = parser.parse_args()

    # Set verbosity level
    verbosity = 2 if args.verbose else 1

    # Ensure we can import test modules properly
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Configure test discovery
    test_pattern = get_test_pattern(args)
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    
    # Discover and run the tests
    print(f"Running tests from {tests_dir} matching {test_pattern}")
    start_dir = tests_dir
    
    # Create a custom test suite to avoid problematic tests
    test_suite = unittest.TestSuite()
    
    # Manually load test modules, excluding problematic ones
    for root, _, files in os.walk(tests_dir):
        for file in sorted(files):
            if file.startswith("test_") and file.endswith(".py"):
                if should_exclude_test(file):
                    print(f"Skipping {file} (excluded from auto-testing)")
                    continue
                
                if test_pattern != "test_*.py" and not file.startswith(test_pattern[:-3]):
                    continue
                
                file_path = os.path.join(root, file)
                module_name = os.path.splitext(file)[0]
                
                # Dynamic module import
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    try:
                        spec.loader.exec_module(module)
                        tests = unittest.defaultTestLoader.loadTestsFromModule(module)
                        test_suite.addTest(tests)
                        print(f"Loaded tests from {file}")
                    except Exception as e:
                        print(f"Error loading tests from {file}: {e}")
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(test_suite)
    
    # Print a summary of test results
    print("\nTest Result Summary:")
    print(f"Ran {result.testsRun} tests")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    # Exit with non-zero status if there were failures or errors
    if not result.wasSuccessful():
        sys.exit(1)
    sys.exit(0)