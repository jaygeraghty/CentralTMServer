
"""
Unit tests for time_utils parsing functions.
Tests all CIF time parsing functionality including half-second handling.
"""

import unittest
from datetime import datetime, date
import sys
import os

# Add parent directory to path to import time_utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from time_utils import (
    parse_cif_time,
    parse_cif_time_to_datetime,
    cif_time_to_iso_datetime,
    validate_cif_time_format
)


class TestCIFTimeParsing(unittest.TestCase):
    """Test cases for CIF time parsing functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_date = datetime(2025, 5, 30)
        self.test_date_str = "2025-05-30"
    
    def test_parse_cif_time_basic(self):
        """Test basic CIF time parsing without half-seconds."""
        # Valid times
        self.assertEqual(parse_cif_time("0000"), "00:00:00")
        self.assertEqual(parse_cif_time("0630"), "06:30:00")
        self.assertEqual(parse_cif_time("1230"), "12:30:00")
        self.assertEqual(parse_cif_time("1810"), "18:10:00")
        self.assertEqual(parse_cif_time("2359"), "23:59:00")
    
    def test_parse_cif_time_with_half_seconds(self):
        """Test CIF time parsing with half-second indicator (H suffix)."""
        # Times with half-seconds (30 seconds added)
        self.assertEqual(parse_cif_time("0000H"), "00:00:30")
        self.assertEqual(parse_cif_time("0630H"), "06:30:30")
        self.assertEqual(parse_cif_time("1230H"), "12:30:30")
        self.assertEqual(parse_cif_time("1810H"), "18:10:30")
        self.assertEqual(parse_cif_time("2359H"), "23:59:30")
    
    def test_parse_cif_time_edge_cases(self):
        """Test edge cases for CIF time parsing."""
        # Boundary times
        self.assertEqual(parse_cif_time("2400"), None)  # Invalid hour
        self.assertEqual(parse_cif_time("1860"), None)  # Invalid minute
        self.assertEqual(parse_cif_time("25"), None)    # Too short
        self.assertEqual(parse_cif_time("12345"), None) # Too long
        
        # Empty/None cases
        self.assertIsNone(parse_cif_time(None))
        self.assertIsNone(parse_cif_time(""))
        self.assertIsNone(parse_cif_time("    "))
    
    def test_parse_cif_time_invalid_formats(self):
        """Test invalid CIF time formats."""
        # Non-numeric characters
        self.assertIsNone(parse_cif_time("12AB"))
        self.assertIsNone(parse_cif_time("AB12"))
        self.assertIsNone(parse_cif_time("1A2B"))
        
        # Invalid suffixes
        self.assertIsNone(parse_cif_time("1230X"))
        self.assertIsNone(parse_cif_time("1230HH"))
    
    def test_parse_cif_time_to_datetime_basic(self):
        """Test converting CIF times to datetime objects."""
        # Basic time conversion
        result = parse_cif_time_to_datetime("1810", self.test_date)
        expected = self.test_date.replace(hour=18, minute=10, second=0, microsecond=0)
        self.assertEqual(result, expected)
        
        # Midnight
        result = parse_cif_time_to_datetime("0000", self.test_date)
        expected = self.test_date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.assertEqual(result, expected)
    
    def test_parse_cif_time_to_datetime_with_half_seconds(self):
        """Test converting CIF times with half-seconds to datetime objects."""
        # Half-second conversion
        result = parse_cif_time_to_datetime("1810H", self.test_date)
        expected = self.test_date.replace(hour=18, minute=10, second=30, microsecond=0)
        self.assertEqual(result, expected)
        
        # Midnight with half-second
        result = parse_cif_time_to_datetime("0000H", self.test_date)
        expected = self.test_date.replace(hour=0, minute=0, second=30, microsecond=0)
        self.assertEqual(result, expected)
    
    def test_parse_cif_time_to_datetime_invalid(self):
        """Test datetime conversion with invalid inputs."""
        self.assertIsNone(parse_cif_time_to_datetime(None, self.test_date))
        self.assertIsNone(parse_cif_time_to_datetime("", self.test_date))
        self.assertIsNone(parse_cif_time_to_datetime("INVALID", self.test_date))
        self.assertIsNone(parse_cif_time_to_datetime("2500", self.test_date))
    
    def test_cif_time_to_iso_datetime_basic(self):
        """Test converting CIF times to ISO datetime strings."""
        # Basic conversion
        result = cif_time_to_iso_datetime("1810", self.test_date_str)
        self.assertEqual(result, "2025-05-30T18:10:00")
        
        # Midnight
        result = cif_time_to_iso_datetime("0000", self.test_date_str)
        self.assertEqual(result, "2025-05-30T00:00:00")
        
        # Late evening
        result = cif_time_to_iso_datetime("2359", self.test_date_str)
        self.assertEqual(result, "2025-05-30T23:59:00")
    
    def test_cif_time_to_iso_datetime_with_half_seconds(self):
        """Test converting CIF times with half-seconds to ISO datetime strings."""
        # Half-second conversion
        result = cif_time_to_iso_datetime("1810H", self.test_date_str)
        self.assertEqual(result, "2025-05-30T18:10:30")
        
        # Midnight with half-second
        result = cif_time_to_iso_datetime("0000H", self.test_date_str)
        self.assertEqual(result, "2025-05-30T00:00:30")
        
        # Multiple half-second examples
        result = cif_time_to_iso_datetime("0936H", self.test_date_str)
        self.assertEqual(result, "2025-05-30T09:36:30")
    
    def test_cif_time_to_iso_datetime_invalid(self):
        """Test ISO datetime conversion with invalid inputs."""
        self.assertIsNone(cif_time_to_iso_datetime(None, self.test_date_str))
        self.assertIsNone(cif_time_to_iso_datetime("", self.test_date_str))
        self.assertIsNone(cif_time_to_iso_datetime("INVALID", self.test_date_str))
        self.assertIsNone(cif_time_to_iso_datetime("2500", self.test_date_str))
    
    def test_validate_cif_time_format_valid(self):
        """Test validation of valid CIF time formats."""
        # Valid times
        self.assertTrue(validate_cif_time_format("0000"))
        self.assertTrue(validate_cif_time_format("1810"))
        self.assertTrue(validate_cif_time_format("2359"))
        self.assertTrue(validate_cif_time_format("0000H"))
        self.assertTrue(validate_cif_time_format("1810H"))
        self.assertTrue(validate_cif_time_format("2359H"))
    
    def test_validate_cif_time_format_invalid(self):
        """Test validation of invalid CIF time formats."""
        # Invalid times
        self.assertFalse(validate_cif_time_format(""))
        self.assertFalse(validate_cif_time_format(None))
        self.assertFalse(validate_cif_time_format("12"))
        self.assertFalse(validate_cif_time_format("12345"))
        self.assertFalse(validate_cif_time_format("2400"))
        self.assertFalse(validate_cif_time_format("1860"))
        self.assertFalse(validate_cif_time_format("12AB"))
        self.assertFalse(validate_cif_time_format("AB12"))
    
    def test_real_world_examples(self):
        """Test with real-world CIF time examples that caused issues."""
        # The original error case: "36H" - this should be invalid
        self.assertIsNone(parse_cif_time("36H"))
        self.assertFalse(validate_cif_time_format("36H"))
        
        # But valid 4-digit times with H should work
        self.assertEqual(parse_cif_time("0036H"), "00:36:30")
        self.assertTrue(validate_cif_time_format("0036H"))
        
        # Common train schedule times
        train_times = [
            ("0630", "06:30:00"),
            ("0630H", "06:30:30"),
            ("0800", "08:00:00"),
            ("1215H", "12:15:30"),
            ("1730", "17:30:00"),
            ("2145H", "21:45:30")
        ]
        
        for cif_time, expected in train_times:
            with self.subTest(cif_time=cif_time):
                self.assertEqual(parse_cif_time(cif_time), expected)
    
    def test_performance_metrics(self):
        """Test performance with a large number of time conversions."""
        import time
        
        test_times = ["0630", "0630H", "1215", "1215H", "1730", "2145H"] * 1000
        
        start_time = time.time()
        results = [parse_cif_time(t) for t in test_times]
        end_time = time.time()
        
        # Should process 6000 times in reasonable time (< 1 second)
        processing_time = end_time - start_time
        self.assertLess(processing_time, 1.0, f"Processing took {processing_time:.3f}s")
        
        # All results should be valid
        self.assertEqual(len(results), 6000)
        self.assertTrue(all(r is not None for r in results))


class TestTimeUtilsStatistics(unittest.TestCase):
    """Test class that generates statistics about time parsing performance."""
    
    def test_generate_parsing_statistics(self):
        """Generate comprehensive statistics about time parsing."""
        from collections import Counter
        
        # Test various time formats
        test_cases = {
            # Format: (input, expected_output, category)
            "0000": ("00:00:00", "midnight"),
            "0000H": ("00:00:30", "midnight_half"),
            "0630": ("06:30:00", "morning"),
            "0630H": ("06:30:30", "morning_half"),
            "1200": ("12:00:00", "noon"),
            "1200H": ("12:00:30", "noon_half"),
            "1810": ("18:10:00", "evening"),
            "1810H": ("18:10:30", "evening_half"),
            "2359": ("23:59:00", "late_night"),
            "2359H": ("23:59:30", "late_night_half"),
            # Invalid cases
            "36H": (None, "invalid_short"),
            "2400": (None, "invalid_hour"),
            "1860": (None, "invalid_minute"),
            "ABCD": (None, "invalid_chars"),
        }
        
        results = {}
        categories = Counter()
        
        for input_time, (expected, category) in test_cases.items():
            actual = parse_cif_time(input_time)
            results[input_time] = {
                'input': input_time,
                'expected': expected,
                'actual': actual,
                'correct': actual == expected,
                'category': category
            }
            categories[category] += 1
        
        # Generate statistics
        total_tests = len(test_cases)
        correct_results = sum(1 for r in results.values() if r['correct'])
        accuracy = correct_results / total_tests * 100
        
        # Print comprehensive statistics
        print(f"\n{'='*60}")
        print(f"TIME UTILS PARSING STATISTICS")
        print(f"{'='*60}")
        print(f"Total test cases: {total_tests}")
        print(f"Correct results: {correct_results}")
        print(f"Accuracy: {accuracy:.1f}%")
        print(f"\nCategory breakdown:")
        for category, count in categories.most_common():
            print(f"  {category:20}: {count} cases")
        
        print(f"\nDetailed Results:")
        print(f"{'Input':8} {'Expected':12} {'Actual':12} {'Status':8} {'Category':15}")
        print(f"{'-'*60}")
        
        for result in results.values():
            status = "✓ PASS" if result['correct'] else "✗ FAIL"
            print(f"{result['input']:8} {str(result['expected']):12} {str(result['actual']):12} {status:8} {result['category']:15}")
        
        # Assert overall accuracy
        self.assertGreaterEqual(accuracy, 85.0, f"Accuracy too low: {accuracy:.1f}%")
        
        return {
            'total_tests': total_tests,
            'accuracy': accuracy,
            'categories': dict(categories),
            'detailed_results': results
        }


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
