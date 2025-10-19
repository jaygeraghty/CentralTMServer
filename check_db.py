"""
Script to check database contents and verify STP tables
"""
import os
from datetime import date, datetime
from app import app, db
from models import (
    BasicSchedule, ScheduleLocation, Association,
    ScheduleLTP, ScheduleSTPNew, ScheduleSTPOverlay, ScheduleSTPCancellation,
    ScheduleLocationLTP, ScheduleLocationSTPNew, ScheduleLocationSTPOverlay, ScheduleLocationSTPCancellation
)

def check_database():
    """Check database contents and print summary"""
    print("Checking database contents...")
    
    # Check STP tables
    ltp_count = db.session.query(ScheduleLTP).count()
    new_count = db.session.query(ScheduleSTPNew).count()
    overlay_count = db.session.query(ScheduleSTPOverlay).count()
    cancel_count = db.session.query(ScheduleSTPCancellation).count()
    
    print(f"ScheduleLTP count: {ltp_count}")
    print(f"ScheduleSTPNew count: {new_count}")
    print(f"ScheduleSTPOverlay count: {overlay_count}")
    print(f"ScheduleSTPCancellation count: {cancel_count}")
    
    # Check location tables
    ltp_loc_count = db.session.query(ScheduleLocationLTP).count()
    new_loc_count = db.session.query(ScheduleLocationSTPNew).count()
    overlay_loc_count = db.session.query(ScheduleLocationSTPOverlay).count()
    cancel_loc_count = db.session.query(ScheduleLocationSTPCancellation).count()
    
    print(f"ScheduleLocationLTP count: {ltp_loc_count}")
    print(f"ScheduleLocationSTPNew count: {new_loc_count}")
    print(f"ScheduleLocationSTPOverlay count: {overlay_loc_count}")
    print(f"ScheduleLocationSTPCancellation count: {cancel_loc_count}")
    
    # Check legacy tables
    bs_count = db.session.query(BasicSchedule).count()
    sl_count = db.session.query(ScheduleLocation).count()
    
    print(f"BasicSchedule count: {bs_count}")
    print(f"ScheduleLocation count: {sl_count}")
    
    # Print sample data
    if ltp_count > 0:
        print("\nSample ScheduleLTP records:")
        ltp_records = db.session.query(ScheduleLTP).limit(2).all()
        for record in ltp_records:
            print(f"ID: {record.id}, UID: {record.uid}, Train Identity: {record.train_identity}, STP: {record.stp_indicator}")
            
        # Print sample locations
        if ltp_loc_count > 0:
            print("\nSample ScheduleLocationLTP records:")
            ltp_loc_records = db.session.query(ScheduleLocationLTP).filter(
                ScheduleLocationLTP.schedule_id == ltp_records[0].id
            ).limit(3).all()
            for loc in ltp_loc_records:
                print(f"Schedule ID: {loc.schedule_id}, TIPLOC: {loc.tiploc}, Type: {loc.location_type}, Platform: {loc.platform}")
    
    # Check if data was routed to legacy tables instead
    if bs_count > 0:
        print("\nSample BasicSchedule records:")
        bs_records = db.session.query(BasicSchedule).limit(2).all()
        for record in bs_records:
            print(f"ID: {record.id}, UID: {record.uid}, Train Identity: {record.train_identity}, STP: {record.stp_indicator}")

if __name__ == "__main__":
    with app.app_context():
        check_database()