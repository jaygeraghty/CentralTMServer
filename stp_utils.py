"""
Utility functions for handling STP indicators and testing area of interest filtering.
"""

import os
import logging
from flask import Flask
from app import app as flask_app
from database import get_db
from sqlalchemy import text

# Configure logging
logger = logging.getLogger(__name__)

def check_locations_in_database(area_of_interest=['CHRX', 'WLOE']):
    """
    Check if the given locations exist in the database tables.
    
    Args:
        area_of_interest: List of TIPLOC codes to check for
        
    Returns:
        Dict with counts for each location across different tables
    """
    results = {}
    
    with flask_app.app_context():
        db = get_db()
        
        for location in area_of_interest:
            location_results = {}
            
            # Check in each relevant table
            tables = [
                'schedule_locations_ltp',
                'schedule_locations_stp_new',
                'schedule_locations_stp_overlay',
                'schedule_locations_stp_cancellation'
            ]
            
            for table in tables:
                try:
                    count = db.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE tiploc = :tiploc"),
                        {'tiploc': location}
                    ).scalar()
                    
                    location_results[table] = count
                except Exception as e:
                    logger.error(f"Error checking {table} for {location}: {str(e)}")
                    location_results[table] = -1
            
            results[location] = location_results
    
    return results

def process_test_file(file_path, area_of_interest=['CHRX', 'WLOE']):
    """
    Directly process a test file to verify area of interest filtering.
    
    Args:
        file_path: Path to the CIF file
        area_of_interest: List of TIPLOC codes we're interested in
        
    Returns:
        True if successful, False otherwise
    """
    # Reset the database first to start with a clean slate
    os.system("python reset_db.py")
    
    # Run the parser to process the file
    os.system(f"cp {file_path} import/test_process.CIF")
    os.system("python run_cif_processing.py")
    
    # Check if the locations were added to the database
    results = check_locations_in_database(area_of_interest)
    
    # Log the results
    for location, counts in results.items():
        for table, count in counts.items():
            if count > 0:
                logger.info(f"Found {count} records with {location} in {table}")
            else:
                logger.warning(f"No records found with {location} in {table}")
    
    # Check if we have any records for our locations
    success = any(
        any(count > 0 for count in table_counts.values())
        for table_counts in results.values()
    )
    
    if success:
        logger.info("SUCCESS: Found at least one record for a location in area of interest")
    else:
        logger.error("ERROR: No records found for any locations in area of interest")
    
    return success