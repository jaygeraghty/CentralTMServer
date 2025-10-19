#!/bin/bash
# Run all core tests for the CIF parser
# This script avoids tests that start servers or require external connections

echo "Running STP indicator tests..."
python -m unittest tests/test_stp_main.py tests/test_stp_integration.py tests/test_stp_indicators_api.py tests/test_stp_precedence.py

echo -e "\nRunning CIF parser basic tests..."
python -m unittest tests/test_cif_parser_basic.py

echo -e "\nAll tests completed!"