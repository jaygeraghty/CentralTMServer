"""
Script to run a small test file to verify our area of interest filtering
"""

import logging
import os
from cif_parser import CIFParser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_test():
    """Run a small test file through the parser to verify area of interest filtering"""
    # Create a test file with known locations in our area of interest
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

    # Write the test file
    test_file_path = "import/small_test.CIF"
    with open(test_file_path, "w") as f:
        f.write(test_file_content)
    
    logger.info(f"Created test file: {test_file_path}")
    
    # Reset the database first
    logger.info("Resetting database...")
    os.system("python reset_db.py")
    
    # Initialize the parser
    parser = CIFParser()
    
    # Process our test file
    logger.info("Processing test file...")
    parser.process_file(test_file_path)
    
    # Query the database to check results
    from database import get_db
    from sqlalchemy import text
    
    db = get_db()
    
    # Check which schedules were saved
    result = db.execute(text("""
        SELECT s.uid, COUNT(l.id) as location_count
        FROM schedules_ltp s
        JOIN schedule_locations_ltp l ON s.id = l.schedule_id
        GROUP BY s.uid
    """)).fetchall()
    
    logger.info("Schedules saved in the database:")
    for row in result:
        logger.info(f"  Schedule {row[0]} with {row[1]} locations")
    
    # Check which locations with CHRX and WLOE were saved
    chrx = db.execute(text("""
        SELECT COUNT(*) FROM schedule_locations_ltp WHERE tiploc = 'CHRX'
    """)).scalar()
    
    wloe = db.execute(text("""
        SELECT COUNT(*) FROM schedule_locations_ltp WHERE tiploc = 'WLOE'
    """)).scalar()
    
    logger.info(f"CHRX locations saved: {chrx}")
    logger.info(f"WLOE locations saved: {wloe}")
    
    # Check which schedules DON'T contain CHRX or WLOE but were saved anyway
    wrong_schedules = db.execute(text("""
        SELECT s.uid
        FROM schedules_ltp s
        WHERE NOT EXISTS (
            SELECT 1 FROM schedule_locations_ltp l 
            WHERE l.schedule_id = s.id AND (l.tiploc = 'CHRX' OR l.tiploc = 'WLOE')
        )
    """)).fetchall()
    
    if wrong_schedules:
        logger.error("Some schedules without locations in area of interest were saved:")
        for row in wrong_schedules:
            logger.error(f"  Schedule {row[0]}")
    else:
        logger.info("SUCCESS: Only schedules with locations in area of interest were saved!")
    
    # Cleanup
    os.remove(test_file_path)
    logger.info("Test completed.")

if __name__ == "__main__":
    run_test()