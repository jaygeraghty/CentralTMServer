#!/usr/bin/env python3

"""
Test script to check delay propagation behavior and understand the numbers
"""

import logging
from datetime import datetime
from active_trains import get_active_trains_manager, apply_forecast_update, propagate_delay

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_forecast_propagation():
    """Test if forecast updates trigger propagation correctly"""
    print("\n=== TESTING FORECAST PROPAGATION ===")
    
    manager = get_active_trains_manager()
    
    # Get a train to test with
    test_train = None
    for train in manager.trains.values():
        if train.schedule and len(train.schedule.locations) > 3:
            test_train = train
            break
    
    if not test_train:
        print("No suitable test train found")
        return
    
    print(f"Testing with train {test_train.headcode} (UID: {test_train.uid})")
    print(f"Train has {len(test_train.schedule.locations)} locations")
    
    # Get first location for forecast
    first_tiploc = list(test_train.schedule.locations.keys())[1]  # Skip first, use second
    
    print(f"Applying forecast update to location: {first_tiploc}")
    
    # Create forecast update
    forecast_payload = {
        "uid": test_train.uid,
        "train_id": test_train.headcode,
        "forecasts": [{
            "tiploc": first_tiploc,
            "forecast_arrival": "15:32",
            "forecast_departure": "15:35",
            "delay_minutes": 7
        }]
    }
    
    # Apply forecast update
    result = apply_forecast_update(manager, forecast_payload)
    print(f"Forecast update result: {result}")
    
    # Check if train is now detected
    print(f"Train detected status: {test_train.detected}")
    
    # Check what happened to locations
    location = test_train.schedule.locations[first_tiploc]
    print(f"Location {first_tiploc}:")
    print(f"  forecast_arr: {location.forecast_arr}")
    print(f"  forecast_dep: {location.forecast_dep}")
    print(f"  pred_arr: {location.pred_arr}")
    print(f"  pred_dep: {location.pred_dep}")
    print(f"  delay_minutes: {location.delay_minutes}")

def test_realtime_propagation():
    """Test real-time event and see what the numbers mean"""
    print("\n=== TESTING REAL-TIME PROPAGATION ===")
    
    manager = get_active_trains_manager()
    
    # Find a detected train
    detected_train = None
    for train in manager.trains.values():
        if train.detected and train.schedule and len(train.schedule.locations) > 5:
            detected_train = train
            break
    
    if not detected_train:
        # Mark a train as detected for testing
        for train in manager.trains.values():
            if train.schedule and len(train.schedule.locations) > 5:
                train.detected = True
                detected_train = train
                break
    
    if not detected_train:
        print("No suitable detected train found")
        return
    
    print(f"Testing with detected train {detected_train.headcode} (UID: {detected_train.uid})")
    print(f"Train has {len(detected_train.schedule.locations)} locations")
    
    # Get a middle location for the event
    location_list = list(detected_train.schedule.locations.keys())
    middle_idx = len(location_list) // 2
    test_tiploc = location_list[middle_idx]
    
    print(f"Simulating arrival event at location: {test_tiploc} (location {middle_idx + 1} of {len(location_list)})")
    
    # Simulate a real-time arrival event
    timestamp = datetime.now()
    detected_train.apply_realtime_update(
        tiploc=test_tiploc,
        timestamp=timestamp,
        event_type="arr",
        from_berth="TEST123",
        to_berth="TEST124"
    )
    
    print("Real-time event applied - check logs above for propagation details")

def analyze_train_locations():
    """Analyze a typical train to understand the location count"""
    print("\n=== ANALYZING TRAIN LOCATIONS ===")
    
    manager = get_active_trains_manager()
    
    # Get first few trains and show their location counts
    trains_checked = 0
    for train in manager.trains.values():
        if trains_checked >= 5:
            break
        if train.schedule:
            loc_count = len(train.schedule.locations)
            print(f"Train {train.headcode}: {loc_count} locations")
            
            # Show first few locations
            locations = list(train.schedule.locations.keys())[:5]
            print(f"  First 5 locations: {locations}")
            trains_checked += 1

if __name__ == "__main__":
    print("Testing delay propagation behavior...")
    
    # Analyze typical train structure
    analyze_train_locations()
    
    # Test forecast propagation
    test_forecast_propagation()
    
    # Test real-time propagation  
    test_realtime_propagation()
    
    print("\nTest complete - check the logs above to understand the numbers")