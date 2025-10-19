"""
Test data loader for STP indicator functionality testing.
This script populates test schedules with different STP indicators
to verify the web interface works correctly with our STP enhancements.
"""

import os
import sys
from datetime import date, datetime
from app import db
from models import (
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation
)

def create_test_data():
    """Create test data with STP indicators for testing the web interface"""
    print("Creating test data for STP indicator functionality...")
    
    # Common data for all schedules
    uid = "A12345"
    train_identity = "1A01"
    days_run = "1111100"  # Mon-Fri
    
    # 1. Create a permanent schedule for Jan-Dec 2025
    perm_schedule = ScheduleLTP()
    perm_schedule.uid = uid
    perm_schedule.train_identity = train_identity
    perm_schedule.train_category = "OO"
    perm_schedule.stp_indicator = "P"
    perm_schedule.transaction_type = "N"
    perm_schedule.runs_from = date(2025, 1, 1)
    perm_schedule.runs_to = date(2025, 12, 31)
    perm_schedule.days_run = days_run
    perm_schedule.train_status = "P"
    perm_schedule.service_code = "12345"
    perm_schedule.power_type = "EMU"
    perm_schedule.speed = 100
    db.session.add(perm_schedule)
    db.session.flush()  # Get the ID
    
    print(f"Created permanent schedule with ID: {perm_schedule.id}")
    
    # Add locations to permanent schedule
    locations = [
        {"sequence": 1, "location_type": "LO", "tiploc": "CHRX", "dep": "0900", "platform": "1"},
        {"sequence": 2, "location_type": "LI", "tiploc": "WLOE", "arr": "0903", "dep": "0904", "platform": "B"},
        {"sequence": 3, "location_type": "LI", "tiploc": "KNGX", "arr": "0915", "dep": "0917", "platform": "5"},
        {"sequence": 4, "location_type": "LT", "tiploc": "EUSTON", "arr": "0930", "platform": "8"}
    ]
    
    for loc_data in locations:
        loc = ScheduleLocationLTP()
        loc.schedule_id = perm_schedule.id
        for key, value in loc_data.items():
            setattr(loc, key, value)
        db.session.add(loc)
    
    # 2. Create a cancellation for July 2025
    cancel_schedule = ScheduleSTPCancellation()
    cancel_schedule.uid = uid
    cancel_schedule.train_identity = train_identity
    cancel_schedule.train_category = "OO"
    cancel_schedule.stp_indicator = "C"
    cancel_schedule.transaction_type = "N"
    cancel_schedule.runs_from = date(2025, 7, 1)
    cancel_schedule.runs_to = date(2025, 7, 31)
    cancel_schedule.days_run = days_run
    cancel_schedule.train_status = "P"
    cancel_schedule.service_code = "12345"
    cancel_schedule.power_type = "EMU"
    cancel_schedule.speed = 100
    db.session.add(cancel_schedule)
    db.session.flush()  # Get the ID
    
    print(f"Created cancellation schedule with ID: {cancel_schedule.id}")
    
    # Add the same locations to cancellation (for reference)
    for loc_data in locations:
        loc = ScheduleLocationSTPCancellation()
        loc.schedule_id = cancel_schedule.id
        for key, value in loc_data.items():
            setattr(loc, key, value)
        db.session.add(loc)
    
    # 3. Create a new schedule for July 2025 (to replace the cancelled one)
    new_schedule = ScheduleSTPNew()
    new_schedule.uid = uid + "NEW"  # Different UID as it's a new schedule
    new_schedule.train_identity = train_identity
    new_schedule.train_category = "OO"
    new_schedule.stp_indicator = "N"
    new_schedule.transaction_type = "N"
    new_schedule.runs_from = date(2025, 7, 1)
    new_schedule.runs_to = date(2025, 7, 31)
    new_schedule.days_run = days_run
    new_schedule.train_status = "P"
    new_schedule.service_code = "12345"
    new_schedule.power_type = "EMU"
    new_schedule.speed = 100
    db.session.add(new_schedule)
    db.session.flush()  # Get the ID
    
    print(f"Created new schedule with ID: {new_schedule.id}")
    
    # Add slightly different locations to new schedule (different times)
    new_locations = [
        {"sequence": 1, "location_type": "LO", "tiploc": "CHRX", "dep": "0910", "platform": "2"},
        {"sequence": 2, "location_type": "LI", "tiploc": "WLOE", "arr": "0913", "dep": "0914", "platform": "A"},
        {"sequence": 3, "location_type": "LI", "tiploc": "KNGX", "arr": "0925", "dep": "0927", "platform": "6"},
        {"sequence": 4, "location_type": "LT", "tiploc": "EUSTON", "arr": "0940", "platform": "9"}
    ]
    
    for loc_data in new_locations:
        loc = ScheduleLocationSTPNew()
        loc.schedule_id = new_schedule.id
        for key, value in loc_data.items():
            setattr(loc, key, value)
        db.session.add(loc)
    
    # 4. Create an overlay for May 2025 to change platform at Kings Cross
    overlay_schedule = ScheduleSTPOverlay()
    overlay_schedule.uid = uid
    overlay_schedule.train_identity = train_identity
    overlay_schedule.train_category = "OO"
    overlay_schedule.stp_indicator = "O"
    overlay_schedule.transaction_type = "N"
    overlay_schedule.runs_from = date(2025, 5, 1)
    overlay_schedule.runs_to = date(2025, 5, 31)
    overlay_schedule.days_run = days_run
    overlay_schedule.train_status = "P"
    overlay_schedule.service_code = "12345"
    overlay_schedule.power_type = "EMU"
    overlay_schedule.speed = 100
    db.session.add(overlay_schedule)
    db.session.flush()  # Get the ID
    
    print(f"Created overlay schedule with ID: {overlay_schedule.id}")
    
    # Add modified locations to overlay (different platform at Kings Cross)
    overlay_locations = [
        {"sequence": 1, "location_type": "LO", "tiploc": "CHRX", "dep": "0900", "platform": "1"},
        {"sequence": 2, "location_type": "LI", "tiploc": "WLOE", "arr": "0903", "dep": "0904", "platform": "B"},
        {"sequence": 3, "location_type": "LI", "tiploc": "KNGX", "arr": "0915", "dep": "0917", "platform": "10"},
        {"sequence": 4, "location_type": "LT", "tiploc": "EUSTON", "arr": "0930", "platform": "8"}
    ]
    
    for loc_data in overlay_locations:
        loc = ScheduleLocationSTPOverlay()
        loc.schedule_id = overlay_schedule.id
        for key, value in loc_data.items():
            setattr(loc, key, value)
        db.session.add(loc)
    
    # Add another permanent schedule with a different UID
    uid2 = "B54321"
    train_identity2 = "1B99"
    
    perm_schedule2 = ScheduleLTP()
    perm_schedule2.uid = uid2
    perm_schedule2.train_identity = train_identity2
    perm_schedule2.train_category = "OO"
    perm_schedule2.stp_indicator = "P"
    perm_schedule2.transaction_type = "N"
    perm_schedule2.runs_from = date(2025, 1, 1)
    perm_schedule2.runs_to = date(2025, 12, 31)
    perm_schedule2.days_run = days_run
    perm_schedule2.train_status = "P"
    perm_schedule2.service_code = "54321"
    perm_schedule2.power_type = "DMU"
    perm_schedule2.speed = 90
    db.session.add(perm_schedule2)
    db.session.flush()  # Get the ID
    
    print(f"Created second permanent schedule with ID: {perm_schedule2.id}")
    
    # Add locations to second permanent schedule
    locations2 = [
        {"sequence": 1, "location_type": "LO", "tiploc": "CHRX", "dep": "1000", "platform": "3"},
        {"sequence": 2, "location_type": "LI", "tiploc": "WLOE", "arr": "1003", "dep": "1004", "platform": "D"},
        {"sequence": 3, "location_type": "LT", "tiploc": "LNDNBDC", "arr": "1020", "platform": "1"}
    ]
    
    for loc_data in locations2:
        loc = ScheduleLocationLTP()
        loc.schedule_id = perm_schedule2.id
        for key, value in loc_data.items():
            setattr(loc, key, value)
        db.session.add(loc)
    
    db.session.commit()
    
    print("Test data creation complete.")
    print(f"Created {db.session.query(ScheduleLTP).count()} permanent schedules")
    print(f"Created {db.session.query(ScheduleSTPNew).count()} new schedules")
    print(f"Created {db.session.query(ScheduleSTPOverlay).count()} overlay schedules")
    print(f"Created {db.session.query(ScheduleSTPCancellation).count()} cancellation schedules")

if __name__ == "__main__":
    from app import app
    with app.app_context():
        create_test_data()