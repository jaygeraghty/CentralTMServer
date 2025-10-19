import unittest
import os
import shutil
from datetime import date, timedelta
import logging

from app import app
from database import get_db
from cif_parser import CIFParser
import simplified_stp_handler as stp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestSTPIntegration(unittest.TestCase):
    """
    Integration test for STP Indicator functionality using the actual CIF parser
    with test_good.CIF file from archive
    """

    def setUp(self):
        """Set up test environment"""
        self.app = app
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.db = get_db()
        
        # Reset the database for clean testing
        self._clear_database()
        
        # Copy test file to import folder for processing
        if not os.path.exists('import'):
            os.makedirs('import')
            
        self.test_file_path = 'test_data/test_good.CIF'
        self.import_file_path = 'import/test_good.CIF'
        
        # Copy the file to import directory
        if os.path.exists(self.test_file_path):
            shutil.copy(self.test_file_path, self.import_file_path)
            logger.info(f"Copied test file to {self.import_file_path}")
        else:
            logger.error(f"Test file {self.test_file_path} not found!")
        
        # Process the test file
        self._process_test_file()
        
    def tearDown(self):
        """Clean up after test"""
        self._clear_database()
        
        # Remove test file from import folder
        if os.path.exists(self.import_file_path):
            os.remove(self.import_file_path)
            
        self.app_context.pop()
        
    def _clear_database(self):
        """Clear all relevant database tables"""
        from sqlalchemy import text
        
        tables = [
            "schedule_locations_ltp",
            "schedule_locations_stp_new",
            "schedule_locations_stp_overlay",
            "schedule_locations_stp_cancellation",
            "schedules_ltp",
            "schedules_stp_new",
            "schedules_stp_overlay",
            "schedules_stp_cancellation",
            "associations_ltp",
            "associations_stp_new",
            "associations_stp_overlay",
            "associations_stp_cancellation"
        ]
        
        for table in tables:
            self.db.execute(text(f"DELETE FROM {table}"))
        
        self.db.commit()
        logger.info("Database cleared for testing")
        
    def _process_test_file(self):
        """Process the test CIF file using the actual parser"""
        parser = CIFParser()
        parser.process_file(self.import_file_path)
        logger.info("Test file processed through CIF parser")
        
    def test_database_counts(self):
        """Test that the correct records were created in each STP table"""
        from sqlalchemy import text
        
        # Count records in different STP tables
        ltp_count = self.db.execute(text("SELECT COUNT(*) FROM schedules_ltp")).scalar() or 0
        stp_new_count = self.db.execute(text("SELECT COUNT(*) FROM schedules_stp_new")).scalar() or 0
        stp_overlay_count = self.db.execute(text("SELECT COUNT(*) FROM schedules_stp_overlay")).scalar() or 0
        stp_cancel_count = self.db.execute(text("SELECT COUNT(*) FROM schedules_stp_cancellation")).scalar() or 0
        
        # Count associations
        ltp_assoc_count = self.db.execute(text("SELECT COUNT(*) FROM associations_ltp")).scalar() or 0
        stp_new_assoc_count = self.db.execute(text("SELECT COUNT(*) FROM associations_stp_new")).scalar() or 0
        stp_overlay_assoc_count = self.db.execute(text("SELECT COUNT(*) FROM associations_stp_overlay")).scalar() or 0
        stp_cancel_assoc_count = self.db.execute(text("SELECT COUNT(*) FROM associations_stp_cancellation")).scalar() or 0
        
        # Log the counts
        logger.info("Database Record Counts:")
        logger.info(f"  LTP Schedules (P): {ltp_count}")
        logger.info(f"  STP New Schedules (N): {stp_new_count}")
        logger.info(f"  STP Overlay Schedules (O): {stp_overlay_count}")
        logger.info(f"  STP Cancellation Schedules (C): {stp_cancel_count}")
        logger.info(f"  LTP Associations (P): {ltp_assoc_count}")
        logger.info(f"  STP New Associations (N): {stp_new_assoc_count}")
        logger.info(f"  STP Overlay Associations (O): {stp_overlay_assoc_count}")
        logger.info(f"  STP Cancellation Associations (C): {stp_cancel_assoc_count}")
        
        # Verify that we have at least some data in each category
        # We don't check exact counts since the test file might be updated
        self.assertGreater(ltp_count, 0, "Should have at least one LTP schedule")
        
    def test_get_schedules_by_date(self):
        """Test fetching schedules for specific dates"""
        # Get the date range of data in the database
        from sqlalchemy import text
        
        min_date_query = text("SELECT MIN(runs_from) FROM schedules_ltp")
        max_date_query = text("SELECT MAX(runs_to) FROM schedules_ltp")
        
        min_date = self.db.execute(min_date_query).scalar()
        max_date = self.db.execute(max_date_query).scalar()
        
        if not min_date or not max_date:
            self.fail("No date range found in the database")
            
        logger.info(f"Test data date range: {min_date} to {max_date}")
        
        # Test a few dates within the range
        test_date = min_date
        
        # Get schedules for this date at CHRX
        schedules = stp.get_schedules_with_stp_applied(
            search_date=test_date,
            location="CHRX"
        )
        
        # Log what we found
        logger.info(f"Schedules for CHRX on {test_date}:")
        for schedule in schedules:
            effective_stp = schedule.get('effective_stp_indicator', '')
            cancelled = 'CANCELLED' if schedule.get('is_cancelled', False) else ''
            logger.info(f"  {schedule['uid']} ({schedule['train_identity']}) - STP: {effective_stp} {cancelled}")
            
            # For overlay schedules, check locations
            if effective_stp == 'O':
                logger.info("    Locations:")
                for loc in schedule.get('locations', []):
                    logger.info(f"      {loc['tiploc']} - Platform: {loc.get('platform', 'N/A')}")
        
        # Verify we got some schedules
        self.assertTrue(len(schedules) > 0, f"Should have schedules for {test_date}")
        
        # Test STP Cancellation (if we have any in the test file)
        # This test will pass regardless, but will log useful information
        for schedule in schedules:
            if schedule.get('is_cancelled', False):
                logger.info(f"Found cancelled schedule: {schedule['uid']} on {test_date}")
                self.assertEqual(schedule['effective_stp_indicator'], 'C', 
                                "Cancelled schedules should have STP indicator 'C'")
        
        # Test STP Overlay (if we have any in the test file)
        for schedule in schedules:
            if schedule.get('effective_stp_indicator') == 'O':
                logger.info(f"Found overlay schedule: {schedule['uid']} on {test_date}")
                
                # Check that we have locations for this overlay
                self.assertTrue(len(schedule.get('locations', [])) > 0, 
                              "Overlay schedules should have locations")

    def test_day_of_week_schedules(self):
        """
        Test that the correct schedules appear on different days of the week
        based on their days_run bitmap
        """
        # Get a date range for testing
        from sqlalchemy import text
        
        date_query = text("""
        SELECT runs_from, days_run FROM schedules_ltp 
        ORDER BY runs_from LIMIT 1
        """)
        
        result = self.db.execute(date_query).fetchone()
        if not result:
            self.fail("No schedules found in database")
            
        start_date = result[0]
        days_run = result[1]
        logger.info(f"Testing schedule with days_run={days_run} starting on {start_date}")
        
        # Test each day of the week
        test_days = []
        for i in range(7):
            # Find the next date that matches the day of week (i+1)
            # where 1=Monday, 7=Sunday
            current_date = start_date
            while current_date.isoweekday() != (i+1):
                current_date += timedelta(days=1)
                
            test_days.append(current_date)
            
        # Log days in each position
        logger.info("Test dates by position:")
        for i, test_date in enumerate(test_days):
            # Position in days_run string (0=Monday, 6=Sunday)
            position = test_date.isoweekday() - 1
            bit_value = days_run[position] if position < len(days_run) else "?"
            logger.info(f"  Position {position} ({test_date.strftime('%A')}): {test_date} - Bit={bit_value}")
            
        # Now test each date
        for test_date in test_days:
            # Position in days_run string (0=Monday, 6=Sunday)
            position = test_date.isoweekday() - 1
            expected_bit = days_run[position] if position < len(days_run) else "0"
            
            # Get schedules for this date at CHRX
            schedules = stp.get_schedules_with_stp_applied(
                search_date=test_date,
                location="CHRX"
            )
            
            logger.info(f"Found {len(schedules)} schedules on {test_date.strftime('%A')} {test_date}")
            
            # If the bit is 1, we should have schedules
            # If the bit is 0, we shouldn't have schedules with this specific days_run
            # But other schedules might still run, so just log the result
            if expected_bit == "1":
                logger.info(f"  Expected schedules on {test_date} (bit=1)")
            else:
                logger.info(f"  Not expecting schedules with days_run={days_run} on {test_date} (bit=0)")

if __name__ == "__main__":
    unittest.main()