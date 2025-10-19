
"""
Test runner for time_utils that generates statistics and performance figures.
Run this file to get comprehensive test results and performance metrics.
"""

import unittest
import sys
import os
import time
from collections import defaultdict, Counter
import json

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from time_utils import (
    parse_cif_time,
    parse_cif_time_to_datetime,
    cif_time_to_iso_datetime,
    validate_cif_time_format
)


def generate_comprehensive_test_report():
    """Generate a comprehensive test report with statistics and figures."""
    
    print("="*80)
    print("TIME_UTILS COMPREHENSIVE TEST REPORT")
    print("="*80)
    print(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test data for comprehensive analysis
    test_cases = {
        # Valid basic times
        "0000": ("00:00:00", "valid_basic"),
        "0630": ("06:30:00", "valid_basic"), 
        "1200": ("12:00:00", "valid_basic"),
        "1810": ("18:10:00", "valid_basic"),
        "2359": ("23:59:00", "valid_basic"),
        
        # Valid times with half-seconds
        "0000H": ("00:00:30", "valid_half_second"),
        "0630H": ("06:30:30", "valid_half_second"),
        "1200H": ("12:00:30", "valid_half_second"),
        "1810H": ("18:10:30", "valid_half_second"),
        "2359H": ("23:59:30", "valid_half_second"),
        
        # Invalid cases
        "36H": (None, "invalid_format"),
        "2400": (None, "invalid_hour"),
        "1860": (None, "invalid_minute"),
        "ABCD": (None, "invalid_chars"),
        "123": (None, "invalid_length"),
        "12345": (None, "invalid_length"),
        "": (None, "invalid_empty"),
    }
    
    # Run tests and collect results
    results = {}
    performance_data = {}
    
    print("1. FUNCTIONAL TESTING")
    print("-" * 40)
    
    total_tests = len(test_cases)
    passed_tests = 0
    
    for input_time, (expected, category) in test_cases.items():
        # Time the function call
        start_time = time.perf_counter()
        actual = parse_cif_time(input_time)
        end_time = time.perf_counter()
        
        execution_time = (end_time - start_time) * 1000000  # Convert to microseconds
        
        is_correct = actual == expected
        if is_correct:
            passed_tests += 1
        
        results[input_time] = {
            'input': input_time,
            'expected': expected,
            'actual': actual,
            'correct': is_correct,
            'category': category,
            'execution_time_us': execution_time
        }
        
        status = "✓ PASS" if is_correct else "✗ FAIL"
        print(f"  {input_time:8} → {str(actual):12} {status:8} ({execution_time:.2f}μs)")
    
    accuracy = (passed_tests / total_tests) * 100
    print(f"\nOverall Accuracy: {passed_tests}/{total_tests} ({accuracy:.1f}%)")
    
    # Category analysis
    print("\n2. CATEGORY ANALYSIS")
    print("-" * 40)
    
    category_stats = defaultdict(lambda: {'total': 0, 'passed': 0})
    for result in results.values():
        cat = result['category']
        category_stats[cat]['total'] += 1
        if result['correct']:
            category_stats[cat]['passed'] += 1
    
    for category, stats in sorted(category_stats.items()):
        accuracy = (stats['passed'] / stats['total']) * 100
        print(f"  {category:20}: {stats['passed']:2}/{stats['total']:2} ({accuracy:5.1f}%)")
    
    # Performance analysis
    print("\n3. PERFORMANCE ANALYSIS")
    print("-" * 40)
    
    execution_times = [r['execution_time_us'] for r in results.values()]
    avg_time = sum(execution_times) / len(execution_times)
    min_time = min(execution_times)
    max_time = max(execution_times)
    
    print(f"  Average execution time: {avg_time:.2f}μs")
    print(f"  Minimum execution time: {min_time:.2f}μs")
    print(f"  Maximum execution time: {max_time:.2f}μs")
    
    # Performance by category
    print("\n  Performance by category:")
    for category in sorted(category_stats.keys()):
        cat_times = [r['execution_time_us'] for r in results.values() if r['category'] == category]
        if cat_times:
            cat_avg = sum(cat_times) / len(cat_times)
            print(f"    {category:20}: {cat_avg:.2f}μs avg")
    
    # Stress testing
    print("\n4. STRESS TESTING")
    print("-" * 40)
    
    stress_inputs = ["1230", "1230H", "INVALID"] * 1000
    
    start_time = time.perf_counter()
    stress_results = [parse_cif_time(t) for t in stress_inputs]
    end_time = time.perf_counter()
    
    total_stress_time = end_time - start_time
    operations_per_second = len(stress_inputs) / total_stress_time
    
    print(f"  Processed {len(stress_inputs)} operations in {total_stress_time:.3f}s")
    print(f"  Performance: {operations_per_second:,.0f} operations/second")
    print(f"  Average time per operation: {(total_stress_time / len(stress_inputs)) * 1000000:.2f}μs")
    
    # Memory usage simulation
    print("\n5. MEMORY USAGE ANALYSIS")
    print("-" * 40)
    
    import sys
    
    # Test memory usage with large datasets
    large_dataset = ["1230", "1230H"] * 10000
    
    # Measure memory before
    initial_size = sys.getsizeof(large_dataset)
    
    # Process dataset
    large_results = [parse_cif_time(t) for t in large_dataset]
    
    # Measure memory after
    results_size = sys.getsizeof(large_results)
    
    print(f"  Input dataset size: {initial_size:,} bytes")
    print(f"  Results dataset size: {results_size:,} bytes")
    print(f"  Memory efficiency ratio: {results_size/initial_size:.2f}")
    
    # Test various time formats for comprehensive coverage
    print("\n6. COMPREHENSIVE FORMAT TESTING")
    print("-" * 40)
    
    time_formats = []
    for hour in range(0, 24, 3):  # Every 3 hours
        for minute in [0, 15, 30, 45]:  # Quarter hours
            basic_time = f"{hour:02d}{minute:02d}"
            half_time = f"{hour:02d}{minute:02d}H"
            time_formats.extend([basic_time, half_time])
    
    format_results = []
    for time_format in time_formats:
        result = parse_cif_time(time_format)
        format_results.append(result is not None)
    
    format_success_rate = sum(format_results) / len(format_results) * 100
    print(f"  Tested {len(time_formats)} time formats")
    print(f"  Success rate: {format_success_rate:.1f}%")
    
    # Generate final summary
    print("\n7. FINAL SUMMARY")
    print("-" * 40)
    
    summary_stats = {
        'total_functional_tests': total_tests,
        'functional_accuracy': accuracy,
        'average_execution_time_us': avg_time,
        'stress_operations_per_second': operations_per_second,
        'format_coverage_success_rate': format_success_rate,
        'memory_efficiency_ratio': results_size/initial_size
    }
    
    print(f"  ✓ Functional Tests: {accuracy:.1f}% accuracy ({passed_tests}/{total_tests})")
    print(f"  ✓ Performance: {avg_time:.2f}μs average, {operations_per_second:,.0f} ops/sec")
    print(f"  ✓ Format Coverage: {format_success_rate:.1f}% success rate")
    print(f"  ✓ Memory Efficiency: {results_size/initial_size:.2f} ratio")
    
    # Overall assessment
    print(f"\n8. OVERALL ASSESSMENT")
    print("-" * 40)
    
    if accuracy >= 95 and avg_time < 10 and format_success_rate >= 95:
        assessment = "EXCELLENT"
    elif accuracy >= 90 and avg_time < 20 and format_success_rate >= 90:
        assessment = "GOOD"
    elif accuracy >= 80 and avg_time < 50 and format_success_rate >= 80:
        assessment = "ACCEPTABLE"
    else:
        assessment = "NEEDS IMPROVEMENT"
    
    print(f"  Overall Rating: {assessment}")
    
    if assessment == "EXCELLENT":
        print("  🎉 Time utilities are performing excellently!")
    elif assessment == "GOOD":
        print("  👍 Time utilities are performing well.")
    elif assessment == "ACCEPTABLE":
        print("  ⚠️  Time utilities are acceptable but could be improved.")
    else:
        print("  ❌ Time utilities need improvement.")
    
    print("\n" + "="*80)
    
    return summary_stats


def run_all_time_tests():
    """Run all time utility tests and generate report."""
    
    # Import test modules
    from test_time_parsing import TestCIFTimeParsing, TestTimeUtilsStatistics
    from test_time_edge_cases import TestTimeUtilsEdgeCases, TestTimeUtilsErrorReporting
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add all test cases
    suite.addTest(unittest.makeSuite(TestCIFTimeParsing))
    suite.addTest(unittest.makeSuite(TestTimeUtilsStatistics))
    suite.addTest(unittest.makeSuite(TestTimeUtilsEdgeCases))
    suite.addTest(unittest.makeSuite(TestTimeUtilsErrorReporting))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Generate comprehensive report
    stats = generate_comprehensive_test_report()
    
    return result, stats


if __name__ == '__main__':
    print("Starting comprehensive time_utils testing...")
    print()
    
    test_result, statistics = run_all_time_tests()
    
    print(f"\nTest Summary:")
    print(f"Tests run: {test_result.testsRun}")
    print(f"Failures: {len(test_result.failures)}")
    print(f"Errors: {len(test_result.errors)}")
    
    if test_result.failures:
        print("\nFailures:")
        for test, traceback in test_result.failures:
            print(f"  - {test}: {traceback}")
    
    if test_result.errors:
        print("\nErrors:")
        for test, traceback in test_result.errors:
            print(f"  - {test}: {traceback}")
    
    print(f"\nFinal Statistics: {statistics}")
