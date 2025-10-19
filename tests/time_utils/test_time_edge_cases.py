
"""
Edge case and error handling tests for time_utils module.
Tests boundary conditions, error states, and unusual inputs.
"""

import unittest
import sys
import os
from datetime import datetime

# Add parent directory to path to import time_utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from time_utils import (
    parse_cif_time,
    parse_cif_time_to_datetime,
    cif_time_to_iso_datetime,
    validate_cif_time_format
)


class TestTimeUtilsEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions for time utilities."""
    
    def test_boundary_times(self):
        """Test boundary time values."""
        # Valid boundaries
        self.assertEqual(parse_cif_time("0000"), "00:00:00")
        self.assertEqual(parse_cif_time("2359"), "23:59:00")
        self.assertEqual(parse_cif_time("0000H"), "00:00:30")
        self.assertEqual(parse_cif_time("2359H"), "23:59:30")
        
        # Invalid boundaries
        self.assertIsNone(parse_cif_time("2400"))  # Hour 24 invalid
        self.assertIsNone(parse_cif_time("1360"))  # Minute 60 invalid
        self.assertIsNone(parse_cif_time("2500"))  # Hour 25 invalid
    
    def test_malformed_inputs(self):
        """Test various malformed input strings."""
        malformed_inputs = [
            "",           # Empty string
            "   ",        # Whitespace
            "123",        # Too short
            "12345",      # Too long
            "12:34",      # Contains colon
            "12.34",      # Contains period
            "12 34",      # Contains space
            "12-34",      # Contains dash
            "1234X",      # Invalid suffix
            "H1234",      # H at beginning
            "12H34",      # H in middle
            "1234HH",     # Multiple H
            "\n1234",     # Leading newline
            "1234\n",     # Trailing newline
            "\t1234",     # Leading tab
            "1234\t",     # Trailing tab
        ]
        
        for malformed in malformed_inputs:
            with self.subTest(input=repr(malformed)):
                self.assertIsNone(parse_cif_time(malformed))
                self.assertFalse(validate_cif_time_format(malformed))
    
    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters."""
        special_inputs = [
            "１２３４",      # Full-width numbers
            "1234″",       # Prime symbol
            "1234°",       # Degree symbol
            "1234…",       # Ellipsis
            "1234–",       # En dash
            "1234—",       # Em dash
            "1234'",       # Apostrophe
            "1234"",       # Smart quote
            "1234※",       # Reference mark
            "①②③④",       # Circled numbers
        ]
        
        for special in special_inputs:
            with self.subTest(input=repr(special)):
                self.assertIsNone(parse_cif_time(special))
    
    def test_numeric_edge_cases(self):
        """Test numeric edge cases and unusual number formats."""
        numeric_edge_cases = [
            "0000",    # All zeros (valid)
            "0001",    # Leading zeros (valid)
            "0100",    # Hour only (valid)
            "0010",    # Minute only (valid)
            "-123",    # Negative (invalid)
            "+123",    # Plus sign (invalid)
            "12.0",    # Float format (invalid)
            "1e23",    # Scientific notation (invalid)
            "0x12",    # Hexadecimal (invalid)
            "0o12",    # Octal (invalid)
            "0b10",    # Binary (invalid)
        ]
        
        expected_results = {
            "0000": "00:00:00",
            "0001": "00:01:00",
            "0100": "01:00:00",
            "0010": "00:10:00",
        }
        
        for numeric_case in numeric_edge_cases:
            with self.subTest(input=numeric_case):
                result = parse_cif_time(numeric_case)
                if numeric_case in expected_results:
                    self.assertEqual(result, expected_results[numeric_case])
                else:
                    self.assertIsNone(result)
    
    def test_none_and_type_errors(self):
        """Test handling of None and incorrect types."""
        # None inputs
        self.assertIsNone(parse_cif_time(None))
        self.assertIsNone(parse_cif_time_to_datetime(None, datetime.now()))
        self.assertIsNone(cif_time_to_iso_datetime(None, "2025-05-30"))
        self.assertFalse(validate_cif_time_format(None))
        
        # Test with various incorrect types (should not crash)
        incorrect_types = [
            123,         # Integer
            12.34,       # Float
            [],          # List
            {},          # Dict
            set(),       # Set
            object(),    # Object
        ]
        
        for incorrect_type in incorrect_types:
            with self.subTest(type=type(incorrect_type).__name__):
                # These should either return None or raise appropriate exceptions
                try:
                    result = parse_cif_time(incorrect_type)
                    self.assertIsNone(result)
                except (TypeError, AttributeError):
                    # These exceptions are acceptable for wrong types
                    pass
    
    def test_datetime_edge_cases(self):
        """Test datetime conversion edge cases."""
        test_date = datetime(2025, 2, 28)  # Non-leap year
        
        # Valid conversions
        result = parse_cif_time_to_datetime("0000", test_date)
        expected = test_date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.assertEqual(result, expected)
        
        result = parse_cif_time_to_datetime("2359H", test_date)
        expected = test_date.replace(hour=23, minute=59, second=30, microsecond=0)
        self.assertEqual(result, expected)
        
        # Test with leap year date
        leap_date = datetime(2024, 2, 29)
        result = parse_cif_time_to_datetime("1230", leap_date)
        expected = leap_date.replace(hour=12, minute=30, second=0, microsecond=0)
        self.assertEqual(result, expected)
    
    def test_iso_datetime_edge_cases(self):
        """Test ISO datetime string conversion edge cases."""
        # Various date formats
        date_formats = [
            "2025-05-30",    # Standard format
            "2025-01-01",    # New Year
            "2025-12-31",    # Year end
            "2024-02-29",    # Leap year
        ]
        
        for date_str in date_formats:
            with self.subTest(date=date_str):
                result = cif_time_to_iso_datetime("1230H", date_str)
                expected = f"{date_str}T12:30:30"
                self.assertEqual(result, expected)
    
    def test_memory_and_performance_stress(self):
        """Test memory usage and performance under stress."""
        import gc
        
        # Test with many rapid conversions
        large_input_set = ["1230", "1230H"] * 10000
        
        # Force garbage collection before test
        gc.collect()
        
        # Process large set
        results = []
        for time_str in large_input_set:
            result = parse_cif_time(time_str)
            results.append(result)
        
        # Verify all results are correct
        expected_results = ["12:30:00", "12:30:30"] * 10000
        self.assertEqual(results, expected_results)
        
        # Force garbage collection after test
        gc.collect()
    
    def test_concurrent_access_simulation(self):
        """Simulate concurrent access patterns."""
        import threading
        import time
        
        results = []
        errors = []
        
        def worker(thread_id):
            """Worker function for threading test."""
            try:
                for i in range(100):
                    time_str = f"{(thread_id % 24):02d}{(i % 60):02d}"
                    if i % 2 == 0:
                        time_str += "H"
                    
                    result = parse_cif_time(time_str)
                    results.append((thread_id, i, result))
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Create and start threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Threading errors: {errors}")
        
        # Verify we got expected number of results
        self.assertEqual(len(results), 500)  # 5 threads × 100 iterations


class TestTimeUtilsErrorReporting(unittest.TestCase):
    """Test error reporting and logging in time utilities."""
    
    def test_error_logging_capture(self):
        """Test that errors are properly logged."""
        import logging
        from io import StringIO
        
        # Create a string buffer to capture log output
        log_buffer = StringIO()
        handler = logging.StreamHandler(log_buffer)
        handler.setLevel(logging.WARNING)
        
        # Get the time_utils logger and add our handler
        logger = logging.getLogger('time_utils')
        original_level = logger.level
        logger.setLevel(logging.WARNING)
        logger.addHandler(handler)
        
        try:
            # Generate some errors that should be logged
            parse_cif_time("INVALID")
            parse_cif_time("2500")
            parse_cif_time("1860")
            
            # Get log output
            log_output = log_buffer.getvalue()
            
            # Verify warnings were logged
            self.assertIn("Invalid", log_output)
            
        finally:
            # Clean up logging setup
            logger.removeHandler(handler)
            logger.setLevel(original_level)
            handler.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
