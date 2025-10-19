#!/usr/bin/env python3
"""
Test script to verify train selection logic within the web server process
"""

import requests
import json

def test_train_selection():
    """Test the improved train selection logic"""
    
    print("Testing improved train selection logic...")
    
    # Step 1: Send forecast update for UID P19414 (should map to headcode 1V34)
    print("\n1. Sending forecast update for UID P19414...")
    forecast_payload = {
        "uid": "P19414", 
        "train_id": "1V50",
        "forecasts": [
            {
                "tiploc": "CHRX",
                "forecast_departure": "08:45:00",
                "delay_minutes": 5,
                "platform": "6"
            }
        ]
    }
    
    response = requests.post(
        "http://localhost:5000/api/trains/forecast_update",
        json=forecast_payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        print("✓ Forecast update successful")
    else:
        print(f"✗ Forecast update failed: {response.status_code}")
        return
    
    # Step 2: Get active trains status to verify train count
    print("\n2. Checking active trains status...")
    status_response = requests.get("http://localhost:5000/api/active_trains/status")
    
    if status_response.status_code == 200:
        status_data = status_response.json()
        print(f"✓ Active trains: {status_data.get('train_count', 'unknown')}")
        print(f"✓ System status: {status_data.get('status', 'unknown')}")
    else:
        print(f"✗ Status check failed: {status_response.status_code}")
    
    # Step 3: Check if we can find train P19414 in the active trains list
    print("\n3. Searching for train P19414 in active trains...")
    trains_response = requests.get("http://localhost:5000/api/active_trains/list?limit=100")
    
    if trains_response.status_code == 200:
        trains_data = trains_response.json()
        trains = trains_data.get('trains', [])
        
        # Look for P19414
        p19414_train = None
        for train in trains:
            if train.get('uid') == 'P19414':
                p19414_train = train
                break
        
        if p19414_train:
            print(f"✓ Found train P19414: headcode={p19414_train.get('headcode')}, detected={p19414_train.get('detected')}")
            
            # Check if it's marked as detected (this is the key fix)
            if p19414_train.get('detected'):
                print("✓ Train correctly marked as detected - train selection will work")
            else:
                print("✗ Train not marked as detected - train selection will fail")
        else:
            print("✗ Train P19414 not found in active trains list")
    else:
        print(f"✗ Failed to get active trains list: {trains_response.status_code}")
    
    print("\nTest completed!")

if __name__ == "__main__":
    test_train_selection()