#!/bin/bash
# Run STP indicator tests
# This targeted script runs tests specific to the STP indicator functionality

echo "Running STP indicator tests..."
echo "------------------------------"

# Individual test for STP main functionality
echo "1. Testing STP main functionality..."
python -m unittest tests/test_stp_main.py

# Test STP indicator API
echo -e "\n2. Testing STP indicator API..."
python -m unittest tests/test_stp_indicators_api.py

# Test STP precedence rules
echo -e "\n3. Testing STP precedence rules..."
python -m unittest tests/test_stp_precedence.py

echo -e "\nSTP tests completed!"