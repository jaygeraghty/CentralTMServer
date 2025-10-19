"""
Test train detection via forecast updates
"""

import pytest
from datetime import date
from active_trains import ActiveTrainsManager, ActiveTrain, ActiveSchedule, ActiveScheduleLocation, apply_forecast_update


def test_train_detection_via_forecast():
    """Test that trains are marked as detected when receiving forecast updates."""
    
    # Create manager with test train
    manager = ActiveTrainsManager()
    
    # Create test train (initially not detected)
    train = ActiveTrain(uid="P12345", headcode="1A23")
    train.detected = False  # Initially not detected
    train.schedule = ActiveSchedule(
        id=1, uid="P12345", stp_indicator="P", transaction_type="N",
        runs_from=date.today(), runs_to=date.today(),
        days_run="1111111", train_status="P", train_category="OO",
        train_identity="1A23", service_code="12345678",
        power_type="EMU", speed=100
    )
    train.schedule.locations = {
        "LONDON": ActiveScheduleLocation(
            sequence=1, tiploc="LONDON", location_type="LO",
            dep_time="10:00"
        ),
        "READING": ActiveScheduleLocation(
            sequence=2, tiploc="READING", location_type="LI",
            arr_time="10:30", dep_time="10:32"
        )
    }
    
    # Add train to manager
    manager.trains[train.uid] = train
    manager.trains_by_headcode[train.headcode] = train
    
    # Verify train is not detected initially
    assert not train.detected
    
    # Apply forecast update
    payload = {
        "uid": "P12345",
        "forecasts": [{
            "tiploc": "READING",
            "forecast_arrival": "10:33",
            "forecast_departure": "10:35",
            "delay_minutes": 3
        }]
    }
    
    result = apply_forecast_update(manager, payload)
    
    # Verify update was successful
    assert result is True
    
    # Verify train is now marked as detected
    assert train.detected
    
    # Verify forecast was applied
    reading_loc = train.schedule.locations["READING"]
    assert reading_loc.forecast_arr == "10:33"
    assert reading_loc.forecast_dep == "10:35"
    assert reading_loc.delay_minutes == 3


def test_already_detected_train():
    """Test logging when train is already detected."""
    
    # Create manager with already detected train
    manager = ActiveTrainsManager()
    
    train = ActiveTrain(uid="P67890", headcode="2B45")
    train.detected = True  # Already detected
    train.schedule = ActiveSchedule(
        id=2, uid="P67890", stp_indicator="P", transaction_type="N",
        runs_from=date.today(), runs_to=date.today(),
        days_run="1111111", train_status="P", train_category="OO",
        train_identity="2B45", service_code="87654321",
        power_type="DMU", speed=90
    )
    train.schedule.locations = {
        "BRISTOL": ActiveScheduleLocation(
            sequence=1, tiploc="BRISTOL", location_type="LO",
            dep_time="14:00"
        ),
        "BATH": ActiveScheduleLocation(
            sequence=2, tiploc="BATH", location_type="LI",
            arr_time="14:15", dep_time="14:17"
        )
    }
    
    manager.trains[train.uid] = train
    manager.trains_by_headcode[train.headcode] = train
    
    # Verify train is already detected
    assert train.detected
    
    # Apply forecast update
    payload = {
        "uid": "P67890",
        "forecasts": [{
            "tiploc": "BATH",
            "forecast_arrival": "14:18",
            "delay_minutes": 3
        }]
    }
    
    result = apply_forecast_update(manager, payload)
    
    # Verify update was successful
    assert result is True
    
    # Verify train remains detected
    assert train.detected
    
    # Verify forecast was applied
    bath_loc = train.schedule.locations["BATH"]
    assert bath_loc.forecast_arr == "14:18"
    assert bath_loc.delay_minutes == 3


def test_detection_via_headcode():
    """Test detection when finding train by headcode."""
    
    manager = ActiveTrainsManager()
    
    train = ActiveTrain(uid="P11111", headcode="3C67")
    train.detected = False
    train.schedule = ActiveSchedule(
        id=3, uid="P11111", stp_indicator="P", transaction_type="N",
        runs_from=date.today(), runs_to=date.today(),
        days_run="1111111", train_status="P", train_category="OO",
        train_identity="3C67", service_code="11111111",
        power_type="HST", speed=125
    )
    train.schedule.locations = {
        "MANCHESTER": ActiveScheduleLocation(
            sequence=1, tiploc="MANCHESTER", location_type="LO",
            dep_time="16:00"
        )
    }
    
    manager.trains[train.uid] = train
    manager.trains_by_headcode[train.headcode] = train
    
    # Apply forecast without UID (will find by headcode)
    payload = {
        "train_id": "3C67",  # No UID provided
        "forecasts": [{
            "tiploc": "MANCHESTER",
            "forecast_departure": "16:02",
            "delay_minutes": 2
        }]
    }
    
    result = apply_forecast_update(manager, payload)
    
    # Verify update was successful and train detected
    assert result is True
    assert train.detected


if __name__ == "__main__":
    # Run tests
    test_train_detection_via_forecast()
    test_already_detected_train() 
    test_detection_via_headcode()
    print("All train detection tests passed!")