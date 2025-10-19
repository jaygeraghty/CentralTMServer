#!/usr/bin/env python3
"""
Run all unit tests for the CIF parser and related components.
"""
import os
import sys
import unittest
import argparse
import importlib.util

def is_server_test(file_path):
    """Return True if the test file contains server/network tests."""
    return "location_container" in file_path or "web_interface" in file_path

def load_test_from_file(file_path):
    """Load test from a specific file."""
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return unittest.defaultTestLoader.loadTestsFromModule(module)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CIF parser test suite")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--stp-only", action="store_true", help="Only run STP indicator tests")
    parser.add_argument("--with-servers", action="store_true", help="Also run tests that start servers")
    args = parser.parse_args()

    # Set verbosity level
    verbosity = 2 if args.verbose else 1

    # Ensure we can import test modules properly
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")

    test_suite = unittest.TestSuite()
    
    # Determine which tests to run
    if args.stp_only:
        # Only run STP-related tests
        stp_test_files = [
            os.path.join(tests_dir, f) for f in os.listdir(tests_dir)
            if f.startswith("test_stp") and f.endswith(".py")
        ]
        for file_path in stp_test_files:
            if not is_server_test(file_path) or args.with_servers:
                test_suite.addTest(load_test_from_file(file_path))
    else:
        # Discover all tests in the tests directory
        for root, _, files in os.walk(tests_dir):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    if not is_server_test(file_path) or args.with_servers:
                        try:
                            test_suite.addTest(load_test_from_file(file_path))
                        except Exception as e:
                            print(f"Error loading tests from {file_path}: {e}")

    # Print a summary of what we're running
    print(f"Running CIF parser tests with verbosity level {verbosity}")
    
    # Run the tests
    test_runner = unittest.TextTestRunner(verbosity=verbosity)
    result = test_runner.run(test_suite)
    
    # Print a summary of test results
    print("\nTest Result Summary:")
    print(f"Ran {result.testsRun} tests")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    # Exit with non-zero status if there were failures
    sys.exit(not result.wasSuccessful())