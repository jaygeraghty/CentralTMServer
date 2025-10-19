"""
Test script to verify that CHRX and WLOE stations appear in the database.
"""

import os
import logging
from sqlalchemy import text
from database import get_db
from flask import Flask
from app import app as flask_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_check():
    """Check if CHRX and WLOE stations are in the database"""
    logger.info("Testing if CHRX and WLOE stations appear in database tables...")
    
    with flask_app.app_context():
        db = get_db()
        locations = ['CHRX', 'WLOE']
        
        # Check if stations exist in STP tables
        for location in locations:
            for table in ['schedule_locations_ltp', 'schedule_locations_stp_new', 
                         'schedule_locations_stp_overlay', 'schedule_locations_stp_cancellation']:
                try:
                    count = db.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE tiploc = :loc"),
                        {"loc": location}
                    ).scalar()
                    
                    if count > 0:
                        logger.info(f"Found {count} records for {location} in {table}")
                    else:
                        logger.warning(f"No records found for {location} in {table}")
                except Exception as e:
                    logger.error(f"Error checking {table}: {str(e)}")
        
        # Check the area of interest in the parser
        from cif_parser import CIFParser
        parser = CIFParser()
        logger.info(f"Area of interest in parser: {parser.area_of_interest}")
        
        if 'CHRX' in parser.area_of_interest and 'WLOE' in parser.area_of_interest:
            logger.info("CHRX and WLOE are correctly included in the area of interest")
        else:
            logger.error("CHRX and/or WLOE missing from area of interest")
            
        # Check if the parser correctly identifies these locations in our test file
        test_file = "import/test_good.CIF"
        if os.path.exists(test_file):
            logger.info(f"Reading {test_file} to check for CHRX and WLOE...")
            
            # Count occurrences in the file
            chrx_count = 0
            wloe_count = 0
            
            with open(test_file, 'r') as f:
                for line in f:
                    if line.startswith(('LO', 'LI', 'LT')):
                        tiploc = line[2:10].strip()
                        if tiploc == 'CHRX':
                            chrx_count += 1
                        elif tiploc == 'WLOE':
                            wloe_count += 1
            
            logger.info(f"Found in file: CHRX: {chrx_count} times, WLOE: {wloe_count} times")
            
            if chrx_count == 0 and wloe_count == 0:
                logger.warning("Neither CHRX nor WLOE found in test file - this may explain why they're not in database")
                logger.info("You should use a file that contains these locations for testing")
        else:
            logger.error(f"Test file {test_file} not found")

if __name__ == "__main__":
    run_check()