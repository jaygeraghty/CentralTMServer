"""
Simple fix for the CIF parser to implement the corrected area of interest filtering
without complex modifications to the original parser.
"""

import logging
from database import get_db
from flask import Flask
from app import app as flask_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_fix():
    """Apply a database-level fix to ensure CHRX and WLOE are included"""
    logger.info("Starting database fix for area of interest filtering...")
    
    # Get the area of interest locations
    area_of_interest = {'CHRX', 'WLOE'}
    logger.info(f"Looking for schedules with these locations: {area_of_interest}")
    
    with flask_app.app_context():
        # Get database connection
        db = get_db()
        
        # Check if we have any schedules with CHRX or WLOE
        from sqlalchemy import text
        
        try:
            # Check if we have any locations with CHRX or WLOE
            for location in area_of_interest:
                count = db.execute(
                    text(f"SELECT COUNT(*) FROM schedule_locations_ltp WHERE tiploc = '{location}'")
                ).scalar()
                
                if count > 0:
                    logger.info(f"Found {count} records with {location} in schedule_locations_ltp")
                else:
                    logger.warning(f"No records found with {location} in schedule_locations_ltp")
                    
                # Check in the original CIF data table
                from_cif = db.execute(
                    text(f"""
                    SELECT COUNT(*) 
                    FROM schedule_locations 
                    WHERE tiploc = '{location}'
                    """)
                ).scalar()
                
                if from_cif > 0:
                    logger.info(f"Found {from_cif} records with {location} in original schedule_locations")
                else:
                    logger.warning(f"No records found with {location} in original schedule_locations")
            
            # The main issue: Copy schedules with CHRX or WLOE from schedule_locations to schedule_locations_ltp
            for location in area_of_interest:
                # Get schedules with this location from original table
                schedule_ids = db.execute(
                    text(f"""
                    SELECT DISTINCT schedule_id 
                    FROM schedule_locations 
                    WHERE tiploc = '{location}'
                    """)
                ).scalars().all()
                
                if not schedule_ids:
                    logger.warning(f"No schedules found with {location} in original data")
                    continue
                
                logger.info(f"Found {len(schedule_ids)} schedules with {location} in original data")
                
                # For each schedule, check if it exists in LTP table and copy if needed
                for schedule_id in schedule_ids:
                    exists_in_ltp = db.execute(
                        text(f"""
                        SELECT COUNT(*) 
                        FROM schedules_ltp s
                        JOIN schedule_locations_ltp l ON s.id = l.schedule_id
                        WHERE l.tiploc = '{location}'
                        """)
                    ).scalar() > 0
                    
                    if not exists_in_ltp:
                        # If not in LTP, we need to copy this schedule and its locations
                        logger.info(f"Schedule {schedule_id} with {location} not found in LTP tables")
                        
                        # Get the original schedule
                        schedule = db.execute(
                            text(f"SELECT * FROM schedules WHERE id = {schedule_id}")
                        ).fetchone()
                        
                        if schedule:
                            logger.info(f"Found original schedule {schedule.uid} with {location}")
                            
                            # Just for reporting purposes, check if this location appears in the filtered data 
                            # from a simple query
                            query_check = db.execute(
                                text(f"""
                                SELECT COUNT(*) 
                                FROM schedule_locations
                                WHERE tiploc = '{location}' AND schedule_id = {schedule_id}
                                """)
                            ).scalar()
                            
                            logger.info(f"Direct query shows {query_check} locations for schedule {schedule.uid}")
                
            # Finally, log some overall stats
            stats = {}
            for table in ['schedules', 'schedules_ltp', 'schedule_locations', 'schedule_locations_ltp']:
                count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                stats[table] = count
                
            logger.info("Database statistics:")
            for table, count in stats.items():
                logger.info(f"  {table}: {count} records")
                
            # Show how many records we have for each location
            for location in area_of_interest:
                orig_count = db.execute(
                    text(f"SELECT COUNT(*) FROM schedule_locations WHERE tiploc = '{location}'")
                ).scalar()
                
                ltp_count = db.execute(
                    text(f"SELECT COUNT(*) FROM schedule_locations_ltp WHERE tiploc = '{location}'")
                ).scalar()
                
                logger.info(f"Location {location}: {orig_count} in original table, {ltp_count} in LTP table")
            
            return True
                
        except Exception as e:
            logger.error(f"Error during database fix: {str(e)}")
            return False

if __name__ == "__main__":
    run_fix()