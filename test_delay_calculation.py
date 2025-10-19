#!/usr/bin/env python3

"""
Test the delay calculation fix to ensure reasonable delay values
"""

import logging
from datetime import datetime, timedelta
from active_trains import get_active_trains_manager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_delay_calculation():
    """Test delay calculation with various scenarios"""
    print("=== TESTING DELAY CALCULATION FIX ===")
    
    manager = get_active_trains_manager()
    
    # Find a train with schedule data
    test_train = None
    for train in manager.trains.values():
        if train.schedule and len(train.schedule.locations) > 2:
            test_train = train
            break
    
    if not test_train:
        print("No suitable train found for testing")
        return
    
    print(f"Testing with train {test_train.headcode} (UID: {test_train.uid})")
    
    # Get a location to test with
    locations = list(test_train.schedule.locations.keys())
    test_tiploc = locations[1] if len(locations) > 1 else locations[0]
    location = test_train.schedule.locations[test_tiploc]
    
    print(f"Testing at location {test_tiploc}")
    
    # Test scenario 1: Normal delay (5 minutes late)
    print("\n--- Test 1: Normal 5-minute delay ---")
    if location.arr_time:
        # Simulate arriving 5 minutes late
        base_time = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
        test_train.apply_realtime_update(
            tiploc=test_tiploc,
            timestamp=base_time,
            event_type="arr"
        )
        print(f"Applied arrival event at {base_time.strftime('%H:%M:%S')}")
        print(f"Location delay_minutes: {location.delay_minutes}")
    
    # Test scenario 2: Large timestamp difference (should be handled)
    print("\n--- Test 2: Large time difference (cross-midnight scenario) ---")
    if location.dep_time:
        # Simulate a scenario that might cause large delay calculation
        large_time = datetime.now().replace(hour=2, minute=0, second=0, microsecond=0)
        test_train.apply_realtime_update(
            tiploc=test_tiploc,
            timestamp=large_time,
            event_type="dep"
        )
        print(f"Applied departure event at {large_time.strftime('%H:%M:%S')}")
        print(f"Location delay_minutes: {location.delay_minutes}")

if __name__ == "__main__":
    test_delay_calculation()