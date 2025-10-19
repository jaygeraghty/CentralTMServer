"""
Fix for STP indicator enhancements - Move location data to STP-specific tables
"""
import os
from datetime import date, datetime
from app import app, db
from sqlalchemy import text
from models import (
    BasicSchedule, ScheduleLocation, Association,
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation
)

def move_locations_to_stp_tables():
    """Move location data from legacy table to STP-specific tables based on schedule STP indicator"""
    print("Moving location data to STP-specific tables...")
    
    # Get all schedules from STP tables
    ltp_schedules = db.session.query(ScheduleLTP).all()
    print(f"Found {len(ltp_schedules)} LTP schedules")
    
    for schedule in ltp_schedules:
        # Find corresponding locations in legacy table
        locations = db.session.query(ScheduleLocation).filter_by(schedule_id=schedule.id).all()
        print(f"Found {len(locations)} locations for LTP schedule ID {schedule.id}")
        
        # Create entries in STP location table
        for loc in locations:
            stp_loc = ScheduleLocationLTP()
            stp_loc.schedule_id = schedule.id
            stp_loc.sequence = loc.sequence
            stp_loc.location_type = loc.location_type
            stp_loc.tiploc = loc.tiploc
            stp_loc.arr = loc.arr
            stp_loc.dep = loc.dep
            stp_loc.pass_time = loc.pass_time
            stp_loc.public_arr = loc.public_arr
            stp_loc.public_dep = loc.public_dep
            stp_loc.platform = loc.platform
            stp_loc.line = loc.line
            stp_loc.path = loc.path
            stp_loc.activity = loc.activity
            db.session.add(stp_loc)
        
        db.session.commit()
        print(f"Moved {len(locations)} locations to ScheduleLocationLTP for schedule ID {schedule.id}")
    
    # Do the same for New STP schedules
    new_schedules = db.session.query(ScheduleSTPNew).all()
    print(f"Found {len(new_schedules)} New STP schedules")
    
    for schedule in new_schedules:
        locations = db.session.query(ScheduleLocation).filter_by(schedule_id=schedule.id).all()
        print(f"Found {len(locations)} locations for New STP schedule ID {schedule.id}")
        
        for loc in locations:
            stp_loc = ScheduleLocationSTPNew()
            stp_loc.schedule_id = schedule.id
            stp_loc.sequence = loc.sequence
            stp_loc.location_type = loc.location_type
            stp_loc.tiploc = loc.tiploc
            stp_loc.arr = loc.arr
            stp_loc.dep = loc.dep
            stp_loc.pass_time = loc.pass_time
            stp_loc.public_arr = loc.public_arr
            stp_loc.public_dep = loc.public_dep
            stp_loc.platform = loc.platform
            stp_loc.line = loc.line
            stp_loc.path = loc.path
            stp_loc.activity = loc.activity
            db.session.add(stp_loc)
        
        db.session.commit()
        print(f"Moved {len(locations)} locations to ScheduleLocationSTPNew for schedule ID {schedule.id}")
    
    # Do the same for Overlay STP schedules
    overlay_schedules = db.session.query(ScheduleSTPOverlay).all()
    print(f"Found {len(overlay_schedules)} Overlay STP schedules")
    
    for schedule in overlay_schedules:
        locations = db.session.query(ScheduleLocation).filter_by(schedule_id=schedule.id).all()
        print(f"Found {len(locations)} locations for Overlay STP schedule ID {schedule.id}")
        
        for loc in locations:
            stp_loc = ScheduleLocationSTPOverlay()
            stp_loc.schedule_id = schedule.id
            stp_loc.sequence = loc.sequence
            stp_loc.location_type = loc.location_type
            stp_loc.tiploc = loc.tiploc
            stp_loc.arr = loc.arr
            stp_loc.dep = loc.dep
            stp_loc.pass_time = loc.pass_time
            stp_loc.public_arr = loc.public_arr
            stp_loc.public_dep = loc.public_dep
            stp_loc.platform = loc.platform
            stp_loc.line = loc.line
            stp_loc.path = loc.path
            stp_loc.activity = loc.activity
            db.session.add(stp_loc)
        
        db.session.commit()
        print(f"Moved {len(locations)} locations to ScheduleLocationSTPOverlay for schedule ID {schedule.id}")
    
    # Do the same for Cancellation STP schedules
    cancel_schedules = db.session.query(ScheduleSTPCancellation).all()
    print(f"Found {len(cancel_schedules)} Cancellation STP schedules")
    
    for schedule in cancel_schedules:
        locations = db.session.query(ScheduleLocation).filter_by(schedule_id=schedule.id).all()
        print(f"Found {len(locations)} locations for Cancellation STP schedule ID {schedule.id}")
        
        for loc in locations:
            stp_loc = ScheduleLocationSTPCancellation()
            stp_loc.schedule_id = schedule.id
            stp_loc.sequence = loc.sequence
            stp_loc.location_type = loc.location_type
            stp_loc.tiploc = loc.tiploc
            stp_loc.arr = loc.arr
            stp_loc.dep = loc.dep
            stp_loc.pass_time = loc.pass_time
            stp_loc.public_arr = loc.public_arr
            stp_loc.public_dep = loc.public_dep
            stp_loc.platform = loc.platform
            stp_loc.line = loc.line
            stp_loc.path = loc.path
            stp_loc.activity = loc.activity
            db.session.add(stp_loc)
        
        db.session.commit()
        print(f"Moved {len(locations)} locations to ScheduleLocationSTPCancellation for schedule ID {schedule.id}")
    
    print("Finished moving location data to STP-specific tables")

if __name__ == "__main__":
    with app.app_context():
        move_locations_to_stp_tables()