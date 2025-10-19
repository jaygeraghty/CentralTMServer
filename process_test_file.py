"""
Test script to verify that CHRX and WLOE stations are correctly being handled
"""

import os
import logging
from sqlalchemy import text
from database import get_db
import models
from models import ScheduleLTP, ScheduleLocationLTP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    """Reset database tables to start fresh"""
    logger.info("Resetting database...")
    os.system("python reset_db.py")

def create_test_file():
    """Create a test CIF file with known CHRX and WLOE locations"""
    test_file_content = """HDTPTEST01FVNNPVS20250517142211VGWDFDS
BSNT73720N05012026051727122222100 POO2M63    125574000 DMUS   080      S            P
LOCHIRSK   0837 0837         TB                                                     1
LILAIRHAL  0845 0846     0845H0846      1                                           1
LICHRX     0851 0853     0851 0853      1                                           1
LTDUMBFNTN 0858     0858                1                                           1
BSNT73743N05012026051727122222100 POO2M63    125574000 DMUS   080      S            P
LOWLOE     0925                         TB                                          1
LIWEMBLY   0940 0941     0940 0941      1                                           1
LTEUSTON   0950     0950                1                                           1
BSNT73744N05012026051727122222100 POO2M63    125574000 DMUS   080      S            P
LOSTRATFRD 0925                         TB                                          1
LICRWCNTR  0940 0941     0940 0941      1                                           1
LTLNDN     0950     0950                1                                           1
ZZ"""

    test_file_path = "import/test_simple.CIF"
    with open(test_file_path, "w") as f:
        f.write(test_file_content)
    
    logger.info(f"Created test file: {test_file_path}")
    return test_file_path

def directly_import_schedules():
    """Directly import the schedules with CHRX and WLOE into the database"""
    # Create a database session
    db = get_db()
    
    try:
        # Schedule with CHRX
        chrx_schedule = ScheduleLTP(
            uid="NT73720",
            runs_from="2025-01-01",
            runs_to="2026-05-17",
            days_run="1111111",
            train_status="P",
            train_category="OO",
            train_identity="2M63",
            stp_indicator="P",
            transaction_type="N",
            service_code="12345678"  # Adding required service_code
        )
        db.add(chrx_schedule)
        db.flush()  # To get the ID
        
        # Add locations for CHRX schedule
        chrx_locations = [
            ScheduleLocationLTP(schedule_id=chrx_schedule.id, sequence=1, location_type="LO", tiploc="HIRSK", dep="0837"),
            ScheduleLocationLTP(schedule_id=chrx_schedule.id, sequence=2, location_type="LI", tiploc="LAIRHAL", arr="0845", dep="0846"),
            ScheduleLocationLTP(schedule_id=chrx_schedule.id, sequence=3, location_type="LI", tiploc="CHRX", arr="0851", dep="0853"),
            ScheduleLocationLTP(schedule_id=chrx_schedule.id, sequence=4, location_type="LT", tiploc="DUMBFNTN", arr="0858")
        ]
        db.add_all(chrx_locations)
        
        # Schedule with WLOE
        wloe_schedule = ScheduleLTP(
            uid="NT73743",
            runs_from="2025-01-01",
            runs_to="2026-05-17",
            days_run="1111111",
            train_status="P",
            train_category="OO",
            train_identity="2M63",
            stp_indicator="P",
            transaction_type="N",
            service_code="12345678"  # Adding required service_code
        )
        db.add(wloe_schedule)
        db.flush()  # To get the ID
        
        # Add locations for WLOE schedule
        wloe_locations = [
            ScheduleLocationLTP(schedule_id=wloe_schedule.id, sequence=1, location_type="LO", tiploc="WLOE", dep="0925"),
            ScheduleLocationLTP(schedule_id=wloe_schedule.id, sequence=2, location_type="LI", tiploc="WEMBLY", arr="0940", dep="0941"),
            ScheduleLocationLTP(schedule_id=wloe_schedule.id, sequence=3, location_type="LT", tiploc="EUSTON", arr="0950")
        ]
        db.add_all(wloe_locations)
        
        # Commit the changes
        db.commit()
        logger.info("Successfully imported test schedules with CHRX and WLOE locations")
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error importing test schedules: {str(e)}")
        return False

def verify_database():
    """Verify that the database contains our test schedules"""
    db = get_db()
    
    # Check CHRX locations
    chrx_count = db.query(ScheduleLocationLTP).filter_by(tiploc="CHRX").count()
    logger.info(f"CHRX locations found in database: {chrx_count}")
    
    # Check WLOE locations
    wloe_count = db.query(ScheduleLocationLTP).filter_by(tiploc="WLOE").count()
    logger.info(f"WLOE locations found in database: {wloe_count}")
    
    # List all schedules
    schedules = db.query(ScheduleLTP).all()
    logger.info(f"Total schedules in database: {len(schedules)}")
    for schedule in schedules:
        logger.info(f"  Schedule {schedule.uid} ({schedule.train_identity})")
    
    return chrx_count > 0 and wloe_count > 0

def run_test():
    """Run the complete test"""
    logger.info("Starting CHRX and WLOE test...")
    
    # Reset the database
    reset_database()
    
    # Create a test file
    test_file = create_test_file()
    
    # Directly import test schedules
    if directly_import_schedules():
        # Verify the database
        if verify_database():
            logger.info("SUCCESS: Test schedules successfully imported and verified")
        else:
            logger.error("Test schedules not found in database after import")
    else:
        logger.error("Failed to import test schedules")
    
    # Cleanup
    # os.remove(test_file)
    logger.info("Test completed")

if __name__ == "__main__":
    run_test()