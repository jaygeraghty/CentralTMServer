# tests/test_forecast_integration.py
import pytest
import datetime as dt
from datetime import datetime, date

from active_trains import (
    ActiveScheduleLocation,
    ActiveSchedule, 
    ActiveTrain,
    ActiveTrainsManager,
    apply_forecast_update,
    propagate_delay
)

def _build_test_train_with_pass():
    """Build a test train that includes pass-only locations"""
    locations = {}
    
    # Schedule: Origin -> Pass-only -> Stop -> Pass-only -> Terminus
    schedule_data = [
        ("ORIGIN", None, "10:00", "LO"),     # Start
        ("PASSA",  None, None,   "LI"),     # Pass-only location A
        ("STOP1",  "10:15", "10:17", "LI"), # Stopping location 
        ("PASSB",  None, None,   "LI"),     # Pass-only location B
        ("TERMIN", "10:30", None, "LT")     # Terminus
    ]
    
    for seq, (tiploc, arr, dep, loc_type) in enumerate(schedule_data, 1):
        # For pass-only locations, set pass_time
        pass_time = "10:05" if tiploc == "PASSA" else ("10:25" if tiploc == "PASSB" else None)
        
        locations[tiploc] = ActiveScheduleLocation(
            sequence=seq,
            tiploc=tiploc,
            location_type=loc_type,
            arr_time=arr,
            dep_time=dep,
            pass_time=pass_time,
            late_dwell_secs=30,
            recovery_secs=0
        )
    
    schedule = ActiveSchedule(
        id=1,
        uid="P12345",
        stp_indicator="P",
        transaction_type="N",
        runs_from=date(2025, 1, 1),
        runs_to=date(2025, 12, 31),
        days_run="1111111",
        train_status="P",
        train_category="OO",
        train_identity="2X50",
        service_code="12345678",
        power_type="EMU",
        locations=locations
    )
    
    return ActiveTrain(uid="P12345", headcode="2X50", schedule=schedule)


def test_forecast_arrival_and_departure():
    """Test forecast with both arrival and departure times"""
    train = _build_test_train_with_pass()
    manager = ActiveTrainsManager()
    manager.trains[train.uid] = train
    
    # Forecast payload for stopping location
    payload = {
        "uid": "P12345",
        "forecasts": [{
            "tiploc": "STOP1",
            "forecast_arrival": "10:22",    # 7 min late
            "forecast_departure": "10:24",  # 7 min late  
            "delay_minutes": 7,
            "platform": "2"
        }]
    }
    
    # Apply forecast update
    result = apply_forecast_update(manager, payload)
    assert result is True
    
    # Check forecast was stored
    loc = train.schedule.locations["STOP1"]
    assert loc.forecast_arr == "10:22"
    assert loc.forecast_dep == "10:24" 
    assert loc.delay_minutes == 7
    assert loc.forecast_platform == "2"
    
    # Check predictions were set
    assert loc.pred_arr == "10:22"
    assert loc.pred_dep == "10:24"
    assert loc.pred_delay_min == 7
    
    # Check downstream propagation to terminus
    termin_loc = train.schedule.locations["TERMIN"]
    assert termin_loc.pred_arr == "10:37"  # 10:30 + 7 min delay
    assert termin_loc.pred_delay_min == 7


def test_forecast_pass_only():
    """Test forecast with pass time only (no arrival/departure)"""
    train = _build_test_train_with_pass()
    manager = ActiveTrainsManager()
    manager.trains[train.uid] = train
    
    # Forecast payload for pass-only location
    payload = {
        "uid": "P12345", 
        "forecasts": [{
            "tiploc": "PASSA",
            "forecast_pass": "10:10",      # 5 min late
            "delay_minutes": 5
        }]
    }
    
    # Apply forecast update
    result = apply_forecast_update(manager, payload)
    assert result is True
    
    # Check pass forecast was stored
    loc = train.schedule.locations["PASSA"]
    assert loc.forecast_pass == "10:10"
    assert loc.delay_minutes == 5
    assert loc.forecast_arr is None
    assert loc.forecast_dep is None
    
    # Check pass prediction was set
    assert loc.pred_pass == "10:10"
    assert loc.pred_delay_min == 5
    assert loc.pred_arr is None
    assert loc.pred_dep is None
    
    # Check downstream synthetic predictions
    stop1_loc = train.schedule.locations["STOP1"]
    assert stop1_loc.pred_arr == "10:20"   # 10:15 + 5 min delay
    # Departure has dwell trimming applied:
    # Booked dwell: 2 min, Late dwell: 30 sec, Trim: 90 sec
    # Recovery: min(5 min delay, 90 sec) = 90 sec = 1.5 min
    # So departure: 10:20 arrival + 30 sec = 10:20:30 ≈ 10:20
    assert stop1_loc.pred_dep == "10:20"   # Trimmed departure time
    assert stop1_loc.pred_delay_min < 5    # Reduced due to dwell recovery


def test_forecast_multiple_locations():
    """Test forecast update with multiple locations"""
    train = _build_test_train_with_pass()
    manager = ActiveTrainsManager()
    manager.trains[train.uid] = train
    
    # Multiple forecasts in one payload
    payload = {
        "uid": "P12345",
        "forecasts": [
            {
                "tiploc": "PASSA",
                "forecast_pass": "10:08",   # 3 min late
                "delay_minutes": 3
            },
            {
                "tiploc": "STOP1", 
                "forecast_arrival": "10:20", # 5 min late
                "forecast_departure": "10:22", # 5 min late
                "delay_minutes": 5,
                "platform": "1"
            }
        ]
    }
    
    # Apply forecast update
    result = apply_forecast_update(manager, payload)
    assert result is True
    
    # Check first location (pass-only)
    passa_loc = train.schedule.locations["PASSA"]
    assert passa_loc.pred_pass == "10:08"
    assert passa_loc.pred_delay_min == 3
    
    # Check second location (stopping)
    stop1_loc = train.schedule.locations["STOP1"]
    assert stop1_loc.pred_arr == "10:20"
    assert stop1_loc.pred_dep == "10:22"
    assert stop1_loc.pred_delay_min == 5
    assert stop1_loc.forecast_platform == "1"
    
    # Terminus should use delay from last forecast (5 min)
    termin_loc = train.schedule.locations["TERMIN"]
    assert termin_loc.pred_arr == "10:35"  # 10:30 + 5 min
    assert termin_loc.pred_delay_min == 5


def test_forecast_with_dwell_trimming():
    """Test that forecast propagation applies dwell trimming at stops"""
    train = _build_test_train_with_pass()
    manager = ActiveTrainsManager()
    manager.trains[train.uid] = train
    
    # Large delay at origin to test dwell trimming
    payload = {
        "uid": "P12345",
        "forecasts": [{
            "tiploc": "ORIGIN",
            "forecast_departure": "10:10",  # 10 min late
            "delay_minutes": 10
        }]
    }
    
    # Apply forecast update
    result = apply_forecast_update(manager, payload)
    assert result is True
    
    # Check origin
    origin_loc = train.schedule.locations["ORIGIN"]
    assert origin_loc.pred_dep == "10:10"
    assert origin_loc.pred_delay_min == 10
    
    # Check stopping location - should have dwell trimming applied
    stop1_loc = train.schedule.locations["STOP1"]
    # Arrival: 10:15 + 10 min = 10:25
    # Booked dwell: 2 min, late dwell: 30 sec
    # Trim: 2 min - 30 sec = 90 sec
    # Recovery: min(10 min, 90 sec) = 90 sec
    # New departure should be earlier due to trimming
    assert stop1_loc.pred_arr == "10:25"
    # Departure should be trimmed - exact time depends on dwell logic
    assert stop1_loc.pred_delay_min < 10  # Should be less than 10 due to recovery


def test_forecast_invalid_train():
    """Test forecast for non-existent train"""
    manager = ActiveTrainsManager()
    
    payload = {
        "uid": "INVALID",
        "forecasts": [{
            "tiploc": "ORIGIN",
            "forecast_departure": "10:10",
            "delay_minutes": 5
        }]
    }
    
    result = apply_forecast_update(manager, payload)
    assert result is False


def test_forecast_invalid_location():
    """Test forecast for invalid location on valid train"""
    train = _build_test_train_with_pass()
    manager = ActiveTrainsManager()
    manager.trains[train.uid] = train
    
    payload = {
        "uid": "P12345",
        "forecasts": [{
            "tiploc": "INVALID",  # Not in this train's schedule
            "forecast_departure": "10:10",
            "delay_minutes": 5
        }]
    }
    
    result = apply_forecast_update(manager, payload)
    # Should return True but not update anything
    assert result is False  # No valid forecasts processed


def test_forecast_no_delay_minutes():
    """Test forecast without delay_minutes field"""
    train = _build_test_train_with_pass()
    manager = ActiveTrainsManager()
    manager.trains[train.uid] = train
    
    payload = {
        "uid": "P12345",
        "forecasts": [{
            "tiploc": "ORIGIN",
            "forecast_departure": "10:10"
            # No delay_minutes field
        }]
    }
    
    result = apply_forecast_update(manager, payload)
    assert result is True
    
    # Check forecast was stored but delay is None
    loc = train.schedule.locations["ORIGIN"]
    assert loc.forecast_dep == "10:10"
    assert loc.delay_minutes is None
    
    # Should still trigger propagation with delay = 0
    assert loc.pred_dep == "10:10"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])