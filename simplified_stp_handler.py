"""
Simplified alternative to handle loading CIF files with different STP indicators.

This module works by:
1. Loading all locations first
2. Then checking if any of them are in our area of interest
3. Only saving schedules that have locations in our area of interest

This solves the issue with schedules containing CHRX and WLOE not being saved.
"""

import os
import logging
import time
from database import get_db
from models import (
    ScheduleLTP, ScheduleLocationLTP, 
    ScheduleSTPNew, ScheduleLocationSTPNew,
    ScheduleSTPOverlay, ScheduleLocationSTPOverlay,
    ScheduleSTPCancellation, ScheduleLocationSTPCancellation
)
from flask import Flask
from app import app as flask_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Our area of interest
AREA_OF_INTEREST = {'CHRX', 'WLOE'}

def parse_test_file(file_path, area_of_interest=None):
    """
    Parse a test CIF file, storing only schedules with locations in our area of interest.
    
    Args:
        file_path: Path to the CIF file
        area_of_interest: Set of TIPLOC codes we're interested in (defaults to CHRX and WLOE)
    
    Returns:
        True if successful, False otherwise
    """
    if area_of_interest is None:
        area_of_interest = AREA_OF_INTEREST
        
    logger.info(f"Parsing file {file_path} with area of interest: {area_of_interest}")
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False

    # Use Flask app context for database operations
    with flask_app.app_context():
        # Get database connection
        db = get_db()
        
        # Variables to track current state
        current_schedule = None
        current_locations = []
        saved_schedules = 0
        skipped_schedules = 0
        
        try:
            # Process the file
            with open(file_path, 'r') as f:
                # Skip header
                header = f.readline()
                
                for line in f:
                    line = line.strip()
                    if not line or len(line) < 2:
                        continue
                        
                    record_type = line[0:2]
                    
                    # Basic Schedule (BS)
                    if record_type == 'BS':
                        # If we have a previous schedule, decide whether to save it
                        if current_schedule is not None:
                            # Check if any locations are in our area of interest
                            is_cancellation = current_schedule.stp_indicator == 'C'
                            has_locations_of_interest = any(
                                loc['tiploc'] in area_of_interest for loc in current_locations
                            )
                            
                            if is_cancellation or has_locations_of_interest:
                                # Save this schedule and its locations
                                db.add(current_schedule)
                                db.flush()  # To get the ID
                                
                                # Add all locations for this schedule
                                for loc_data in current_locations:
                                    loc = None
                                    
                                    # Create appropriate location object based on schedule type
                                    if isinstance(current_schedule, ScheduleLTP):
                                        loc = ScheduleLocationLTP(**loc_data)
                                    elif isinstance(current_schedule, ScheduleSTPNew):
                                        loc = ScheduleLocationSTPNew(**loc_data)
                                    elif isinstance(current_schedule, ScheduleSTPOverlay):
                                        loc = ScheduleLocationSTPOverlay(**loc_data)
                                    elif isinstance(current_schedule, ScheduleSTPCancellation):
                                        loc = ScheduleLocationSTPCancellation(**loc_data)
                                        
                                    if loc:
                                        loc.schedule_id = current_schedule.id
                                        db.add(loc)
                                        
                                # Log what we're saving
                                if is_cancellation:
                                    logger.info(f"Saving cancellation schedule {current_schedule.uid}")
                                else:
                                    logger.info(f"Saving schedule {current_schedule.uid} with locations in area of interest")
                                    
                                saved_schedules += 1
                            else:
                                # Skip this schedule as it has no locations in our area of interest
                                logger.debug(f"Skipping schedule - no locations in area of interest")
                                skipped_schedules += 1
                                
                        # Reset for new schedule
                        current_locations = []
                        
                        # Parse BS record
                        uid = line[3:9].strip()
                        stp_indicator = line[79:80]  # P, N, O, C
                        
                        # Create appropriate schedule object based on STP indicator
                        if stp_indicator == 'P':
                            current_schedule = ScheduleLTP()
                        elif stp_indicator == 'N':
                            current_schedule = ScheduleSTPNew()
                        elif stp_indicator == 'O':
                            current_schedule = ScheduleSTPOverlay()
                        elif stp_indicator == 'C':
                            current_schedule = ScheduleSTPCancellation()
                        else:
                            logger.warning(f"Unknown STP indicator: {stp_indicator}")
                            current_schedule = None
                            continue
                            
                        # Populate schedule fields
                        current_schedule.uid = uid
                        current_schedule.stp_indicator = stp_indicator
                        current_schedule.transaction_type = 'N'  # New
                        
                        # Other required fields
                        runs_from_str = line[9:15].strip()
                        runs_to_str = line[15:21].strip()
                        days_run = line[21:28].strip()
                        
                        current_schedule.runs_from = f"20{runs_from_str[4:6]}-{runs_from_str[2:4]}-{runs_from_str[0:2]}"
                        current_schedule.runs_to = f"20{runs_to_str[4:6]}-{runs_to_str[2:4]}-{runs_to_str[0:2]}"
                        current_schedule.days_run = days_run
                        
                        # Additional fields
                        current_schedule.train_status = line[29:30]
                        current_schedule.train_category = line[30:32].strip()
                        current_schedule.train_identity = line[32:36].strip()
                        current_schedule.service_code = line[41:49].strip()
                        current_schedule.power_type = line[50:53].strip() or "DMU"  # Default value 
                        current_schedule.speed = int(line[53:56]) if line[53:56].strip() else 100
                        current_schedule.operating_chars = line[56:60].strip() or "B"  # Default value
                                                
                    # Location records (LO, LI, LT)
                    elif record_type in ['LO', 'LI', 'LT']:
                        # Only process if we have a valid schedule
                        if current_schedule is None:
                            continue
                            
                        # Get TIPLOC
                        tiploc = line[2:10].strip()
                        
                        # Based on record type, parse fields
                        if record_type == 'LO':  # Origin
                            loc_data = {
                                'sequence': len(current_locations) + 1,
                                'tiploc': tiploc,
                                'location_type': 'LO',
                                'dep': line[10:15].strip() or None,
                                'public_dep': line[15:19].strip() or None,
                                'platform': line[19:22].strip() or None,
                                'line': line[22:25].strip() or None,
                                'activity': line[29:41].strip() or None
                            }
                        elif record_type == 'LI':  # Intermediate
                            loc_data = {
                                'sequence': len(current_locations) + 1,
                                'tiploc': tiploc,
                                'location_type': 'LI',
                                'arr': line[10:15].strip() or None,
                                'dep': line[15:20].strip() or None,
                                'pass_time': line[20:25].strip() or None,
                                'public_arr': line[25:29].strip() or None,
                                'public_dep': line[29:33].strip() or None,
                                'platform': line[33:36].strip() or None,
                                'line': line[36:39].strip() or None,
                                'path': line[39:42].strip() or None,
                                'activity': line[42:54].strip() or None
                            }
                        elif record_type == 'LT':  # Terminating
                            loc_data = {
                                'sequence': len(current_locations) + 1,
                                'tiploc': tiploc,
                                'location_type': 'LT',
                                'arr': line[10:15].strip() or None,
                                'public_arr': line[15:19].strip() or None,
                                'platform': line[19:22].strip() or None,
                                'path': line[22:25].strip() or None,
                                'activity': line[25:37].strip() or None
                            }
                            
                        # Add to our list of locations for this schedule
                        current_locations.append(loc_data)
                        
                # After processing all lines, handle the last schedule
                if current_schedule is not None:
                    # Check if any locations are in our area of interest
                    is_cancellation = current_schedule.stp_indicator == 'C'
                    has_locations_of_interest = any(
                        loc['tiploc'] in area_of_interest for loc in current_locations
                    )
                    
                    if is_cancellation or has_locations_of_interest:
                        # Save this schedule and its locations
                        db.add(current_schedule)
                        db.flush()  # To get the ID
                        
                        # Add all locations for this schedule
                        for loc_data in current_locations:
                            loc = None
                            
                            # Create appropriate location object based on schedule type
                            if isinstance(current_schedule, ScheduleLTP):
                                loc = ScheduleLocationLTP(**loc_data)
                            elif isinstance(current_schedule, ScheduleSTPNew):
                                loc = ScheduleLocationSTPNew(**loc_data)
                            elif isinstance(current_schedule, ScheduleSTPOverlay):
                                loc = ScheduleLocationSTPOverlay(**loc_data)
                            elif isinstance(current_schedule, ScheduleSTPCancellation):
                                loc = ScheduleLocationSTPCancellation(**loc_data)
                                
                            if loc:
                                loc.schedule_id = current_schedule.id
                                db.add(loc)
                                
                        # Log what we're saving
                        if is_cancellation:
                            logger.info(f"Saving cancellation schedule {current_schedule.uid}")
                        else:
                            logger.info(f"Saving schedule {current_schedule.uid} with locations in area of interest")
                            
                        saved_schedules += 1
                    else:
                        # Skip this schedule as it has no locations in our area of interest
                        logger.debug(f"Skipping schedule - no locations in area of interest")
                        skipped_schedules += 1
                
            # Commit all changes
            db.commit()
            
            logger.info(f"Finished processing file {file_path}")
            logger.info(f"Saved {saved_schedules} schedules, skipped {skipped_schedules} schedules")
            
            return True
                
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            db.rollback()
            return False

def run_test():
    """Run a test with a simplified parser that correctly handles area of interest filtering"""
    # Reset database first
    os.system("python reset_db.py")
    
    # Create a test file or use an existing one
    test_file = "import/test_simple.CIF"
    if not os.path.exists(test_file):
        logger.info("Creating test file...")
        with open(test_file, "w") as f:
            f.write("""HDTPTEST01FVNNPVS20250517142211VGWDFDS
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
ZZ""")
    
    # Parse the test file
    logger.info("Parsing test file...")
    success = parse_test_file(test_file)
    
    if success:
        # Verify results
        with flask_app.app_context():
            db = get_db()
            
            from sqlalchemy import func, text
            
            # Check CHRX locations
            chrx_count = db.execute(
                text("SELECT COUNT(*) FROM schedule_locations_ltp WHERE tiploc = 'CHRX'")
            ).scalar()
            
            # Check WLOE locations
            wloe_count = db.execute(
                text("SELECT COUNT(*) FROM schedule_locations_ltp WHERE tiploc = 'WLOE'")
            ).scalar()
            
            logger.info(f"CHRX locations in database: {chrx_count}")
            logger.info(f"WLOE locations in database: {wloe_count}")
            
            if chrx_count > 0 and wloe_count > 0:
                logger.info("SUCCESS: Both CHRX and WLOE locations found in database!")
            else:
                logger.error("ERROR: Some locations not found in database")
    else:
        logger.error("Failed to parse test file")

if __name__ == "__main__":
    run_test()